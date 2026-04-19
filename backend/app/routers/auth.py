from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.database import get_session
from app.core.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    generate_reset_token, hash_reset_token,
    decode_token,
)
from app.core.deps import get_current_user
from app.core.ratelimit import limiter
from app.models.user import User, PasswordResetToken
from app.models.sorting_hint import SortingHint
from app.schemas.auth import (
    RegisterRequest, LoginRequest,
    ForgotPasswordRequest, ResetPasswordRequest,
    UpdateProfileRequest, TokenResponse, UserResponse,
)
from app.services.email_service import send_password_reset_email
from app.core.palette import random_user_color

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("6/minute")
async def register(request: Request, req: RegisterRequest, session: AsyncSession = Depends(get_session)):
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


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(token: str, session: AsyncSession = Depends(get_session)):
    try:
        payload = decode_token(token)
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
