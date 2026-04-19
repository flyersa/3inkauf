from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.database import get_session
from app.config import get_settings
from app.core import runtime_config
from app.core.deps import get_current_user
from app.models.user import User
from app.models.list_item import ListItem
from app.models.category import Category
from app.models.sorting_hint import SortingHint
from app.routers.lists import get_list_with_access
from app.services.ml_service import ml_service
from app.schemas.list_item import AutoSortResponse, AutoSortProposal, ApplyAutoSortRequest

router = APIRouter(prefix="/lists/{list_id}", tags=["ml"])


@router.post("/auto-sort", response_model=AutoSortResponse)
async def auto_sort(
    list_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await get_list_with_access(list_id, current_user, session)

    settings = get_settings()
    use_advanced = bool(settings.ollama_url)

    if not use_advanced and not ml_service.model:
        raise HTTPException(status_code=503, detail="ML model not loaded")

    # Only uncategorized items
    items_result = await session.execute(
        select(ListItem).where(ListItem.list_id == list_id, ListItem.category_id == None)
    )
    items = items_result.scalars().all()

    cats_result = await session.execute(
        select(Category).where(Category.list_id == list_id)
    )
    categories = cats_result.scalars().all()

    if not items or not categories:
        return AutoSortResponse(assignments=[])

    # Load hints for THIS list only
    hints_result = await session.execute(
        select(SortingHint).where(
            SortingHint.user_id == current_user.id,
            SortingHint.list_id == list_id,
        )
    )
    hints = {h.item_name: h.category_name for h in hints_result.scalars().all()}

    item_dicts = [{"id": i.id, "name": i.name} for i in items]
    cat_dicts = [{"id": c.id, "name": c.name} for c in categories]

    if use_advanced:
        assignments = ml_service.auto_sort_advanced(
            item_dicts, cat_dicts, hints=hints,
            ollama_url=settings.ollama_url,
            ollama_model=runtime_config.get_model(),
        )
    else:
        assignments = ml_service.auto_sort_simple(item_dicts, cat_dicts, hints=hints)

    return AutoSortResponse(
        assignments=[
            AutoSortProposal(
                item_id=a["item_id"],
                item_name=a["item_name"],
                category_id=a["category_id"],
                category_name=a["category_name"],
                confidence=a["confidence"],
            )
            for a in assignments
        ]
    )


@router.post("/auto-sort/apply")
async def apply_auto_sort(
    list_id: str,
    req: ApplyAutoSortRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await get_list_with_access(list_id, current_user, session, require_edit=True)

    # Validate that every category_id the client wants to assign actually
    # belongs to THIS list. Without this, an attacker can cross-assign items
    # to categories owned by a different list (IDOR-class bug).
    requested_cat_ids = {
        a.get("category_id") for a in req.assignments if a.get("category_id")
    }
    valid_cat_ids: set[str] = set()
    if requested_cat_ids:
        cat_rows = await session.execute(
            select(Category.id).where(
                Category.list_id == list_id,
                Category.id.in_(requested_cat_ids),
            )
        )
        valid_cat_ids = {row[0] for row in cat_rows.all()}
        invalid = requested_cat_ids - valid_cat_ids
        if invalid:
            raise HTTPException(
                status_code=400,
                detail="One or more category IDs do not belong to this list",
            )

    updated = 0
    for assignment in req.assignments:
        item_id = assignment.get("item_id")
        category_id = assignment.get("category_id")
        if not item_id or not category_id:
            continue
        # Redundant safety net — category_id was already verified above.
        if category_id not in valid_cat_ids:
            continue
        result = await session.execute(
            select(ListItem).where(ListItem.id == item_id, ListItem.list_id == list_id)
        )
        item = result.scalar_one_or_none()
        if item:
            item.category_id = category_id
            session.add(item)
            updated += 1

    await session.commit()
    return {"message": f"Updated {updated} items", "updated": updated}


@router.post("/save-hints")
async def save_sorting_hints(
    list_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Save current item->category mappings as hints for THIS list."""
    await get_list_with_access(list_id, current_user, session)

    result = await session.execute(
        select(ListItem, Category)
        .join(Category, Category.id == ListItem.category_id)
        .where(ListItem.list_id == list_id, ListItem.category_id != None)
    )
    pairs = result.all()

    saved = 0
    for item, category in pairs:
        item_name_lower = item.name.lower().strip()
        existing = await session.execute(
            select(SortingHint).where(
                SortingHint.user_id == current_user.id,
                SortingHint.list_id == list_id,
                SortingHint.item_name == item_name_lower,
            )
        )
        hint = existing.scalar_one_or_none()
        if hint:
            hint.category_name = category.name
            session.add(hint)
        else:
            hint = SortingHint(
                user_id=current_user.id,
                list_id=list_id,
                item_name=item_name_lower,
                category_name=category.name,
            )
            session.add(hint)
        saved += 1

    await session.commit()
    return {"message": f"Saved {saved} sorting hints", "saved": saved}
