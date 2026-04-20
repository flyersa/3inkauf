import logging
from typing import Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.core.deps import get_current_user
from app.core.ratelimit import limiter
from app.config import get_settings
from app.core import runtime_config
from app.models.user import User
from app.services.ml_service import ml_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])


class VoiceContext(BaseModel):
    route: str = "unknown"
    list_id: Optional[str] = None
    list_name: Optional[str] = None
    items: list[str] = []
    locale: str = "en"


class VoiceIntentRequest(BaseModel):
    transcript: str
    context: VoiceContext = VoiceContext()


@router.post("/intent")
@limiter.limit("30/minute")
async def parse_voice_intent(
    request: Request,
    req: VoiceIntentRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.ollama_url:
        raise HTTPException(
            status_code=503,
            detail="Voice intent parsing requires Ollama (advanced AI mode)",
        )
    transcript = (req.transcript or "").strip()
    if not transcript:
        raise HTTPException(status_code=400, detail="Empty transcript")

    try:
        return ml_service.parse_voice_intent(
            transcript=transcript,
            context=req.context.model_dump(),
            ollama_url=settings.ollama_url,
            ollama_model=runtime_config.get_audio_model(),
        )
    except Exception as e:
        logger.exception("Voice intent parsing failed")
        raise HTTPException(status_code=500, detail=f"Intent parsing failed: {e}")
