from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.database import get_session
from app.core.deps import get_current_user
from app.core.websocket import manager
from app.models.user import User
from app.models.category import Category
from app.models.list_item import ListItem
from app.routers.lists import get_list_with_access
from app.schemas.category import (
    CreateCategoryRequest, UpdateCategoryRequest,
    ReorderCategoriesRequest, CategoryResponse,
)

router = APIRouter(prefix="/lists/{list_id}/categories", tags=["categories"])


@router.get("", response_model=list[CategoryResponse])
async def get_categories(
    list_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await get_list_with_access(list_id, current_user, session)
    result = await session.execute(
        select(Category).where(Category.list_id == list_id)
        .order_by(Category.sort_order, Category.created_at)
    )
    return result.scalars().all()


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    list_id: str,
    req: CreateCategoryRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await get_list_with_access(list_id, current_user, session)

    # Get next sort order
    result = await session.execute(
        select(Category.sort_order).where(Category.list_id == list_id)
        .order_by(Category.sort_order.desc()).limit(1)
    )
    max_order = result.scalar() or 0

    cat = Category(list_id=list_id, name=req.name, sort_order=max_order + 10)
    session.add(cat)
    await session.commit()
    await session.refresh(cat)

    await manager.broadcast(list_id, {
        "type": "category_added",
        "category": {"id": cat.id, "name": cat.name, "sort_order": cat.sort_order},
    }, exclude_user=current_user.id)

    return cat


@router.patch("/{category_id}", response_model=CategoryResponse)
async def update_category(
    list_id: str,
    category_id: str,
    req: UpdateCategoryRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await get_list_with_access(list_id, current_user, session)
    result = await session.execute(
        select(Category).where(Category.id == category_id, Category.list_id == list_id)
    )
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")

    if req.name is not None:
        cat.name = req.name
    if req.sort_order is not None:
        cat.sort_order = req.sort_order

    session.add(cat)
    await session.commit()
    await session.refresh(cat)

    await manager.broadcast(list_id, {
        "type": "category_updated",
        "category": {"id": cat.id, "name": cat.name, "sort_order": cat.sort_order},
    }, exclude_user=current_user.id)

    return cat


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    list_id: str,
    category_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await get_list_with_access(list_id, current_user, session)
    result = await session.execute(
        select(Category).where(Category.id == category_id, Category.list_id == list_id)
    )
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")

    # Unassign items from this category
    items_result = await session.execute(
        select(ListItem).where(ListItem.category_id == category_id)
    )
    for item in items_result.scalars().all():
        item.category_id = None
        session.add(item)

    await session.delete(cat)
    await session.commit()

    await manager.broadcast(list_id, {
        "type": "category_removed",
        "category_id": category_id,
    }, exclude_user=current_user.id)


@router.patch("/reorder", response_model=list[CategoryResponse])
async def reorder_categories(
    list_id: str,
    req: ReorderCategoriesRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await get_list_with_access(list_id, current_user, session)

    for i, cat_id in enumerate(req.category_ids):
        result = await session.execute(
            select(Category).where(Category.id == cat_id, Category.list_id == list_id)
        )
        cat = result.scalar_one_or_none()
        if cat:
            cat.sort_order = (i + 1) * 10
            session.add(cat)

    await session.commit()

    result = await session.execute(
        select(Category).where(Category.list_id == list_id)
        .order_by(Category.sort_order)
    )
    categories = result.scalars().all()

    await manager.broadcast(list_id, {
        "type": "categories_reordered",
        "category_ids": req.category_ids,
    }, exclude_user=current_user.id)

    return categories
