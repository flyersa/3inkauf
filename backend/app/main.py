import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.database import init_db
from app.core.ratelimit import limiter
from app.core.security import decode_token
from app.core.websocket import manager
from app.routers import auth, lists, categories, items, sharing, ml, images, bonus_cards, lists_scan, voice, admin, recipes
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


@app.websocket("/ws/lists/{list_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    list_id: str,
    token: str = Query(...),
):
    # Authenticate
    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        if not user_id:
            await websocket.close(code=4001)
            return
    except Exception:
        await websocket.close(code=4001)
        return

    await manager.connect(websocket, list_id, user_id)
    try:
        while True:
            data = await websocket.receive_text()
            # Client messages can be forwarded to other users
            try:
                msg = json.loads(data)
                msg["user_id"] = user_id
                await manager.broadcast(list_id, msg, exclude_user=user_id)
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        manager.disconnect(list_id, user_id)


@app.get("/")
async def root():
    return {"message": "Grocery PWA API", "docs": "/docs"}
