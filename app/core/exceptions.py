"""Shared application exceptions."""

from __future__ import annotations

from fastapi import HTTPException, status


class ValidationFailure(HTTPException):
    """Raised when user input fails business validation."""

    def __init__(self, detail: str) -> None:
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


class ResourceNotFound(HTTPException):
    """Raised when an expected entity cannot be found."""

    def __init__(self, detail: str) -> None:
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class ExternalToolFailure(HTTPException):
    """Raised when a controlled subprocess returns an error."""

    def __init__(self, detail: str) -> None:
        super().__init__(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)
