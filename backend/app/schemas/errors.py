"""Standard error response schemas for consistent API error handling."""
from typing import Any

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Single error response (4xx/5xx)."""

    detail: str = Field(..., description="Human-readable error message")
    status_code: int | None = Field(None, description="HTTP status code")
    error: str | None = Field(None, description="Error type/code, e.g. not_found, bad_request")


class ValidationErrorItem(BaseModel):
    """One validation error (field or body)."""

    loc: list[str | int] = Field(..., description="Path to the field (e.g. ['body', 'messages'])")
    msg: str = Field(..., description="Error message")
    type: str | None = Field(None, description="Pydantic error type")


class ValidationErrorDetail(BaseModel):
    """Validation error response (422)."""

    detail: list[ValidationErrorItem] = Field(..., description="List of validation errors")
    status_code: int = Field(422, description="HTTP status code")
