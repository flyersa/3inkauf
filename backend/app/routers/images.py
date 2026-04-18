import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.database import get_session
from app.core.deps import get_current_user
from app.models.user import User
from app.models.list_item import ListItem
from app.models.item_image import ItemImage
from app.routers.lists import get_list_with_access

router = APIRouter(tags=["images"])

MAX_SIZE = 5 * 1024 * 1024  # 5MB


@router.post("/lists/{list_id}/items/{item_id}/image")
async def upload_item_image(
    list_id: str,
    item_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await get_list_with_access(list_id, current_user, session)
    result = await session.execute(
        select(ListItem).where(ListItem.id == item_id, ListItem.list_id == list_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    if file.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, and WebP images are allowed")

    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="Image too large (max 5MB)")

    # Delete old image from DB if exists
    if item.image_path:
        old_img = await session.execute(
            select(ItemImage).where(ItemImage.id == item.image_path)
        )
        old = old_img.scalar_one_or_none()
        if old:
            await session.delete(old)

    # Store new image as BLOB in SQLite
    image_id = uuid.uuid4().hex
    img = ItemImage(id=image_id, content_type=file.content_type, data=content)
    session.add(img)

    item.image_path = image_id
    session.add(item)
    await session.commit()

    return {"image_url": f"/api/v1/images/{image_id}"}


@router.delete("/lists/{list_id}/items/{item_id}/image")
async def delete_item_image(
    list_id: str,
    item_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await get_list_with_access(list_id, current_user, session)
    result = await session.execute(
        select(ListItem).where(ListItem.id == item_id, ListItem.list_id == list_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    if item.image_path:
        img_result = await session.execute(
            select(ItemImage).where(ItemImage.id == item.image_path)
        )
        img = img_result.scalar_one_or_none()
        if img:
            await session.delete(img)
        item.image_path = None
        session.add(item)
        await session.commit()

    return {"message": "Image deleted"}


@router.get("/images/{image_id}")
async def get_image(image_id: str, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(ItemImage).where(ItemImage.id == image_id)
    )
    img = result.scalar_one_or_none()
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")

    return Response(
        content=img.data,
        media_type=img.content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
