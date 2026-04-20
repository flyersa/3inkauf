import logging
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, func

from app.config import get_settings
from app.core import runtime_config
from app.core.deps import get_current_user
from app.core.websocket import manager
from app.database import get_session
from app.models.user import User
from app.models.list_item import ListItem
from app.models.item_image import ItemImage
from app.core.security import signed_image_url
from app.core.image_validation import validate_image
from app.routers.lists import get_list_with_access
from app.schemas.list_item import (
    CreateItemRequest, UpdateItemRequest, ReorderItemsRequest, ItemResponse,
)
from app.services.ml_service import ml_service

logger = logging.getLogger(__name__)
MAX_PHOTO_SIZE = 8 * 1024 * 1024

router = APIRouter(prefix="/lists/{list_id}/items", tags=["items"])


async def enrich_item(item: ListItem, session: AsyncSession) -> ItemResponse:
    """Add user info to item response."""
    user_result = await session.execute(select(User).where(User.id == item.added_by_id))
    user = user_result.scalar_one_or_none()
    return ItemResponse(
        id=item.id, list_id=item.list_id, category_id=item.category_id,
        added_by_id=item.added_by_id,
        added_by_name=user.display_name if user else "Unknown",
        added_by_color=user.color if user else "#999999",
        name=item.name, quantity=item.quantity, checked=item.checked,
        sort_order=item.sort_order,
        image_url=signed_image_url(item.image_path) if item.image_path else None,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


async def get_items_enriched(list_id: str, session: AsyncSession) -> list[ItemResponse]:
    result = await session.execute(
        select(ListItem).where(ListItem.list_id == list_id)
        .order_by(ListItem.sort_order, ListItem.created_at)
    )
    items = result.scalars().all()
    user_ids = list(set(i.added_by_id for i in items))
    if not user_ids:
        return []
    users_result = await session.execute(select(User).where(User.id.in_(user_ids)))
    users_map = {u.id: u for u in users_result.scalars().all()}
    default_user = User(display_name="Unknown", color="#999999")
    return [
        ItemResponse(
            id=item.id, list_id=item.list_id, category_id=item.category_id,
            added_by_id=item.added_by_id,
            added_by_name=users_map.get(item.added_by_id, default_user).display_name,
            added_by_color=users_map.get(item.added_by_id, default_user).color,
            name=item.name, quantity=item.quantity, checked=item.checked,
            sort_order=item.sort_order,
        image_url=signed_image_url(item.image_path) if item.image_path else None,
        created_at=item.created_at,
            updated_at=item.updated_at,
        )
        for item in items
    ]


@router.get("", response_model=list[ItemResponse])
async def get_items(
    list_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await get_list_with_access(list_id, current_user, session)
    return await get_items_enriched(list_id, session)


@router.post("", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(
    list_id: str,
    req: CreateItemRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await get_list_with_access(list_id, current_user, session, require_edit=True)

    # Reject duplicates (case-insensitive, trimmed) within the same list.
    name_key = (req.name or "").strip().lower()
    dupe = await session.execute(
        select(ListItem).where(
            ListItem.list_id == list_id,
            func.lower(func.trim(ListItem.name)) == name_key,
        )
    )
    if dupe.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"'{req.name}' is already on this list",
        )

    result = await session.execute(
        select(ListItem.sort_order).where(ListItem.list_id == list_id)
        .order_by(ListItem.sort_order.desc()).limit(1)
    )
    max_order = result.scalar() or 0

    item = ListItem(
        list_id=list_id,
        added_by_id=current_user.id,
        name=req.name,
        quantity=req.quantity,
        category_id=req.category_id,
        sort_order=max_order + 10,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)

    response = await enrich_item(item, session)

    await manager.broadcast(list_id, {
        "type": "item_added",
        "item": response.model_dump(mode="json"),
    })

    return response


# /from-photo stays LITERAL (not a path-param) so it must be declared before /{item_id}.
@router.post("/from-photo", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item_from_photo(
    list_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """User takes a photo of a single item → AI identifies it → item is added
    uncategorized to the list. Reuses the fridge model since the task is the
    same shape (identify grocery product from a photograph)."""
    await get_list_with_access(list_id, current_user, session, require_edit=True)

    settings = get_settings()
    if not settings.ollama_url:
        raise HTTPException(status_code=503, detail="Photo item recognition requires Ollama")
    content = await file.read()
    if len(content) > MAX_PHOTO_SIZE:
        raise HTTPException(status_code=400, detail="Image too large (max 8MB)")
    # Verify actual bytes are a real image — Content-Type is attacker-controlled.
    actual_mime = validate_image(content)

    language = "German" if (current_user.locale or "de").lower().startswith("de") else "English"
    try:
        detected = ml_service.identify_item_from_image(
            content,
            language=language,
            ollama_url=settings.ollama_url,
            ollama_model=runtime_config.get_item_model(),
        )
    except Exception as e:
        logger.exception("Item-photo recognition failed")
        raise HTTPException(status_code=500, detail=f"Image recognition failed: {e}")

    name = (detected.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="Could not identify an item in the photo")
    qty = detected.get("quantity") or None

    # Duplicate check (mirror of manual create_item).
    name_key = name.lower()
    dupe = await session.execute(
        select(ListItem).where(
            ListItem.list_id == list_id,
            func.lower(func.trim(ListItem.name)) == name_key,
        )
    )
    if dupe.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"'{name}' is already on this list")

    result = await session.execute(
        select(ListItem.sort_order).where(ListItem.list_id == list_id)
        .order_by(ListItem.sort_order.desc()).limit(1)
    )
    max_order = result.scalar() or 0

    # Persist the user's photo as the item's image so the list shows the exact
    # snapshot they took. Same storage as the manual photo-attach endpoint.
    image_id = uuid.uuid4().hex
    # Store with the detected MIME, never the client-claimed one.
    session.add(ItemImage(id=image_id, content_type=actual_mime, data=content))

    item = ListItem(
        list_id=list_id,
        added_by_id=current_user.id,
        name=name,
        quantity=qty,
        category_id=None,
        sort_order=max_order + 10,
        image_path=image_id,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)

    response = await enrich_item(item, session)
    await manager.broadcast(list_id, {
        "type": "item_added",
        "item": response.model_dump(mode="json"),
    })
    return response


# IMPORTANT: /reorder MUST be before /{item_id} to avoid route conflict
@router.patch("/reorder", response_model=list[ItemResponse])
# reorder mutates, so it requires edit permission too
async def reorder_items(
    list_id: str,
    req: ReorderItemsRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await get_list_with_access(list_id, current_user, session, require_edit=True)

    # Empty array = no-op. Skip DB + broadcast entirely. (Client now guards
    # this too, but belt-and-suspenders since the old frontend fired empty
    # reorder calls on source zones that emptied out.)
    if not req.item_ids:
        return await get_items_enriched(list_id, session)

    # ONE SELECT covers every id; previously this did N sequential SELECTs
    # which on the 2 GB dev VM put /reorder at ~500-700 ms for modest lists.
    result = await session.execute(
        select(ListItem).where(
            ListItem.id.in_(req.item_ids),
            ListItem.list_id == list_id,
        )
    )
    items_map = {it.id: it for it in result.scalars()}
    for i, iid in enumerate(req.item_ids):
        item = items_map.get(iid)
        if item is not None:
            item.sort_order = (i + 1) * 10
            session.add(item)

    await session.commit()

    await manager.broadcast(list_id, {
        "type": "items_reordered",
        "item_ids": req.item_ids,
    })

    return await get_items_enriched(list_id, session)


@router.patch("/{item_id}", response_model=ItemResponse)
async def update_item(
    list_id: str,
    item_id: str,
    req: UpdateItemRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await get_list_with_access(list_id, current_user, session, require_edit=True)
    result = await session.execute(
        select(ListItem).where(ListItem.id == item_id, ListItem.list_id == list_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    if req.name is not None:
        new_key = req.name.strip().lower()
        current_key = (item.name or "").strip().lower()
        if new_key != current_key:
            dupe = await session.execute(
                select(ListItem).where(
                    ListItem.list_id == list_id,
                    ListItem.id != item.id,
                    func.lower(func.trim(ListItem.name)) == new_key,
                )
            )
            if dupe.scalar_one_or_none():
                raise HTTPException(
                    status_code=409,
                    detail=f"'{req.name}' is already on this list",
                )
        item.name = req.name
    if req.quantity is not None:
        item.quantity = req.quantity
    if req.checked is not None:
        item.checked = req.checked
    if req.category_id is not None:
        item.category_id = req.category_id if req.category_id != "" else None
    if req.sort_order is not None:
        item.sort_order = req.sort_order
    item.updated_at = datetime.now(timezone.utc)

    session.add(item)
    await session.commit()
    await session.refresh(item)

    response = await enrich_item(item, session)

    await manager.broadcast(list_id, {
        "type": "item_updated",
        "item": response.model_dump(mode="json"),
    })

    return response


@router.patch("/{item_id}/check", response_model=ItemResponse)
async def toggle_check(
    list_id: str,
    item_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await get_list_with_access(list_id, current_user, session, require_edit=True)
    result = await session.execute(
        select(ListItem).where(ListItem.id == item_id, ListItem.list_id == list_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    item.checked = not item.checked
    item.updated_at = datetime.now(timezone.utc)
    session.add(item)
    await session.commit()
    await session.refresh(item)

    response = await enrich_item(item, session)

    await manager.broadcast(list_id, {
        "type": "item_checked",
        "item_id": item.id,
        "checked": item.checked,
        "user": {"id": current_user.id, "display_name": current_user.display_name},
    })

    return response


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    list_id: str,
    item_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await get_list_with_access(list_id, current_user, session, require_edit=True)
    result = await session.execute(
        select(ListItem).where(ListItem.id == item_id, ListItem.list_id == list_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    await session.delete(item)
    await session.commit()

    await manager.broadcast(list_id, {
        "type": "item_removed",
        "item_id": item_id,
        "user": {"id": current_user.id, "display_name": current_user.display_name},
    })


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def clear_all_items(
    list_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Delete all items from a list (keeps categories)."""
    await get_list_with_access(list_id, current_user, session, require_edit=True)
    result = await session.execute(
        select(ListItem).where(ListItem.list_id == list_id)
    )
    items = result.scalars().all()
    for item in items:
        await session.delete(item)
    await session.commit()

    await manager.broadcast(list_id, {
        "type": "items_cleared",
        "user": {"id": current_user.id, "display_name": current_user.display_name},
    })
