import uuid
from datetime import datetime, timezone
from sqlmodel import SQLModel, Field


class ShoppingList(SQLModel, table=True):
    __tablename__ = "shopping_lists"

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    owner_id: str = Field(foreign_key="users.id", index=True)
    name: str = Field(max_length=100)
    sort_order: int = Field(default=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
