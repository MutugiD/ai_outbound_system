"""Shared auth re-exports used by split service apps."""

from app.dependencies import get_current_user

__all__ = ["get_current_user"]

