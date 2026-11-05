"""The downstream safety gate. Every path from a prescription item to prices must call this."""

from __future__ import annotations

from typing import Protocol


class UnverifiedItemError(Exception):
    """A prescription item has no human-confirmed identity, so it cannot reach comparison."""

    def __init__(self, status: str) -> None:
        super().__init__(status)
        self.status = status


class GatedItem(Protocol):
    @property
    def status(self) -> str: ...
    @property
    def verified_medicine_id(self) -> int | None: ...
    @property
    def verified_by_type(self) -> str | None: ...


def require_verified(item: GatedItem) -> int:
    """Return the confirmed medicine id, or raise. Confidence scores are deliberately not inputs."""
    if (
        item.status != "verified"
        or item.verified_medicine_id is None
        or item.verified_by_type not in {"user", "pharmacist"}
    ):
        raise UnverifiedItemError(item.status)
    return item.verified_medicine_id
