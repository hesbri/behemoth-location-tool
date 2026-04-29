from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import TypeVar

T = TypeVar("T")


def clone_value(value: T) -> T:
    if hasattr(value, "model_copy"):
        return value.model_copy(deep=True)  # type: ignore[return-value]
    return deepcopy(value)


def models_equal(left: object, right: object) -> bool:
    if hasattr(left, "model_dump") and hasattr(right, "model_dump"):
        return left.model_dump(by_alias=True) == right.model_dump(by_alias=True)  # type: ignore[attr-defined]
    return left == right


def call_if_set(callback: Callable[[], None] | None) -> None:
    if callback is not None:
        callback()
