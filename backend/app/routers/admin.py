"""Admin endpoints. All require HTTP Basic auth (ADMIN_USERNAME/PASSWORD)."""
from __future__ import annotations

import logging
import secrets
import string
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import delete, func, select

from app.core import runtime_config
from app.core.admin_auth import get_admin
from app.core.security import hash_password
from app.core.websocket import manager as ws_manager
from app.database import get_session
from app.models.bonus_card import BonusCard
from app.models.bonus_card_share import BonusCardShare
from app.models.category import Category
from app.models.list_item import ListItem
from app.models.list_share import ListShare
from app.models.shopping_list import ShoppingList
from app.models.sorting_hint import SortingHint
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(get_admin)])


# ---------- Stats ----------

@router.get("/stats")
async def stats(session: AsyncSession = Depends(get_session)):
    users_total = (await session.execute(select(func.count()).select_from(User))).scalar_one()
    lists_total = (await session.execute(select(func.count()).select_from(ShoppingList))).scalar_one()
    items_total = (await session.execute(select(func.count()).select_from(ListItem))).scalar_one()
    bonus_cards_total = (await session.execute(select(func.count()).select_from(BonusCard))).scalar_one()
    active_user_ids: set[str] = set()
    for conns in ws_manager.active_connections.values():
        active_user_ids.update(conns.keys())
    return {
        "users_total": users_total,
        "lists_total": lists_total,
        "items_total": items_total,
        "bonus_cards_total": bonus_cards_total,
        "active_users_now": len(active_user_ids),
        "active_list_rooms": len(ws_manager.active_connections),
    }


# ---------- Users ----------

class UserEditRequest(BaseModel):
    display_name: Optional[str] = None
    email: Optional[EmailStr] = None
    locale: Optional[str] = None
    color: Optional[str] = None


class ResetPasswordRequest(BaseModel):
    send_email: bool = False


def _serialize_user(u: User) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "display_name": u.display_name,
        "color": u.color,
        "color_customized": u.color_customized,
        "locale": u.locale,
        "created_at": u.created_at.isoformat() if u.created_at else None,
        "updated_at": u.updated_at.isoformat() if u.updated_at else None,
    }


@router.get("/users")
async def list_users(session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(User).order_by(User.created_at.desc()))).scalars().all()
    return [_serialize_user(u) for u in rows]


@router.get("/users/{user_id}")
async def get_user(user_id: str, session: AsyncSession = Depends(get_session)):
    u = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not u:
        raise HTTPException(404, "User not found")
    return _serialize_user(u)


@router.patch("/users/{user_id}")
async def edit_user(
    user_id: str,
    req: UserEditRequest,
    session: AsyncSession = Depends(get_session),
):
    u = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not u:
        raise HTTPException(404, "User not found")
    if req.display_name is not None:
        name = req.display_name.strip()
        if not name:
            raise HTTPException(400, "display_name must not be empty")
        u.display_name = name
    if req.email is not None:
        new_email = req.email.lower().strip()
        if new_email != u.email:
            existing = (await session.execute(select(User).where(User.email == new_email))).scalar_one_or_none()
            if existing:
                raise HTTPException(409, "Email already in use")
            u.email = new_email
    if req.locale is not None:
        u.locale = req.locale.strip() or u.locale
    if req.color is not None:
        u.color = req.color.strip()
        u.color_customized = True
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return _serialize_user(u)


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, session: AsyncSession = Depends(get_session)):
    u = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not u:
        raise HTTPException(404, "User not found")

    # Shares involving this user as recipient
    await session.execute(delete(ListShare).where(ListShare.user_id == user_id))
    await session.execute(delete(BonusCardShare).where(BonusCardShare.user_id == user_id))
    await session.execute(delete(SortingHint).where(SortingHint.user_id == user_id))

    # Lists owned by user: drop their items, categories, and shares.
    owned_lists = (await session.execute(select(ShoppingList).where(ShoppingList.owner_id == user_id))).scalars().all()
    for lst in owned_lists:
        await session.execute(delete(ListItem).where(ListItem.list_id == lst.id))
        await session.execute(delete(Category).where(Category.list_id == lst.id))
        await session.execute(delete(ListShare).where(ListShare.list_id == lst.id))
        await session.delete(lst)

    # Bonus cards owned by user: drop their shares too.
    owned_cards = (await session.execute(select(BonusCard).where(BonusCard.user_id == user_id))).scalars().all()
    for card in owned_cards:
        await session.execute(delete(BonusCardShare).where(BonusCardShare.card_id == card.id))
        await session.delete(card)

    await session.delete(u)
    await session.commit()
    return {"ok": True}


