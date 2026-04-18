import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field


class ListItem(SQLModel, table=True):
    __tablename__ = "list_items"

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    list_id: str = Field(foreign_key="shopping_lists.id", index=True)
    category_id: Optional[str] = Field(default=None, foreign_key="categories.id", index=True)
    added_by_id: str = Field(foreign_key="users.id")
    name: str = Field(max_length=200)
    quantity: Optional[str] = Field(default=None, max_length=50)
    checked: bool = Field(default=False)
    sort_order: int = Field(default=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
