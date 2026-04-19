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
    list_id: str,
    user: User,
    session: AsyncSession,
    require_owner: bool = False,
    require_edit: bool = False,
) -> ShoppingList:
    """Get a list and verify user has access.

    - ``require_owner=True``: reject non-owners with 403 (used for share management,
      delete-list, etc.).
    - ``require_edit=True``: reject view-only shared users with 403 (used for any
      endpoint that mutates list content: items, categories, rename, reorder).
    """
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
    share = share_result.scalar_one_or_none()
    if not share:
        raise HTTPException(status_code=404, detail="List not found")

    if require_edit and (share.permission or "").lower() != "edit":
        raise HTTPException(
            status_code=403,
            detail="You only have view access to this list",
        )

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

    # Get shared lists (joined with owner User so we can expose owner name/color)
    shared_result = await session.execute(
        select(ShoppingList, ListShare.permission, User.display_name, User.color)
        .join(ListShare, ListShare.list_id == ShoppingList.id)
        .join(User, User.id == ShoppingList.owner_id)
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
            id=lst.id, owner_id=lst.owner_id,
            owner_display_name=current_user.display_name,
            owner_color=current_user.color,
            name=lst.name,
            sort_order=lst.sort_order, created_at=lst.created_at,
            updated_at=lst.updated_at, is_owner=True,
            item_count=item_counts.get(lst.id, 0),
        ))
    for lst, permission, owner_name, owner_color in shared_lists:
        response.append(ListResponse(
            id=lst.id, owner_id=lst.owner_id,
            owner_display_name=owner_name,
            owner_color=owner_color,
            name=lst.name,
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
    # Reject duplicate name among this user's OWNED lists (case-insensitive, trimmed).
    # Shared-in lists don't count — those belong to other users.
    name_key = (req.name or "").strip().lower()
    dupe = await session.execute(
        select(ShoppingList).where(
            ShoppingList.owner_id == current_user.id,
            func.lower(func.trim(ShoppingList.name)) == name_key,
        )
    )
    if dupe.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"You already have a list named '{req.name}'",
        )

    lst = ShoppingList(owner_id=current_user.id, name=req.name)
    session.add(lst)
    await session.commit()
    await session.refresh(lst)
    return ListResponse(
        id=lst.id, owner_id=lst.owner_id,
        owner_display_name=current_user.display_name,
        owner_color=current_user.color,
        name=lst.name,
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

    if lst.owner_id == current_user.id:
        owner_name, owner_color = current_user.display_name, current_user.color
    else:
        owner_result = await session.execute(select(User).where(User.id == lst.owner_id))
        owner = owner_result.scalar_one()
        owner_name, owner_color = owner.display_name, owner.color

    return ListResponse(
        id=lst.id, owner_id=lst.owner_id,
        owner_display_name=owner_name, owner_color=owner_color,
        name=lst.name,
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
    lst = await get_list_with_access(list_id, current_user, session, require_edit=True)
    if req.name is not None:
        new_key = req.name.strip().lower()
        current_key = (lst.name or "").strip().lower()
        if new_key != current_key:
            dupe = await session.execute(
                select(ShoppingList).where(
                    ShoppingList.owner_id == lst.owner_id,
                    ShoppingList.id != lst.id,
                    func.lower(func.trim(ShoppingList.name)) == new_key,
                )
            )
            if dupe.scalar_one_or_none():
                raise HTTPException(
                    status_code=409,
                    detail=f"You already have a list named '{req.name}'",
                )
        lst.name = req.name
    if req.sort_order is not None:
        lst.sort_order = req.sort_order
    lst.updated_at = datetime.now(timezone.utc)
    session.add(lst)
    await session.commit()
    await session.refresh(lst)

    if lst.owner_id == current_user.id:
        owner_name, owner_color = current_user.display_name, current_user.color
    else:
        owner_result = await session.execute(select(User).where(User.id == lst.owner_id))
        owner = owner_result.scalar_one()
        owner_name, owner_color = owner.display_name, owner.color

    return ListResponse(
        id=lst.id, owner_id=lst.owner_id,
        owner_display_name=owner_name, owner_color=owner_color,
        name=lst.name,
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