def _generate_password(length: int = 14) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    specials = "!@#$%^&*"
    for _ in range(20):
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.islower() for c in pw)
            and any(c.isupper() for c in pw)
            and any(c.isdigit() for c in pw)
            and any(c in specials for c in pw)
        ):
            return pw
    # Fallback — extremely unlikely to reach this
    return pw


async def _send_admin_password_email(email: str, new_password: str, locale: str) -> None:
    # Lazy import: email service reads SMTP settings on import
    import aiosmtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    from app.config import get_settings

    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_user:
        raise RuntimeError("SMTP not configured")

    if locale.startswith("de"):
        subject = "Dein Passwort wurde zurückgesetzt"
        html = f"""
        <html><body style="font-family: sans-serif; padding: 20px;">
        <h2>Neues Passwort</h2>
        <p>Ein Administrator hat dein Passwort zurückgesetzt.</p>
        <p>Dein neues Passwort lautet:</p>
        <p style="font-family: monospace; font-size: 18px; background: #f4f4f4; padding: 12px; border-radius: 6px; display: inline-block;">{new_password}</p>
        <p>Bitte melde dich mit diesem Passwort an und ändere es anschließend in deinen Einstellungen.</p>
        </body></html>
        """
    else:
        subject = "Your password has been reset"
        html = f"""
        <html><body style="font-family: sans-serif; padding: 20px;">
        <h2>New password</h2>
        <p>An administrator has reset your password.</p>
        <p>Your new password is:</p>
        <p style="font-family: monospace; font-size: 18px; background: #f4f4f4; padding: 12px; border-radius: 6px; display: inline-block;">{new_password}</p>
        <p>Please sign in with this password and change it afterwards in your settings.</p>
        </body></html>
        """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_sender
    msg["To"] = email
    msg.attach(MIMEText(html, "html"))

    # AWS SES sometimes hangs on QUIT after the message is accepted. Bound
    # the whole handshake so admin actions always return promptly.
    await aiosmtplib.send(
        msg,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user,
        password=settings.smtp_password,
        start_tls=True,
        timeout=15,
    )


@router.post("/users/{user_id}/reset-password")
async def reset_password(
    user_id: str,
    req: ResetPasswordRequest,
    session: AsyncSession = Depends(get_session),
):
    u = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not u:
        raise HTTPException(404, "User not found")
    new_pw = _generate_password()
    u.password_hash = hash_password(new_pw)
    session.add(u)
    await session.commit()

    email_sent = False
    email_error: Optional[str] = None
    if req.send_email:
        try:
            await _send_admin_password_email(u.email, new_pw, u.locale or "de")
            email_sent = True
        except Exception as e:
            email_error = str(e)
            logger.exception("Admin password-reset email failed")

    # Always return the new password to the admin so they can hand it over manually.
    return {
        "ok": True,
        "new_password": new_pw,
        "email_requested": req.send_email,
        "email_sent": email_sent,
        "email_error": email_error,
    }


# ---------- Shopping lists ----------

@router.get("/lists")
async def admin_list_all(session: AsyncSession = Depends(get_session)):
    rows = (
        await session.execute(
            select(ShoppingList, User.email, User.display_name)
            .join(User, User.id == ShoppingList.owner_id)
            .order_by(ShoppingList.created_at.desc())
        )
    ).all()
    out = []
    for lst, email, display_name in rows:
        items_count = (
            await session.execute(select(func.count()).select_from(ListItem).where(ListItem.list_id == lst.id))
        ).scalar_one()
        cats_count = (
            await session.execute(select(func.count()).select_from(Category).where(Category.list_id == lst.id))
        ).scalar_one()
        shares_count = (
            await session.execute(select(func.count()).select_from(ListShare).where(ListShare.list_id == lst.id))
        ).scalar_one()
        out.append({
            "id": lst.id,
            "name": lst.name,
            "owner_id": lst.owner_id,
            "owner_email": email,
            "owner_display_name": display_name,
            "items_count": items_count,
            "categories_count": cats_count,
            "shares_count": shares_count,
            "created_at": lst.created_at.isoformat() if lst.created_at else None,
            "updated_at": lst.updated_at.isoformat() if lst.updated_at else None,
        })
    return out


