import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.database import get_session
from app.core.deps import get_current_user
from app.core.image_validation import validate_image
from app.core.security import signed_image_url
from app.models.user import User
from app.models.bonus_card import BonusCard
from app.models.bonus_card_share import BonusCardShare
from app.models.item_image import ItemImage
from app.schemas.bonus_card import (
    CreateBonusCardRequest, UpdateBonusCardRequest, BonusCardResponse,
    BonusCardShareRequest, BonusCardShareResponse,
)

router = APIRouter(prefix="/bonus-cards", tags=["bonus-cards"])

MAX_SIZE = 5 * 1024 * 1024


def to_response(
    card: BonusCard,
    is_owner: bool,
    owner_display_name: Optional[str] = None,
    owner_color: Optional[str] = None,
) -> BonusCardResponse:
    return BonusCardResponse(
        id=card.id,
        name=card.name,
        description=card.description,
        image_url=signed_image_url(card.image_id) if card.image_id else None,
        sort_order=card.sort_order,
        is_owner=is_owner,
        owner_display_name=owner_display_name,
        owner_color=owner_color,
        created_at=card.created_at,
        updated_at=card.updated_at,
    )


async def _get_card_with_access(
    card_id: str, user: User, session: AsyncSession, require_owner: bool = False
) -> tuple[BonusCard, bool]:
    """Return (card, is_owner). 404 if user has no access."""
    result = await session.execute(
        select(BonusCard).where(BonusCard.id == card_id)
    )
    card = result.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="Bonus card not found")
    if card.user_id == user.id:
        return card, True
    if require_owner:
        raise HTTPException(status_code=403, detail="Only the card owner can perform this action")
    share_result = await session.execute(
        select(BonusCardShare).where(
            BonusCardShare.card_id == card_id, BonusCardShare.user_id == user.id
        )
    )
    if not share_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Bonus card not found")
    return card, False


