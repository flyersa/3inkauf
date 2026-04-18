from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime


class CreateCategoryRequest(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 1 or len(v) > 100:
            raise ValueError("Category name must be 1-100 characters")
        return v


class UpdateCategoryRequest(BaseModel):
    name: Optional[str] = None
    sort_order: Optional[int] = None


class ReorderCategoriesRequest(BaseModel):
    category_ids: list[str]


class CategoryResponse(BaseModel):
    id: str
    list_id: str
    name: str
    sort_order: int
    created_at: datetime
