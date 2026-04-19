from datetime import datetime, timezone
from sqlmodel import SQLModel, Field


class FeatureFlag(SQLModel, table=True):
    """Persistent key-value flags toggled by admins.

    Values are stored as short strings so the same table can hold booleans,
    enum-ish choices, or short config strings without schema changes. Booleans
    use ``"true"`` / ``"false"``.
    """

    __tablename__ = "feature_flags"

    key: str = Field(primary_key=True, max_length=100)
    value: str = Field(max_length=1000)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