@router.get("/lists/{list_id}")
async def admin_list_detail(list_id: str, session: AsyncSession = Depends(get_session)):
    lst = (await session.execute(select(ShoppingList).where(ShoppingList.id == list_id))).scalar_one_or_none()
    if not lst:
        raise HTTPException(404, "List not found")
    items = (
        await session.execute(
            select(ListItem).where(ListItem.list_id == list_id).order_by(ListItem.sort_order, ListItem.created_at)
        )
    ).scalars().all()
    categories = (
        await session.execute(
            select(Category).where(Category.list_id == list_id).order_by(Category.sort_order, Category.created_at)
        )
    ).scalars().all()
    return {
        "list": {
            "id": lst.id, "name": lst.name, "owner_id": lst.owner_id,
            "created_at": lst.created_at.isoformat() if lst.created_at else None,
        },
        "categories": [
            {"id": c.id, "name": c.name, "sort_order": c.sort_order} for c in categories
        ],
        "items": [
            {
                "id": i.id, "name": i.name, "quantity": i.quantity,
                "checked": i.checked, "category_id": i.category_id,
                "sort_order": i.sort_order, "added_by_id": i.added_by_id,
            } for i in items
        ],
    }


@router.delete("/lists/{list_id}")
async def admin_delete_list(list_id: str, session: AsyncSession = Depends(get_session)):
    lst = (await session.execute(select(ShoppingList).where(ShoppingList.id == list_id))).scalar_one_or_none()
    if not lst:
        raise HTTPException(404, "List not found")
    await session.execute(delete(ListItem).where(ListItem.list_id == list_id))
    await session.execute(delete(Category).where(Category.list_id == list_id))
    await session.execute(delete(ListShare).where(ListShare.list_id == list_id))
    await session.delete(lst)
    await session.commit()
    return {"ok": True}


@router.delete("/lists/{list_id}/items/{item_id}")
async def admin_delete_item(list_id: str, item_id: str, session: AsyncSession = Depends(get_session)):
    it = (
        await session.execute(
            select(ListItem).where(ListItem.id == item_id, ListItem.list_id == list_id)
        )
    ).scalar_one_or_none()
    if not it:
        raise HTTPException(404, "Item not found")
    await session.delete(it)
    await session.commit()
    return {"ok": True}


class ReorderRequest(BaseModel):
    ordered_ids: list[str]


@router.patch("/lists/{list_id}/items/reorder")
async def admin_reorder_items(
    list_id: str,
    req: ReorderRequest,
    session: AsyncSession = Depends(get_session),
):
    items = (await session.execute(select(ListItem).where(ListItem.list_id == list_id))).scalars().all()
    by_id = {i.id: i for i in items}
    for idx, iid in enumerate(req.ordered_ids):
        if iid in by_id:
            by_id[iid].sort_order = idx
            session.add(by_id[iid])
    await session.commit()
    return {"ok": True, "reordered": len(req.ordered_ids)}


@router.delete("/lists/{list_id}/categories/{cat_id}")
async def admin_delete_category(list_id: str, cat_id: str, session: AsyncSession = Depends(get_session)):
    c = (
        await session.execute(
            select(Category).where(Category.id == cat_id, Category.list_id == list_id)
        )
    ).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Category not found")
    # Detach items from the removed category (don't delete the items themselves).
    orphans = (await session.execute(select(ListItem).where(ListItem.category_id == cat_id))).scalars().all()
    for item in orphans:
        item.category_id = None
        session.add(item)
    await session.delete(c)
    await session.commit()
    return {"ok": True}


@router.patch("/lists/{list_id}/categories/reorder")
async def admin_reorder_categories(
    list_id: str,
    req: ReorderRequest,
    session: AsyncSession = Depends(get_session),
):
    cats = (await session.execute(select(Category).where(Category.list_id == list_id))).scalars().all()
    by_id = {c.id: c for c in cats}
    for idx, cid in enumerate(req.ordered_ids):
        if cid in by_id:
            by_id[cid].sort_order = idx
            session.add(by_id[cid])
    await session.commit()
    return {"ok": True, "reordered": len(req.ordered_ids)}


# ---------- Runtime model overrides ----------

class ModelOverrideRequest(BaseModel):
    # Use None to leave unchanged; pass empty string to clear that specific override.
    ollama_model: Optional[str] = None
    ollama_ocr_model: Optional[str] = None
    ollama_audio_model: Optional[str] = None
    ollama_recipe_model: Optional[str] = None


@router.get("/runtime-config")
async def get_runtime_config():
    return runtime_config.get_state()


@router.post("/runtime-config")
async def set_runtime_config(req: ModelOverrideRequest):
    for key in ("ollama_model", "ollama_ocr_model", "ollama_audio_model", "ollama_recipe_model"):
        val = getattr(req, key)
        if val is not None:
            runtime_config.set_override(key, val)
    return runtime_config.get_state()


@router.delete("/runtime-config")
async def clear_runtime_config():
    runtime_config.clear_overrides()
    return runtime_config.get_state()
