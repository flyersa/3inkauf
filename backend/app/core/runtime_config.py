"""In-memory runtime overrides for Ollama model selection.

Admins can temporarily swap models via /admin/runtime-config without touching
the .env. Overrides reset on every backend restart — the env file remains the
source of truth, and the API surfaces both sides so the operator sees the
difference.
"""
from typing import Optional

from app.config import get_settings


_overrides: dict[str, Optional[str]] = {
    "ollama_model": None,
    "ollama_ocr_model": None,
    "ollama_audio_model": None,
    "ollama_recipe_model": None,
    "ollama_fridge_model": None,
    "ollama_item_model": None,
}


def get_model() -> str:
    s = get_settings()
    return _overrides["ollama_model"] or s.ollama_model


def get_ocr_model() -> str:
    s = get_settings()
    return _overrides["ollama_ocr_model"] or s.ollama_ocr_model or s.ollama_model


def get_audio_model() -> str:
    s = get_settings()
    return _overrides["ollama_audio_model"] or s.ollama_audio_model or s.ollama_model


def get_recipe_model() -> str:
    s = get_settings()
    return _overrides["ollama_recipe_model"] or s.ollama_recipe_model or s.ollama_model


def get_fridge_model() -> str:
    s = get_settings()
    return _overrides["ollama_fridge_model"] or s.ollama_fridge_model or s.ollama_ocr_model or s.ollama_model


def get_item_model() -> str:
    """Item-from-photo: single grocery item in a user's own photo. Falls
    back to the fridge model because the task shape is identical."""
    s = get_settings()
    return (
        _overrides["ollama_item_model"]
        or s.ollama_item_model
        or _overrides["ollama_fridge_model"]
        or s.ollama_fridge_model
        or s.ollama_model
    )


def get_state() -> dict:
    s = get_settings()
    return {
        "settings": {
            "ollama_model": s.ollama_model,
            "ollama_ocr_model": s.ollama_ocr_model,
            "ollama_audio_model": s.ollama_audio_model,
            "ollama_recipe_model": s.ollama_recipe_model,
            "ollama_fridge_model": s.ollama_fridge_model,
            "ollama_item_model": s.ollama_item_model,
        },
        "overrides": dict(_overrides),
        "effective": {
            "ollama_model": get_model(),
            "ollama_ocr_model": get_ocr_model(),
            "ollama_audio_model": get_audio_model(),
            "ollama_recipe_model": get_recipe_model(),
            "ollama_fridge_model": get_fridge_model(),
            "ollama_item_model": get_item_model(),
        },
    }


def set_override(key: str, value: Optional[str]) -> None:
    if key not in _overrides:
        raise KeyError(key)
    v = (value or "").strip()
    _overrides[key] = v or None


def clear_overrides() -> None:
    for k in _overrides:
        _overrides[k] = None
