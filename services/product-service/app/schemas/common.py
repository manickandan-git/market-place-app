from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class PageMetadata(APIModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int


ItemT = TypeVar("ItemT")


class PaginatedResponse[ItemT](APIModel):
    items: list[ItemT]
    pagination: PageMetadata

    @classmethod
    def create(
        cls,
        *,
        items: list[ItemT],
        page: int,
        page_size: int,
        total_items: int,
    ) -> "PaginatedResponse[ItemT]":
        return cls(
            items=items,
            pagination=PageMetadata(
                page=page,
                page_size=page_size,
                total_items=total_items,
                total_pages=(total_items + page_size - 1) // page_size,
            ),
        )


class ErrorResponse(APIModel):
    error_code: str
    message: str
    request_id: str | None = None
    details: list[dict] = Field(default_factory=list)


class HealthResponse(APIModel):
    service: str
    status: str
    version: str
