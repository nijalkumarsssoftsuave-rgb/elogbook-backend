"""Shared API schema types."""

from typing import Generic, TypeVar

from pydantic import BaseModel

from src.core.response import Envelope, ErrorDetail, Meta

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """A single page of a paginated list response (US-009 ES-314)."""

    items: list[T]
    page: int
    page_size: int
    total: int
    total_pages: int
    sort: str | None = None


__all__ = ["Envelope", "ErrorDetail", "Meta", "Page"]
