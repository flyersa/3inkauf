import logging
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException

from app.core.deps import get_current_user
from app.config import get_settings
from app.core import runtime_config
from app.models.user import User
from app.services.ml_service import ml_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lists/scan", tags=["lists-scan"])

MAX_SIZE = 8 * 1024 * 1024


@router.post("")
async def scan_list_from_photo(
    file: UploadFile = File(...),
    language: str = Form("English"),
    current_user: User = Depends(get_current_user),
):
    """Take a photo of a paper shopping list and return a structured proposal.
    The client is expected to preview and confirm before persisting."""
    settings = get_settings()
    if not settings.ollama_url:
        raise HTTPException(
            status_code=503,
            detail="Scan is only available when Ollama (advanced AI mode) is configured",
        )
    if file.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, and WebP images are allowed")
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="Image too large (max 8MB)")
    try:
        return ml_service.scan_list_from_image(
            content,
            language=language,
            ollama_url=settings.ollama_url,
            ollama_model=runtime_config.get_ocr_model(),
        )
    except Exception as e:
        logger.exception("Scan failed")
        raise HTTPException(status_code=500, detail=f"Scan failed: {e}")


@router.post("-fridge")
async def scan_fridge_from_photo(
    file: UploadFile = File(...),
    language: str = Form("German"),
    current_user: User = Depends(get_current_user),
):
    """Photograph of a fridge interior → list of detected items + categories
    + per-item confidence. Reuses the same preview flow as paper-list scan."""
    settings = get_settings()
    if not settings.ollama_url:
        raise HTTPException(
            status_code=503,
            detail="Fridge scan is only available when Ollama is configured",
        )
    if file.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, and WebP images are allowed")
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="Image too large (max 8MB)")
    try:
        return ml_service.scan_fridge_from_image(
            content,
            language=language,
            ollama_url=settings.ollama_url,
            ollama_model=runtime_config.get_fridge_model(),
        )
    except Exception as e:
        logger.exception("Fridge scan failed")
        raise HTTPException(status_code=500, detail=f"Fridge scan failed: {e}")
