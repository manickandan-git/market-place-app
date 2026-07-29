from __future__ import annotations

from math import ceil

from pydantic import BaseModel, ConfigDict, Field


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=False)


class PaginatedResponse[T](APIModel):
    items: list[T]
    page: int
    page_size: int
    total_items: int
    total_pages: int

    @classmethod
    def create(
        cls,
        *,
        items: list,
        page: int,
        page_size: int,
        total_items: int,
    ):
        return cls(
            items=items,
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=ceil(total_items / page_size) if total_items else 0,
        )


class ErrorDetail(APIModel):
    code: str
    message: str
    request_id: str | None = None


class ErrorResponse(APIModel):
    error: ErrorDetail


class HealthResponse(APIModel):
    status: str = Field(examples=["ok"])
    service: str
    version: str
