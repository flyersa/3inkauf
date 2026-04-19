"""HTTP Basic auth for /admin endpoints. Credentials come from env vars
ADMIN_USERNAME and ADMIN_PASSWORD. If either is empty, admin is disabled."""
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import get_settings

_security = HTTPBasic(auto_error=False)


def get_admin(credentials: HTTPBasicCredentials | None = Depends(_security)) -> str:
    settings = get_settings()
    if not settings.admin_username or not settings.admin_password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin interface not configured on this server",
        )
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin credentials required",
            headers={"WWW-Authenticate": "Basic"},
        )
    ok_user = secrets.compare_digest(
        credentials.username.encode("utf-8"), settings.admin_username.encode("utf-8")
    )
    ok_pass = secrets.compare_digest(
        credentials.password.encode("utf-8"), settings.admin_password.encode("utf-8")
    )
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
