import json
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import get_settings
from app.core import feature_flags
from app.core.ratelimit import limiter
from app.core.security import decode_token
from app.core.websocket import manager
from app.database import get_session, init_db
from app.models.user import User
from app.routers import auth, lists, categories, items, sharing, ml, images, bonus_cards, lists_scan, voice, admin, recipes
from app.routers.lists import get_list_with_access
from app.services.ml_service import ml_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up Grocery PWA backend...")
    await init_db()
    logger.info("Database initialized")

    # Load ML model in background
    try:
        ml_service.load_model(settings.ml_model_name)
    except Exception as e:
        logger.warning(f"ML model loading failed (non-fatal): {e}")

    yield

    # Shutdown
    logger.info("Shutting down...")


app = FastAPI(
    title="Grocery PWA API",
    version="0.1.0",
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — origins come from the CORS_ORIGINS env var (comma-separated).
# If unset, fall back to wildcard + no credentials (safe dev default: browsers
# ignore credentialed requests to a wildcard origin per the CORS spec).
_origins_raw = [o.strip() for o in (settings.cors_origins or "").split(",") if o.strip()]
_allowed_origins = _origins_raw or ["*"]
_allow_credentials = bool(_origins_raw)  # credentials only when we pinned origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
logger.info(
    "CORS: allowed_origins=%s allow_credentials=%s",
    _allowed_origins, _allow_credentials,
)

# Routers
app.include_router(auth.router, prefix="/api/v1")
app.include_router(lists.router, prefix="/api/v1")
app.include_router(categories.router, prefix="/api/v1")
app.include_router(items.router, prefix="/api/v1")
app.include_router(sharing.router, prefix="/api/v1")
app.include_router(ml.router, prefix="/api/v1")
app.include_router(images.router, prefix="/api/v1")
app.include_router(bonus_cards.router, prefix="/api/v1")
app.include_router(lists_scan.router, prefix="/api/v1")
app.include_router(voice.router, prefix="/api/v1")
app.include_router(recipes.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")


@app.get("/api/v1/health")
async def health():
    return {
        "status": "ok",
        "model_loaded": ml_service.model is not None,
        "ollama_enabled": bool(settings.ollama_url),
    }


@app.get("/api/v1/config")
async def public_config(session: AsyncSession = Depends(get_session)):
    """Public, unauthenticated config the login/register pages need to render
    correctly (e.g. whether self-registration is enabled). Keep this surface
    minimal — every field here is effectively world-readable."""
    reg = await feature_flags.get_bool(session, "registration_enabled", True)
    return {"registration_enabled": reg}


@app.websocket("/ws/lists/{list_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    list_id: str,
    token: str = Query(...),
    session: AsyncSession = Depends(get_session),
):
    # 1. Authenticate with an ACCESS token only. Mirrors get_current_user so
    #    30-day refresh tokens can't be used for month-long WS surveillance.
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            await websocket.close(code=4001)
            return
        user_id = payload.get("sub")
        if not user_id:
            await websocket.close(code=4001)
            return
    except Exception:
        await websocket.close(code=4001)
        return

    # 2. Load the user row (sanity check — account may have been deleted).
    res = await session.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if user is None:
        await websocket.close(code=4001)
        return

    # 3. AuthZ: user must be the owner or have a ListShare on this list.
    #    Closes (a) the IDOR — joining any random list — and (b) the
    #    non-existent-list-id DoS. Reuses the HTTP route's gate function
    #    so authz rules stay in one place.
    try:
        await get_list_with_access(list_id, user, session)
    except HTTPException as exc:
        # 404 (list missing or not shared to us) → 4004; 403 → 4003.
        await websocket.close(code=4004 if exc.status_code == 404 else 4003)
        return

    await manager.connect(websocket, list_id, user_id)
    try:
        # Passive listener only. Client messages are CONSUMED and DISCARDED.
        # Previously the server re-broadcast arbitrary client JSON as-is,
        # letting an attacker inject fake item_added / items_cleared events
        # to any room they could join. All real mutations travel over HTTP,
        # where the route handler stamps and broadcasts server-trusted events.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(list_id, user_id)


@app.get("/")
async def root():
    return {"message": "Grocery PWA API", "docs": "/docs"}
