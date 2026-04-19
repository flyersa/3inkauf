"""Persistent feature flags (SQLite on the PVC, survives restarts).

Kept separate from ``runtime_config`` which holds deliberately-ephemeral
Ollama model overrides. Flags here are written to the ``feature_flags`` table
so that an admin toggle sticks even after a pod restart.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.feature_flag import FeatureFlag


DEFAULTS: dict[str, str] = {
    # User self-registration via POST /auth/register. When disabled, the only
    # way new users get in is via POST /admin/users.
    "registration_enabled": "true",
}


async def get_string(session: AsyncSession, key: str, default: Optional[str] = None) -> str:
    row = (
        await session.execute(select(FeatureFlag).where(FeatureFlag.key == key))
    ).scalar_one_or_none()
    if row is None:
        return default if default is not None else DEFAULTS.get(key, "")
    return row.value


async def set_string(session: AsyncSession, key: str, value: str) -> None:
    row = (
        await session.execute(select(FeatureFlag).where(FeatureFlag.key == key))
    ).scalar_one_or_none()
    if row is None:
        row = FeatureFlag(key=key, value=value)
    else:
        row.value = value
        row.updated_at = datetime.now(timezone.utc)
    session.add(row)
    await session.commit()


async def get_bool(session: AsyncSession, key: str, default: bool = False) -> bool:
    raw = await get_string(session, key, default="true" if default else "false")
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


async def set_bool(session: AsyncSession, key: str, value: bool) -> None:
    await set_string(session, key, "true" if value else "false")


async def get_all(session: AsyncSession) -> dict[str, str]:
    """Return every known flag, falling back to DEFAULTS for missing rows."""
    rows = (await session.execute(select(FeatureFlag))).scalars().all()
    out = dict(DEFAULTS)
    for r in rows:
        out[r.key] = r.value
    return out
