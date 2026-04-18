import uuid
from datetime import datetime, timezone
from sqlmodel import SQLModel, Field, UniqueConstraint


class BonusCardShare(SQLModel, table=True):
    __tablename__ = "bonus_card_shares"
    __table_args__ = (UniqueConstraint("card_id", "user_id"),)

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    card_id: str = Field(foreign_key="bonus_cards.id", index=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
