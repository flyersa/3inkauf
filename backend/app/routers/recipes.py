"""Recipe generation endpoints.

Two flavors:
- POST /lists/{list_id}/recipes/from-items → propose 3-5 recipes makeable from
  items already on the list, flagging which ingredients are missing.
- POST /recipes/from-query → expand a free-text request like "spaghetti
  bolognese for 4 people" into a structured ingredient list.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import get_settings
from app.core import runtime_config
from app.core.deps import get_current_user
from app.core.ratelimit import limiter
from app.database import get_session
from app.models.list_item import ListItem
from app.models.user import User
from app.routers.lists import get_list_with_access
from app.services.ml_service import ml_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["recipes"])


class RecipeFromQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    locale: str = "de"


class RecipeIngredient(BaseModel):
    name: str
    quantity: Optional[str] = None


class FullRecipeRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    servings: Optional[int] = None
    existing_ingredients: Optional[list[RecipeIngredient]] = None
    locale: str = "de"


class RecipeEmailRequest(BaseModel):
    title: str
    servings: Optional[int] = None
    prep_time_minutes: Optional[int] = None
    cook_time_minutes: Optional[int] = None
    ingredients: list[RecipeIngredient] = []
    steps: list[str] = []
    tips: Optional[str] = None
    locale: str = "de"


@router.post("/lists/{list_id}/recipes/from-items")
async def recipes_from_items(
    list_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await get_list_with_access(list_id, current_user, session)
    settings = get_settings()
    if not settings.ollama_url:
        raise HTTPException(
            status_code=503,
            detail="Recipe generation requires Ollama (advanced AI mode)",
        )

    items_rows = (
        await session.execute(
            select(ListItem).where(ListItem.list_id == list_id)
        )
    ).scalars().all()
    names = [i.name for i in items_rows if i.name and i.name.strip()]
    if not names:
        raise HTTPException(status_code=400, detail="List has no items to base recipes on")

    locale = (current_user.locale or "de").lower()
    try:
        return ml_service.generate_recipes_from_items(
            items_on_list=names,
            locale=locale,
            ollama_url=settings.ollama_url,
            ollama_model=runtime_config.get_recipe_model(),
        )
    except Exception as e:
        logger.exception("generate_recipes_from_items failed")
        raise HTTPException(status_code=500, detail=f"Recipe generation failed: {e}")


@router.post("/recipes/from-query")
async def recipe_from_query(
    req: RecipeFromQueryRequest,
    current_user: User = Depends(get_current_user),
):
    settings = get_settings()
    if not settings.ollama_url:
        raise HTTPException(
            status_code=503,
            detail="Recipe generation requires Ollama (advanced AI mode)",
        )
    locale = (req.locale or current_user.locale or "de").lower()
    try:
        return ml_service.generate_recipe_from_query(
            query=req.query,
            locale=locale,
            ollama_url=settings.ollama_url,
            ollama_model=runtime_config.get_recipe_model(),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("generate_recipe_from_query failed")
        raise HTTPException(status_code=500, detail=f"Recipe generation failed: {e}")


@router.post("/recipes/full")
async def full_recipe(
    req: FullRecipeRequest,
    current_user: User = Depends(get_current_user),
):
    settings = get_settings()
    if not settings.ollama_url:
        raise HTTPException(status_code=503, detail="Recipe generation requires Ollama")
    locale = (req.locale or current_user.locale or "de").lower()
    existing = [i.model_dump() for i in (req.existing_ingredients or [])]
    try:
        return ml_service.generate_full_recipe(
            title=req.title,
            locale=locale,
            servings=req.servings,
            existing_ingredients=existing,
            ollama_url=settings.ollama_url,
            ollama_model=runtime_config.get_recipe_model(),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("generate_full_recipe failed")
        raise HTTPException(status_code=500, detail=f"Recipe generation failed: {e}")


@router.post("/recipes/email")
@limiter.limit("20/hour")
async def email_recipe(
    request: Request,
    req: RecipeEmailRequest,
    current_user: User = Depends(get_current_user),
):
    """Send the rendered recipe to the currently authenticated user's address."""
    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_user:
        raise HTTPException(status_code=503, detail="SMTP not configured on this server")
    if not current_user.email:
        raise HTTPException(status_code=400, detail="Current user has no email address")

    locale = (req.locale or current_user.locale or "de").lower()
    is_de = locale.startswith("de")

    # Build HTML body
    ing_rows = "".join(
        f"<li>{_esc(i.name)}"
        + (f" <span style=\"color:#888\">({_esc(i.quantity)})</span>" if i.quantity else "")
        + "</li>"
        for i in req.ingredients
    )
    step_rows = "".join(f"<li>{_esc(s)}</li>" for s in req.steps)

    labels = {
        "ingredients": "Zutaten" if is_de else "Ingredients",
        "steps": "Zubereitung" if is_de else "Steps",
        "servings": "Portionen" if is_de else "Servings",
        "prep": "Vorbereitung" if is_de else "Prep",
        "cook": "Kochzeit" if is_de else "Cook",
        "tips": "Tipps" if is_de else "Tips",
        "subject_prefix": "Rezept" if is_de else "Recipe",
        "minutes": "Min." if is_de else "min",
    }

    meta_bits = []
    if req.servings:
        meta_bits.append(f"{labels['servings']}: {req.servings}")
    if req.prep_time_minutes:
        meta_bits.append(f"{labels['prep']}: {req.prep_time_minutes} {labels['minutes']}")
    if req.cook_time_minutes:
        meta_bits.append(f"{labels['cook']}: {req.cook_time_minutes} {labels['minutes']}")
    meta = " &middot; ".join(meta_bits)

    html = f"""
    <html><body style="font-family: sans-serif; padding: 20px; max-width: 640px;">
      <h1 style="color: #ea580c;">{_esc(req.title)}</h1>
      {f'<p style="color:#666;">{meta}</p>' if meta else ''}
      <h2>{labels['ingredients']}</h2>
      <ul>{ing_rows}</ul>
      <h2>{labels['steps']}</h2>
      <ol>{step_rows}</ol>
      {f'<p><strong>{labels["tips"]}:</strong> {_esc(req.tips)}</p>' if req.tips else ''}
      <p style="color:#999; font-size:12px; margin-top:30px;">3inkauf</p>
    </body></html>
    """

    import aiosmtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"{labels['subject_prefix']}: {req.title}"
    msg["From"] = settings.smtp_sender
    msg["To"] = current_user.email
    msg.attach(MIMEText(html, "html"))

    try:
        # AWS SES occasionally hangs on QUIT after accepting the message, which
        # makes the request wait forever. Bound the whole SMTP handshake so the
        # HTTP request always completes.
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            start_tls=True,
            timeout=15,
        )
    except TimeoutError:
        logger.warning("SMTP timed out on recipe email to %s (message likely delivered)", current_user.email)
        return {"ok": True, "to": current_user.email, "timeout": True}
    except Exception as e:
        logger.exception("Failed to send recipe email")
        raise HTTPException(status_code=500, detail=f"Email delivery failed: {e}")
    return {"ok": True, "to": current_user.email}


def _esc(s) -> str:
    """Minimal HTML escape for email body."""
    if s is None:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
