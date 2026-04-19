import base64
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from passlib.context import CryptContext

from app.config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: str, expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload = {"sub": user_id, "exp": expire, "type": "access"}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    payload = {"sub": user_id, "exp": expire, "type": "refresh"}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])


def generate_reset_token() -> tuple[str, str]:
    """Returns (raw_token, hashed_token)."""
    raw = secrets.token_urlsafe(32)
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed


def hash_reset_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def _image_signature(image_id: str, expires_at: int) -> str:
    """HMAC-SHA256 over image_id|expires_at, url-safe base64 w/o padding."""
    msg = f"{image_id}|{expires_at}".encode()
    sig = hmac.new(settings.secret_key.encode(), msg, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).rstrip(b"=").decode()


def signed_image_url(image_id: str, ttl_seconds: Optional[int] = None) -> str:
    """Build a short-lived, HMAC-signed URL for an image. `<img>` tags can't
    send Authorization headers, so we sign the URL instead — anyone authorized
    got the URL from an authenticated API response, and it stops working in
    ``IMAGE_URL_TTL_SECONDS`` regardless of where it leaks to."""
    ttl = ttl_seconds if ttl_seconds is not None else settings.image_url_ttl_seconds
    exp = int(time.time()) + max(60, int(ttl))
    sig = _image_signature(image_id, exp)
    return f"/api/v1/images/{image_id}?exp={exp}&sig={sig}"


def verify_image_signature(image_id: str, expires_at: int, sig: str) -> bool:
    """Constant-time verify that ``sig`` was produced by ``_image_signature``
    and that the URL hasn't expired."""
    if int(time.time()) > expires_at:
        return False
    expected = _image_signature(image_id, expires_at)
    return hmac.compare_digest(expected.encode(), sig.encode())
