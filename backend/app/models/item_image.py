import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, LargeBinary


class ItemImage(SQLModel, table=True):
    __tablename__ = "item_images"

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    content_type: str = Field(max_length=50)
    data: Optional[bytes] = Field(default=None, sa_column=Column(LargeBinary))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
