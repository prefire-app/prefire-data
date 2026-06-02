"""Common dataset interface for prefire-data endpoints."""

from typing import Protocol


class Dataset(Protocol):
    """Protocol every dataset module must satisfy.

    A dataset module exposes a single `query(event)` callable that takes an
    API Gateway HTTP API v2 event dict and returns a JSON-serializable dict.
    """

    def query(self, event: dict) -> dict:
        """Return a JSON-serializable dict for the given event."""
        ...
