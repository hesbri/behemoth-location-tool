from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class GenerationSeed:
    mansion_seed: int
    location_id: str
    socket_id: str
    pass_name: str

    def to_int(self) -> int:
        key = f"{self.mansion_seed}|{self.location_id}|{self.socket_id}|{self.pass_name}".encode()
        return int.from_bytes(hashlib.blake2b(key, digest_size=4).digest(), "little")

def should_spawn(seed: GenerationSeed, chance_percent: int) -> bool:
    if chance_percent <= 0:
        return False
    if chance_percent >= 100:
        return True
    rng = random.Random(seed.to_int())
    return rng.randint(1, 100) <= chance_percent
