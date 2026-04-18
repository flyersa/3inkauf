from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime


class CreateListRequest(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 1 or len(v) > 100:
            raise ValueError("List name must be 1-100 characters")
        return v


class UpdateListRequest(BaseModel):
    name: Optional[str] = None
    sort_order: Optional[int] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if len(v) < 1 or len(v) > 100:
                raise ValueError("List name must be 1-100 characters")
        return v


class ListResponse(BaseModel):
    id: str
    owner_id: str
    name: str
    sort_order: int
    created_at: datetime
    updated_at: datetime
    is_owner: bool = False
    permission: Optional[str] = None
    item_count: int = 0


class ShareRequest(BaseModel):
    email: str
    permission: str = "edit"

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.lower().strip()

    @field_validator("permission")
    @classmethod
    def validate_permission(cls, v: str) -> str:
        if v not in ("view", "edit"):
            raise ValueError("Permission must be view or edit")
        return v


class ShareResponse(BaseModel):
    id: str
    list_id: str
    user_id: str
    user_email: str
    user_display_name: str
    user_color: str
    permission: str