@router.get("", response_model=list[BonusCardResponse])
async def list_bonus_cards(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    owned_result = await session.execute(
        select(BonusCard).where(BonusCard.user_id == current_user.id)
        .order_by(BonusCard.sort_order, BonusCard.created_at)
    )
    owned = owned_result.scalars().all()

    shared_result = await session.execute(
        select(BonusCard, User.display_name, User.color)
        .join(BonusCardShare, BonusCardShare.card_id == BonusCard.id)
        .join(User, User.id == BonusCard.user_id)
        .where(BonusCardShare.user_id == current_user.id)
        .order_by(BonusCard.sort_order, BonusCard.created_at)
    )
    shared = shared_result.all()

    response = [
        to_response(c, True, current_user.display_name, current_user.color) for c in owned
    ]
    for card, owner_name, owner_color in shared:
        response.append(to_response(card, False, owner_name, owner_color))
    return response


@router.post("", response_model=BonusCardResponse, status_code=status.HTTP_201_CREATED)
async def create_bonus_card(
    req: CreateBonusCardRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(BonusCard.sort_order).where(BonusCard.user_id == current_user.id)
        .order_by(BonusCard.sort_order.desc()).limit(1)
    )
    last = result.scalar_one_or_none() or 0
    card = BonusCard(
        user_id=current_user.id,
        name=req.name,
        description=req.description,
        sort_order=last + 1,
    )
    session.add(card)
    await session.commit()
    await session.refresh(card)
    return to_response(card, True, current_user.display_name, current_user.color)


@router.patch("/{card_id}", response_model=BonusCardResponse)
async def update_bonus_card(
    card_id: str,
    req: UpdateBonusCardRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    card, _ = await _get_card_with_access(card_id, current_user, session, require_owner=True)
    if req.name is not None:
        card.name = req.name
    if req.description is not None:
        card.description = req.description or None
    card.updated_at = datetime.now(timezone.utc)
    session.add(card)
    await session.commit()
    await session.refresh(card)
    return to_response(card, True, current_user.display_name, current_user.color)


@router.delete("/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bonus_card(
    card_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    card, _ = await _get_card_with_access(card_id, current_user, session, require_owner=True)
    if card.image_id:
        img_result = await session.execute(
            select(ItemImage).where(ItemImage.id == card.image_id)
        )
        img = img_result.scalar_one_or_none()
        if img:
            await session.delete(img)
    # Deleting the card cascades nothing automatically; remove share rows first.
    share_rows = await session.execute(
        select(BonusCardShare).where(BonusCardShare.card_id == card_id)
    )
    for share in share_rows.scalars().all():
        await session.delete(share)
    await session.delete(card)
    await session.commit()


@router.post("/{card_id}/image", response_model=BonusCardResponse)
async def upload_bonus_card_image(
    card_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    card, _ = await _get_card_with_access(card_id, current_user, session, require_owner=True)
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="Image too large (max 5MB)")
    # Validate real image bytes — Content-Type header is attacker-controlled.
    actual_mime = validate_image(content)

    if card.image_id:
        old_img = await session.execute(
            select(ItemImage).where(ItemImage.id == card.image_id)
        )
        old = old_img.scalar_one_or_none()
        if old:
            await session.delete(old)

    image_id = uuid.uuid4().hex
    img = ItemImage(id=image_id, content_type=actual_mime, data=content)
    session.add(img)
    card.image_id = image_id
    card.updated_at = datetime.now(timezone.utc)
    session.add(card)
    await session.commit()
    await session.refresh(card)
    return to_response(card, True, current_user.display_name, current_user.color)


@router.delete("/{card_id}/image", response_model=BonusCardResponse)
async def delete_bonus_card_image(
    card_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    card, _ = await _get_card_with_access(card_id, current_user, session, require_owner=True)
    if card.image_id:
        img_result = await session.execute(
            select(ItemImage).where(ItemImage.id == card.image_id)
        )
        img = img_result.scalar_one_or_none()
        if img:
            await session.delete(img)
        card.image_id = None
        card.updated_at = datetime.now(timezone.utc)
        session.add(card)
        await session.commit()
        await session.refresh(card)
    return to_response(card, True, current_user.display_name, current_user.color)


# ---- Sharing ----

@router.get("/{card_id}/shares", response_model=list[BonusCardShareResponse])
async def list_bonus_card_shares(
    card_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await _get_card_with_access(card_id, current_user, session, require_owner=True)
    result = await session.execute(
        select(BonusCardShare, User)
        .join(User, User.id == BonusCardShare.user_id)
        .where(BonusCardShare.card_id == card_id)
    )
    rows = result.all()
    return [
        BonusCardShareResponse(
            id=share.id, card_id=share.card_id, user_id=share.user_id,
            user_email=user.email, user_display_name=user.display_name,
            user_color=user.color,
        )
        for share, user in rows
    ]


@router.post("/{card_id}/shares", response_model=BonusCardShareResponse, status_code=status.HTTP_201_CREATED)
async def share_bonus_card(
    card_id: str,
    req: BonusCardShareRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await _get_card_with_access(card_id, current_user, session, require_owner=True)

    user_result = await session.execute(select(User).where(User.email == req.email))
    target_user = user_result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found with that email")
    if target_user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot share a card with yourself")

    existing = await session.execute(
        select(BonusCardShare).where(
            BonusCardShare.card_id == card_id, BonusCardShare.user_id == target_user.id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Card already shared with this user")

    share = BonusCardShare(card_id=card_id, user_id=target_user.id)
    session.add(share)
    await session.commit()
    await session.refresh(share)

    return BonusCardShareResponse(
        id=share.id, card_id=share.card_id, user_id=share.user_id,
        user_email=target_user.email, user_display_name=target_user.display_name,
        user_color=target_user.color,
    )


@router.delete("/{card_id}/shares/me", status_code=status.HTTP_204_NO_CONTENT)
async def leave_shared_bonus_card(
    card_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Recipient removes their own share. Owner cannot call this."""
    card_result = await session.execute(
        select(BonusCard).where(BonusCard.id == card_id)
    )
    card = card_result.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="Bonus card not found")
    if card.user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Owner cannot leave their own card")
    share_result = await session.execute(
        select(BonusCardShare).where(
            BonusCardShare.card_id == card_id, BonusCardShare.user_id == current_user.id
        )
    )
    share = share_result.scalar_one_or_none()
    if not share:
        raise HTTPException(status_code=404, detail="You are not a recipient of this card")
    await session.delete(share)
    await session.commit()


@router.delete("/{card_id}/shares/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_bonus_card_share(
    card_id: str,
    share_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await _get_card_with_access(card_id, current_user, session, require_owner=True)
    result = await session.execute(
        select(BonusCardShare).where(
            BonusCardShare.id == share_id, BonusCardShare.card_id == card_id
        )
    )
    share = result.scalar_one_or_none()
    if not share:
        raise HTTPException(status_code=404, detail="Share not found")
    await session.delete(share)
    await session.commit()
