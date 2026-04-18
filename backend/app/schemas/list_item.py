from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime


class CreateItemRequest(BaseModel):
    name: str
    quantity: Optional[str] = None
    category_id: Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 1 or len(v) > 200:
            raise ValueError("Item name must be 1-200 characters")
        return v


class UpdateItemRequest(BaseModel):
    name: Optional[str] = None
    quantity: Optional[str] = None
    checked: Optional[bool] = None
    category_id: Optional[str] = None
    sort_order: Optional[int] = None


class ReorderItemsRequest(BaseModel):
    item_ids: list[str]


class ItemResponse(BaseModel):
    id: str
    list_id: str
    category_id: Optional[str]
    added_by_id: str
    added_by_name: str = ""
    added_by_color: str = "#4A90D9"
    name: str
    quantity: Optional[str]
    checked: bool
    sort_order: int
    image_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class AutoSortProposal(BaseModel):
    item_id: str
    item_name: str
    category_id: str
    category_name: str
    confidence: float


class AutoSortResponse(BaseModel):
    assignments: list[AutoSortProposal]


class ApplyAutoSortRequest(BaseModel):
    assignments: list[dict]  # [{item_id: str, category_id: str}]
