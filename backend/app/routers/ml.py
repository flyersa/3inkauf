from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.database import get_session
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

    if not ml_service.model:
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

    # Load user's sorting hints
    hints_result = await session.execute(
        select(SortingHint).where(SortingHint.user_id == current_user.id)
    )
    hints_list = hints_result.scalars().all()
    hints = {h.item_name: h.category_name for h in hints_list}

    item_dicts = [{"id": i.id, "name": i.name} for i in items]
    cat_dicts = [{"id": c.id, "name": c.name} for c in categories]

    assignments = ml_service.auto_sort(item_dicts, cat_dicts, hints=hints)

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
    await get_list_with_access(list_id, current_user, session)

    updated = 0
    for assignment in req.assignments:
        item_id = assignment.get("item_id")
        category_id = assignment.get("category_id")
        if not item_id or not category_id:
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
    """Save current item->category mappings as sorting hints for future auto-sort."""
    await get_list_with_access(list_id, current_user, session)

    # Get all categorized items with their category names
    result = await session.execute(
        select(ListItem, Category)
        .join(Category, Category.id == ListItem.category_id)
        .where(ListItem.list_id == list_id, ListItem.category_id != None)
    )
    pairs = result.all()

    saved = 0
    for item, category in pairs:
        item_name_lower = item.name.lower().strip()

        # Upsert: check if hint exists, update or create
        existing = await session.execute(
            select(SortingHint).where(
                SortingHint.user_id == current_user.id,
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
                item_name=item_name_lower,
                category_name=category.name,
            )
            session.add(hint)
        saved += 1

    await session.commit()
    return {"message": f"Saved {saved} sorting hints", "saved": saved}
