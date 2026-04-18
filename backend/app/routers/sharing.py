from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.database import get_session
from app.core.deps import get_current_user
from app.models.user import User
from app.models.shopping_list import ShoppingList
from app.models.list_share import ListShare
from app.routers.lists import get_list_with_access
from app.schemas.shopping_list import ShareRequest, ShareResponse

router = APIRouter(prefix="/lists/{list_id}/shares", tags=["sharing"])


@router.get("", response_model=list[ShareResponse])
async def get_shares(
    list_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await get_list_with_access(list_id, current_user, session)
    result = await session.execute(
        select(ListShare, User)
        .join(User, User.id == ListShare.user_id)
        .where(ListShare.list_id == list_id)
    )
    shares = result.all()
    return [
        ShareResponse(
            id=share.id, list_id=share.list_id, user_id=share.user_id,
            user_email=user.email, user_display_name=user.display_name,
            user_color=user.color, permission=share.permission,
        )
        for share, user in shares
    ]


@router.post("", response_model=ShareResponse, status_code=status.HTTP_201_CREATED)
async def share_list(
    list_id: str,
    req: ShareRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    lst = await get_list_with_access(list_id, current_user, session, require_owner=True)

    # Find user by email
    user_result = await session.execute(select(User).where(User.email == req.email))
    target_user = user_result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found with that email")
    if target_user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot share a list with yourself")

    # Check if already shared
    existing = await session.execute(
        select(ListShare).where(
            ListShare.list_id == list_id, ListShare.user_id == target_user.id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="List already shared with this user")

    share = ListShare(
        list_id=list_id, user_id=target_user.id, permission=req.permission
    )
    session.add(share)
    await session.commit()
    await session.refresh(share)

    return ShareResponse(
        id=share.id, list_id=share.list_id, user_id=share.user_id,
        user_email=target_user.email, user_display_name=target_user.display_name,
        user_color=target_user.color, permission=share.permission,
    )


@router.delete("/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_share(
    list_id: str,
    share_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    lst = await get_list_with_access(list_id, current_user, session, require_owner=True)
    result = await session.execute(
        select(ListShare).where(ListShare.id == share_id, ListShare.list_id == list_id)
    )
    share = result.scalar_one_or_none()
    if not share:
        raise HTTPException(status_code=404, detail="Share not found")

    await session.delete(share)
    await session.commit()
