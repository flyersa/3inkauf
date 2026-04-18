import uuid
from datetime import datetime, timezone
from sqlmodel import SQLModel, Field, UniqueConstraint


class SortingHint(SQLModel, table=True):
    __tablename__ = "sorting_hints"
    __table_args__ = (UniqueConstraint("user_id", "item_name"),)

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    item_name: str = Field(max_length=200)  # lowercased, trimmed
    category_name: str = Field(max_length=100)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
