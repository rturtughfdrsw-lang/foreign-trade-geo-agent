"""Persistence abstractions for historical results."""

from .sqlite import SQLiteHistoryStore

__all__ = ["SQLiteHistoryStore"]
