from __future__ import annotations

from dataclasses import dataclass

from behemoth_location_tool.model.location import LocationInstance, PlacedEntity


@dataclass
class PlacementResultRow:
    socket_id: str
    entity_id: str = ""
    placement_source: str = ""
    reject_reason: str = ""

    @property
    def placed(self) -> bool:
        return bool(self.entity_id)


def build_instance_id(
    location_id: str,
    socket_id: str,
    entity_id: str,
    existing_ids: set[str],
) -> str:
    base = f"{location_id}__{socket_id}__{entity_id}"
    if base not in existing_ids:
        return base
    suffix = 2
    while True:
        candidate = f"{base}__{suffix:02d}"
        if candidate not in existing_ids:
            return candidate
        suffix += 1


def apply_placement_rows(
    location: LocationInstance,
    rows: list[PlacementResultRow],
) -> list[PlacedEntity]:
    existing_ids = {item.instance_id for item in location.placed_entities}
    created: list[PlacedEntity] = []
    for row in rows:
        if not row.placed:
            continue
        instance_id = build_instance_id(location.id, row.socket_id, row.entity_id, existing_ids)
        existing_ids.add(instance_id)
        created.append(
            PlacedEntity(
                instance_id=instance_id,
                entity_id=row.entity_id,
                socket_id=row.socket_id,
                placement_source=row.placement_source,
            )
        )
    location.placed_entities.extend(created)
    return created
