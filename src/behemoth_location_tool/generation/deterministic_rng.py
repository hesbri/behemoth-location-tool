from __future__ import annotations

import hashlib
import random
from typing import TypeVar

T = TypeVar("T")


def stable_seed_int(
    mansion_seed: int,
    location_id: str,
    socket_id: str,
    pass_name: str,
) -> int:
    key = f"{mansion_seed}|{location_id}|{socket_id}|{pass_name}".encode()
    return int.from_bytes(hashlib.blake2b(key, digest_size=4).digest(), "little")


def roll_spawn_chance(seed: int, chance_percent: int) -> bool:
    if chance_percent <= 0:
        return False
    if chance_percent >= 100:
        return True
    rng = random.Random(seed)
    return rng.randint(1, 100) <= chance_percent


def choose_uniform(seed: int, candidates: list[T]) -> T | None:
    if not candidates:
        return None
    rng = random.Random(seed)
    return rng.choice(candidates)


def choose_weighted(seed: int, candidates: list[tuple[T, int]]) -> T | None:
    if not candidates:
        return None
    total = sum(weight for _item, weight in candidates)
    if total <= 0:
        return None
    rng = random.Random(seed)
    roll = rng.randint(1, total)
    cumulative = 0
    for item, weight in candidates:
        cumulative += weight
        if roll <= cumulative:
            return item
    return candidates[-1][0]
