from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, func, or_

from app.database import get_session
from app.core.deps import get_current_user
from app.models.user import User
from app.models.shopping_list import ShoppingList
from app.models.list_share import ListShare
from app.models.list_item import ListItem
from app.schemas.shopping_list import (
    CreateListRequest, UpdateListRequest, ListResponse,
)

router = APIRouter(prefix="/lists", tags=["lists"])


async def get_list_with_access(
    list_id: str, user: User, session: AsyncSession, require_owner: bool = False
) -> ShoppingList:
    """Get a list and verify user has access."""
    result = await session.execute(select(ShoppingList).where(ShoppingList.id == list_id))
    lst = result.scalar_one_or_none()
    if not lst:
        raise HTTPException(status_code=404, detail="List not found")

    if lst.owner_id == user.id:
        return lst

    if require_owner:
        raise HTTPException(status_code=403, detail="Only the list owner can perform this action")

    # Check shared access
    share_result = await session.execute(
        select(ListShare).where(ListShare.list_id == list_id, ListShare.user_id == user.id)
    )
    if not share_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="List not found")

    return lst


@router.get("", response_model=list[ListResponse])
async def get_lists(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    # Get owned lists
    owned_result = await session.execute(
        select(ShoppingList).where(ShoppingList.owner_id == current_user.id)
        .order_by(ShoppingList.sort_order, ShoppingList.created_at.desc())
    )
    owned_lists = owned_result.scalars().all()

    # Get shared lists
    shared_result = await session.execute(
        select(ShoppingList, ListShare.permission)
        .join(ListShare, ListShare.list_id == ShoppingList.id)
        .where(ListShare.user_id == current_user.id)
        .order_by(ShoppingList.sort_order, ShoppingList.created_at.desc())
    )
    shared_lists = shared_result.all()

    # Count items per list
    all_list_ids = [l.id for l in owned_lists] + [row[0].id for row in shared_lists]
    item_counts = {}
    if all_list_ids:
        count_result = await session.execute(
            select(ListItem.list_id, func.count(ListItem.id))
            .where(ListItem.list_id.in_(all_list_ids))
            .group_by(ListItem.list_id)
        )
        item_counts = dict(count_result.all())

    response = []
    for lst in owned_lists:
        response.append(ListResponse(
            id=lst.id, owner_id=lst.owner_id, name=lst.name,
            sort_order=lst.sort_order, created_at=lst.created_at,
            updated_at=lst.updated_at, is_owner=True,
            item_count=item_counts.get(lst.id, 0),
        ))
    for lst, permission in shared_lists:
        response.append(ListResponse(
            id=lst.id, owner_id=lst.owner_id, name=lst.name,
            sort_order=lst.sort_order, created_at=lst.created_at,
            updated_at=lst.updated_at, is_owner=False, permission=permission,
            item_count=item_counts.get(lst.id, 0),
        ))

    return response


@router.post("", response_model=ListResponse, status_code=status.HTTP_201_CREATED)
async def create_list(
    req: CreateListRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    lst = ShoppingList(owner_id=current_user.id, name=req.name)
    session.add(lst)
    await session.commit()
    await session.refresh(lst)
    return ListResponse(
        id=lst.id, owner_id=lst.owner_id, name=lst.name,
        sort_order=lst.sort_order, created_at=lst.created_at,
        updated_at=lst.updated_at, is_owner=True, item_count=0,
    )


@router.get("/{list_id}", response_model=ListResponse)
async def get_list(
    list_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    lst = await get_list_with_access(list_id, current_user, session)
    count_result = await session.execute(
        select(func.count(ListItem.id)).where(ListItem.list_id == list_id)
    )
    item_count = count_result.scalar() or 0

    return ListResponse(
        id=lst.id, owner_id=lst.owner_id, name=lst.name,
        sort_order=lst.sort_order, created_at=lst.created_at,
        updated_at=lst.updated_at, is_owner=(lst.owner_id == current_user.id),
        item_count=item_count,
    )


@router.patch("/{list_id}", response_model=ListResponse)
async def update_list(
    list_id: str,
    req: UpdateListRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    lst = await get_list_with_access(list_id, current_user, session)
    if req.name is not None:
        lst.name = req.name
    if req.sort_order is not None:
        lst.sort_order = req.sort_order
    lst.updated_at = datetime.now(timezone.utc)
    session.add(lst)
    await session.commit()
    await session.refresh(lst)
    return ListResponse(
        id=lst.id, owner_id=lst.owner_id, name=lst.name,
        sort_order=lst.sort_order, created_at=lst.created_at,
        updated_at=lst.updated_at, is_owner=(lst.owner_id == current_user.id),
    )


@router.delete("/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_list(
    list_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    lst = await get_list_with_access(list_id, current_user, session, require_owner=True)
    await session.delete(lst)
    await session.commit()
