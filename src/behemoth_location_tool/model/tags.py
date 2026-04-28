from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def matches(child_tag: str, parent_tag: str) -> bool:
    child = child_tag.strip()
    parent = parent_tag.strip()
    return child == parent or child.startswith(parent + ".")


def matches_all(entity_tags: set[str], required: list[str]) -> bool:
    return all(any(matches(tag, required_tag) for tag in entity_tags) for required_tag in required)


def matches_none(entity_tags: set[str], forbidden: list[str]) -> bool:
    return all(not any(matches(tag, forbidden_tag) for tag in entity_tags) for forbidden_tag in forbidden)


def _walk_tree(node: Any, prefix: str, out: set[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if not isinstance(key, str) or not key.strip():
                continue
            current = key if not prefix else f"{prefix}.{key}"
            out.add(current)
            _walk_tree(value, current, out)
    elif isinstance(node, list):
        for item in node:
            if isinstance(item, str) and item.strip():
                out.add(item.strip())


def extract_known_tags(data: Any) -> set[str]:
    tags_root = data.get("tags") if isinstance(data, dict) and "tags" in data else data
    known: set[str] = set()
    _walk_tree(tags_root, "", known)
    return known


@dataclass(frozen=True)
class TagIndex:
    known_tags: set[str]

    def is_known(self, tag: str) -> bool:
        value = tag.strip()
        if not value:
            return False
        return any(matches(known, value) or matches(value, known) for known in self.known_tags)
