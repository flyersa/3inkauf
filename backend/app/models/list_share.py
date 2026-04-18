import uuid
from datetime import datetime, timezone
from sqlmodel import SQLModel, Field, UniqueConstraint


class ListShare(SQLModel, table=True):
    __tablename__ = "list_shares"
    __table_args__ = (UniqueConstraint("list_id", "user_id"),)

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    list_id: str = Field(foreign_key="shopping_lists.id", index=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    permission: str = Field(default="edit", max_length=10)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
