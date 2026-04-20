import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import get_settings
from app.core import feature_flags
from app.core.deps import get_current_user
from app.core.palette import random_user_color
from app.core.ratelimit import limiter
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_reset_token,
    hash_password,
    hash_reset_token,
    verify_password,
)
from app.database import get_session
from app.models.account_deletion_token import AccountDeletionToken
from app.models.bonus_card import BonusCard
from app.models.bonus_card_share import BonusCardShare
from app.models.category import Category
from app.models.list_item import ListItem
from app.models.list_share import ListShare
from app.models.shopping_list import ShoppingList
from app.models.sorting_hint import SortingHint
from app.models.user import PasswordResetToken, User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserResponse,
)
from app.services.email_service import (
    send_delete_confirmation_email,
    send_password_reset_email,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("6/minute")
async def register(request: Request, req: RegisterRequest, session: AsyncSession = Depends(get_session)):
    # Admin can toggle self-registration off from the admin UI.
    if not await feature_flags.get_bool(session, "registration_enabled", True):
        raise HTTPException(
            status_code=403,
            detail="User registration is currently disabled. Please ask an administrator to create an account for you.",
        )

    # Check if email already exists
    result = await session.execute(select(User).where(User.email == req.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=req.email,
        password_hash=hash_password(req.password),
        display_name=req.display_name,
        locale=req.locale,
        color=random_user_color(),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit("6/minute")
async def login(request: Request, req: LoginRequest, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


class RefreshRequest(BaseModel):
    token: str = Field(min_length=1, max_length=4096)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    req: RefreshRequest,
    session: AsyncSession = Depends(get_session),
):
    """Refresh with the token supplied in the JSON body. Previously accepted
    as a URL query parameter, which leaked into nginx access logs, Referer
    headers, browser history and error-logging pipelines."""
    try:
        payload = decode_token(req.token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = payload.get("sub")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/forgot-password")
@limiter.limit("2/minute")
async def forgot_password(request: Request, req: ForgotPasswordRequest, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()

    # Always return success to prevent email enumeration
    if not user:
        return {"message": "If the email exists, a reset link has been sent"}

    raw_token, hashed_token = generate_reset_token()
    reset = PasswordResetToken(
        user_id=user.id,
        token_hash=hashed_token,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    session.add(reset)
    await session.commit()

    await send_password_reset_email(user.email, raw_token, user.locale)
    return {"message": "If the email exists, a reset link has been sent"}


@router.post("/reset-password")
async def reset_password(req: ResetPasswordRequest, session: AsyncSession = Depends(get_session)):
    token_hash = hash_reset_token(req.token)
    result = await session.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used == False,
            PasswordResetToken.expires_at > datetime.now(timezone.utc),
        )
    )
    reset_token = result.scalar_one_or_none()
    if not reset_token:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    # Update password
    user_result = await session.execute(select(User).where(User.id == reset_token.user_id))
    user = user_result.scalar_one()
    user.password_hash = hash_password(req.new_password)
    user.updated_at = datetime.now(timezone.utc)

    # Mark token as used
    reset_token.used = True

    session.add(user)
    session.add(reset_token)
    await session.commit()

    return {"message": "Password reset successfully"}


@router.get("/me", response_model=UserResponse)
async def get_profile(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_profile(
    req: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if req.display_name is not None:
        current_user.display_name = req.display_name
    if req.locale is not None:
        current_user.locale = req.locale
    if req.color is not None:
        current_user.color = req.color
        current_user.color_customized = True
    current_user.updated_at = datetime.now(timezone.utc)

    session.add(current_user)
    await session.commit()
    await session.refresh(current_user)
    return current_user


@router.delete("/me/hints")
async def wipe_all_hints(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Delete all sorting hints for the current user across all lists."""
    result = await session.execute(
        select(SortingHint).where(SortingHint.user_id == current_user.id)
    )
    hints = result.scalars().all()
    count = len(hints)
    for hint in hints:
        await session.delete(hint)
    await session.commit()
    return {"message": f"Deleted {count} hints", "deleted": count}


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


@router.post("/me/password")
@limiter.limit("10/hour")
async def change_password(
    request: Request,
    req: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Change the authenticated user's own password. Requires the current
    password to be supplied so a stolen-session attacker can't silently
    hijack the account."""
    if not verify_password(req.current_password, current_user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    if req.new_password == req.current_password:
        raise HTTPException(status_code=400, detail="New password must differ from current password")

    current_user.password_hash = hash_password(req.new_password)
    current_user.updated_at = datetime.now(timezone.utc)
    session.add(current_user)
    await session.commit()
    return {"message": "Password changed"}


# =====================================================================
# Account deletion — two-phase: request code → confirm with code → wipe.
# Security invariants:
#   * both endpoints require a valid JWT (get_current_user), so the
#     user_id being deleted is always the caller's own.
#   * code is a 6-digit number (1e6 keyspace) generated with secrets,
#     stored as SHA-256 hash, compared in constant time.
#   * per-IP rate limit on both endpoints; per-user attempt counter on
#     the token itself (5 wrong tries burns the token).
#   * expiry is 15 minutes; requesting a new code invalidates every
#     previously issued unused token for that user.
#   * cascade delete runs inside the same transaction as the token
#     consumption, so a partial failure cannot leave us in a state
#     where the code is "used" but data still exists.
# =====================================================================


def _hash_code(code: str) -> str:
    """Keyed HMAC-SHA256 of the deletion code.

    Uses the server SECRET_KEY as the HMAC key so a leaked
    account_deletion_tokens table is not rainbow-crackable (unkeyed SHA-256
    over a 6-digit space precomputes to ~1MB in milliseconds).
    """
    key = get_settings().secret_key.encode("utf-8")
    return hmac.new(key, code.encode("utf-8"), hashlib.sha256).hexdigest()


def _generate_deletion_code() -> str:
    # 6 digits; zero-padded. secrets.randbelow is cryptographically secure.
    return f"{secrets.randbelow(1_000_000):06d}"


class ConfirmDeleteRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^[0-9]{6}$")
    # Require the current password alongside the email code. Defense in depth:
    # an attacker holding a stolen access token AND the victim's inbox still
    # needs the password to actually delete. Matches the change-password path.
    current_password: str = Field(min_length=1, max_length=128)


@router.post("/me/delete/request")
@limiter.limit("3/hour")
async def request_account_deletion(
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Generate a one-time 6-digit code and email it to the current user.

    Invalidates any previously issued unused deletion tokens for this user
    so that an attacker cannot stockpile codes by repeatedly calling this
    endpoint. Per-user cooldown blocks email-flood abuse from a stolen JWT
    across rotating IPs (which would defeat the per-IP slowapi limiter).
    """
    # Per-user cooldown: reject if a previous code was issued < 60 s ago.
    latest_res = await session.execute(
        select(AccountDeletionToken)
        .where(AccountDeletionToken.user_id == current_user.id)
        .order_by(AccountDeletionToken.created_at.desc())
        .limit(1)
    )
    latest = latest_res.scalars().first()
    if latest is not None:
        latest_at = latest.created_at
        if latest_at.tzinfo is None:
            latest_at = latest_at.replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc) - latest_at) < timedelta(seconds=60):
            raise HTTPException(
                status_code=429,
                detail="Please wait before requesting another code.",
            )

    # Invalidate previous unused tokens for this user so only the newest
    # code is ever valid.
    result = await session.execute(
        select(AccountDeletionToken).where(
            AccountDeletionToken.user_id == current_user.id,
            AccountDeletionToken.used == False,  # noqa: E712
        )
    )
    for prev in result.scalars().all():
        prev.used = True
        session.add(prev)

    code = _generate_deletion_code()
    token = AccountDeletionToken(
        user_id=current_user.id,
        code_hash=_hash_code(code),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    session.add(token)
    await session.commit()

    await send_delete_confirmation_email(current_user.email, code, current_user.locale)
    return {"message": "Confirmation code sent to your email"}


@router.post("/me/delete/confirm")
@limiter.limit("10/hour")
async def confirm_account_deletion(
    request: Request,
    req: ConfirmDeleteRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Verify the emailed code and permanently delete the user's account.

    On success: cascades lists, items, categories, shares (both directions),
    bonus cards, hints, orphan images, and finally the user row itself.
    Returns 204 No Content on success — caller should clear local tokens
    and redirect to login.
    """
    # Find the most recent unused, unexpired token for this user.
    result = await session.execute(
        select(AccountDeletionToken)
        .where(
            AccountDeletionToken.user_id == current_user.id,
            AccountDeletionToken.used == False,  # noqa: E712
            AccountDeletionToken.expires_at > datetime.now(timezone.utc),
        )
        .order_by(AccountDeletionToken.created_at.desc())
    )
    token = result.scalars().first()
    if token is None:
        raise HTTPException(
            status_code=400,
            detail="No active deletion code. Please request a new one.",
        )

    if token.attempts >= 5:
        token.used = True
        session.add(token)
        await session.commit()
        raise HTTPException(
            status_code=429,
            detail="Too many incorrect attempts. Please request a new code.",
        )

    token.attempts += 1
    session.add(token)

    # Constant-time compare on the HMAC digests
    if not hmac.compare_digest(token.code_hash, _hash_code(req.code)):
        await session.commit()
        raise HTTPException(status_code=400, detail="Incorrect code")

    # Defense in depth: even with a valid email code, require the current
    # password so a stolen-session attacker can't nuke the account.
    if not verify_password(req.current_password, current_user.password_hash):
        await session.commit()
        raise HTTPException(status_code=401, detail="Incorrect password")

    # Code + password valid — consume token and cascade-delete everything
    token.used = True
    session.add(token)

    user_id = current_user.id
    user_email = current_user.email
    try:
        await _cascade_delete_user(session, user_id)
    except Exception:
        # Let the exception bubble so the session is rolled back by the framework.
        logger.exception("Cascade delete failed for user %s", user_id)
        raise HTTPException(
            status_code=500,
            detail="Account deletion failed. Please contact support.",
        )

    logger.info("Account deleted: user_id=%s email=%s", user_id, user_email)
    return {"message": "Account deleted"}


async def _cascade_delete_user(session: AsyncSession, user_id: str):
    """Delete every row belonging to ``user_id`` in FK-safe order.

    Called ONLY from ``confirm_account_deletion`` after a valid code. The
    caller owns the transaction boundary; we do a single commit at the
    end so any SQL-level failure rolls the whole thing back.
    """

    # 1) Tokens tied to this user (password-reset + every deletion token
    #    including the one we are consuming — the current session-local
    #    token object is already being committed, but we purge the row
    #    for good measure along with every sibling)
    await session.execute(
        delete(PasswordResetToken).where(PasswordResetToken.user_id == user_id)
    )
    await session.execute(
        delete(AccountDeletionToken).where(AccountDeletionToken.user_id == user_id)
    )

    # 2) Shares where THIS user is the grantee (= lists/cards shared
    #    to us by someone else). Owners are unaffected.
    await session.execute(delete(ListShare).where(ListShare.user_id == user_id))
    await session.execute(delete(BonusCardShare).where(BonusCardShare.user_id == user_id))

    # 3) Sorting hints authored by this user (across any list, including
    #    ones owned by other users that were shared with us — those hints
    #    are personal, so we wipe them).
    await session.execute(delete(SortingHint).where(SortingHint.user_id == user_id))

    # 4) Items this user ADDED to lists owned by OTHER users (shared lists).
    #    list_items.added_by_id is a NOT-NULL FK to users.id; leaving these
    #    rows behind would either dangle (SQLite dev) or fail FK enforcement
    #    (Postgres). Simplest correct fix: delete them. Co-users of the
    #    shared list lose the items this user contributed, which is the
    #    expected semantic when a contributor deletes their account.
    await session.execute(
        delete(ListItem).where(ListItem.added_by_id == user_id)
    )

    # 5) Lists OWNED by this user: cascade children, then the list itself.
    owned_lists_res = await session.execute(
        select(ShoppingList.id).where(ShoppingList.owner_id == user_id)
    )
    owned_list_ids = [row[0] for row in owned_lists_res.all()]
    if owned_list_ids:
        # Any remaining items on our owned lists (would have been caught by
        # step 4 already if we added them, but others may have contributed)
        await session.execute(
            delete(ListItem).where(ListItem.list_id.in_(owned_list_ids))
        )
        await session.execute(
            delete(Category).where(Category.list_id.in_(owned_list_ids))
        )
        # Purge ANY other user's shares / hints on these lists too
        await session.execute(
            delete(ListShare).where(ListShare.list_id.in_(owned_list_ids))
        )
        await session.execute(
            delete(SortingHint).where(SortingHint.list_id.in_(owned_list_ids))
        )
        await session.execute(
            delete(ShoppingList).where(ShoppingList.id.in_(owned_list_ids))
        )

    # 6) Bonus cards OWNED by this user: cascade shares, then the card.
    owned_cards_res = await session.execute(
        select(BonusCard.id).where(BonusCard.user_id == user_id)
    )
    owned_card_ids = [row[0] for row in owned_cards_res.all()]
    if owned_card_ids:
        await session.execute(
            delete(BonusCardShare).where(BonusCardShare.card_id.in_(owned_card_ids))
        )
        await session.execute(
            delete(BonusCard).where(BonusCard.id.in_(owned_card_ids))
        )

    # 7) Finally, the user row.
    await session.execute(delete(User).where(User.id == user_id))

    # 8) Orphan-sweep image BLOBs. Done as a global cleanup (cheap since
    #    it's a subquery on indexed FK columns) — safe because we only
    #    delete images no surviving item_or_card references.
    await session.execute(
        text(
            """
            DELETE FROM item_images
            WHERE id NOT IN (
                SELECT image_path FROM list_items WHERE image_path IS NOT NULL
                UNION
                SELECT image_id   FROM bonus_cards WHERE image_id   IS NOT NULL
            )
            """
        )
    )

    await session.commit()
