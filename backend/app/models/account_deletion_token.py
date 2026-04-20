import uuid
from datetime import datetime, timezone
from sqlmodel import SQLModel, Field


class AccountDeletionToken(SQLModel, table=True):
    __tablename__ = "account_deletion_tokens"

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    code_hash: str = Field(max_length=255)
    expires_at: datetime
    attempts: int = Field(default=0)
    used: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
