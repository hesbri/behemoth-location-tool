"""Unified scoped ID generation for the Behemoth Location Tool.

IDs are unique within their owning scope, not globally.

Scopes:
  - EntityDefinition.id              → unique across all entity modules
  - RoomCatalogEntry.id              → unique within room_catalog.json
  - SocketDefinition.id (catalog)    → unique only within that room entry
  - LocationInstance.id              → unique within locations.json
  - SocketDefinition.id (location)   → unique only within that location
  - ExitDefinition.id                → unique only within that location
  - PlacedEntity.instance_id         → unique only within that location
"""
from __future__ import annotations

import re

__all__ = [
    "normalize_id",
    "generate_id",
    "generate_padded_id",
]


# ── Normalization ────────────────────────────────────────────────────────────

_NON_ALNUM = re.compile(r"[^a-zA-Z0-9_]")
_REPEATED_UNDERSCORE = re.compile(r"_{2,}")
_LEADING_TRAILING = re.compile(r"^_+|_+$")


def normalize_id(display_name: str, *, fallback: str = "object") -> str:
    """Convert a display name to a valid snake_case ID.

    Steps:
      1. Lowercase.
      2. Replace spaces and hyphens with underscores.
      3. Strip characters that are not ``[a-zA-Z0-9_]``.
      4. Collapse repeated underscores.
      5. Trim leading/trailing underscores.
      6. If the result is empty, use *fallback*.
    """
    text = display_name.lower()
    text = text.replace(" ", "_").replace("-", "_")
    text = _NON_ALNUM.sub("", text)
    text = _REPEATED_UNDERSCORE.sub("_", text)
    text = _LEADING_TRAILING.sub("", text)
    return text or fallback


# ── Uniqueness helpers ───────────────────────────────────────────────────────

def _base_and_suffix(candidate: str) -> tuple[str, int]:
    """Split *candidate* into ``(base, suffix)``.

    If *candidate* ends with ``_N`` where N is a positive integer, return
    ``(base, N)``.  Otherwise return ``(candidate, 0)``.
    """
    m = re.match(r"^(.+)_([1-9]\d*)$", candidate)
    if m:
        return m.group(1), int(m.group(2))
    return candidate, 0


def generate_id(
    display_name: str,
    existing_ids: set[str] | list[str],
    *,
    fallback: str = "object",
    prefix: str | None = None,
) -> str:
    """Generate a unique ID from *display_name* within *existing_ids* scope.

    Appends ``_2``, ``_3``, … until the ID is unique.
    If *prefix* is given, the base is ``prefix.base_name``.
    """
    if isinstance(existing_ids, list):
        existing_ids = set(existing_ids)

    base = normalize_id(display_name, fallback=fallback)
    if prefix:
        base = f"{prefix}.{base}"

    candidate = base
    if candidate not in existing_ids:
        return candidate

    # If base itself ends with _N, start from there
    _, existing_suffix = _base_and_suffix(base)
    n = max(2, existing_suffix + 1)

    while True:
        candidate = f"{base}_{n}"
        if candidate not in existing_ids:
            return candidate
        n += 1


def generate_padded_id(
    display_name: str,
    existing_ids: set[str] | list[str],
    *,
    fallback: str = "object",
    prefix: str | None = None,
    width: int = 2,
) -> str:
    """Generate a unique ID with a zero-padded numeric suffix.

    The first ID gets no suffix.  Subsequent collisions get ``_02``, ``_03``,
    etc. (controlled by *width*).
    """
    if isinstance(existing_ids, list):
        existing_ids = set(existing_ids)

    base = normalize_id(display_name, fallback=fallback)
    if prefix:
        base = f"{prefix}.{base}"

    candidate = base
    if candidate not in existing_ids:
        return candidate

    n = 2
    while True:
        candidate = f"{base}_{n:0{width}d}"
        if candidate not in existing_ids:
            return candidate
        n += 1