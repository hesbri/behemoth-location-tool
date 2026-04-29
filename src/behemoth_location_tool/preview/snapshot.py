from __future__ import annotations

from pathlib import Path
from typing import Any

from behemoth_location_tool.io.json_io import write_json
from behemoth_location_tool.model.entity import EntityDefinition
from behemoth_location_tool.model.location import (
    LocationInstance,
    get_effective_background,
    get_effective_layers,
    get_effective_sockets,
)
from behemoth_location_tool.model.project import ProjectConfig
from behemoth_location_tool.model.room import RoomCatalog, RoomCatalogEntry


def build_empty_preview_snapshot(project: ProjectConfig) -> dict[str, Any]:
    return {
        "version": 1,
        "project": {
            "designWidth": project.design_width,
            "designHeight": project.design_height,
            "imageRoot": str(project.image_root).replace("\\", "/"),
        },
        "activeLocationId": "",
        "entities": [],
        "locations": [],
        "debug": {
            "showSockets": True,
            "showClickableRects": True,
            "showSafeArea": False,
            "showLayerNames": False,
        },
    }


def build_room_catalog_snapshot(
    project: ProjectConfig,
    room: RoomCatalogEntry,
) -> dict[str, Any]:
    """Build a preview snapshot for a room catalog entry.

    Uses a synthetic location ID: preview_room_catalog_<room_id>
    """
    snapshot_id = f"preview_room_catalog_{room.id}"
    image_root = str(project.image_root).replace("\\", "/")

    # Build sockets list
    sockets = []
    for sock in room.sockets:
        socket_data: dict[str, Any] = {
            "id": sock.id,
            "name": sock.name,
            "x": sock.x,
            "y": sock.y,
            "rotation": sock.rotation,
            "scale": sock.scale,
            "pivotMode": sock.pivot_mode.value,
            "layer": sock.layer,
            "sortOrder": sock.sort_order,
            "ambientSpawnChance": sock.ambient_spawn_chance,
        }
        if sock.allowed_entity_ids:
            socket_data["allowedEntityIds"] = sock.allowed_entity_ids
        if sock.required_tags:
            socket_data["requiredTags"] = sock.required_tags
        if sock.forbidden_tags:
            socket_data["forbiddenTags"] = sock.forbidden_tags
        sockets.append(socket_data)

    # Build layers
    layers: dict[str, Any] = {}
    if room.layers.mode == "custom" and room.layers.order:
        layers = {
            "mode": "custom",
            "order": room.layers.order,
        }
    else:
        layers = {
            "mode": "project_default",
        }
    if room.layers.overrides:
        layers["overrides"] = room.layers.overrides

    # Build location entry
    location: dict[str, Any] = {
        "id": snapshot_id,
        "roomId": room.id,
        "backgroundImage": room.background_image or "",
        "designSize": {"w": room.design_size.w, "h": room.design_size.h},
        "sockets": sockets,
        "layers": layers,
    }

    return {
        "version": 1,
        "project": {
            "designWidth": project.design_width,
            "designHeight": project.design_height,
            "imageRoot": image_root,
        },
        "activeLocationId": snapshot_id,
        "entities": [],
        "locations": [location],
        "debug": {
            "showSockets": True,
            "showClickableRects": True,
            "showSafeArea": False,
            "showLayerNames": False,
        },
    }


def build_location_snapshot(
    project: ProjectConfig,
    location: LocationInstance,
    *,
    catalog: RoomCatalog | None = None,
    entities: list[EntityDefinition] | None = None,
    project_layers: list[str] | None = None,
) -> dict[str, Any]:
    """Build a preview snapshot for an actual location instance.

    Includes sockets, exits with clickable rects, placed entities.
    Uses effective background (override or inherited from catalog).
    Uses effective sockets (inherited from catalog or overridden).
    Uses effective layers (location custom or project default).
    Includes referenced entities needed to render placedEntities/exits.
    """
    image_root = str(project.image_root).replace("\\", "/")
    effective_bg = get_effective_background(location, catalog)
    effective_sockets = get_effective_sockets(location, catalog)
    effective_layer_list = get_effective_layers(location, project_layers)

    # Build sockets
    sockets = []
    for sock in effective_sockets:
        socket_data: dict[str, Any] = {
            "id": sock.id,
            "name": sock.name,
            "x": sock.x,
            "y": sock.y,
            "rotation": sock.rotation,
            "scale": sock.scale,
            "pivotMode": sock.pivot_mode.value,
            "layer": sock.layer,
            "sortOrder": sock.sort_order,
            "ambientSpawnChance": sock.ambient_spawn_chance,
        }
        if sock.allowed_entity_ids:
            socket_data["allowedEntityIds"] = sock.allowed_entity_ids
        if sock.required_tags:
            socket_data["requiredTags"] = sock.required_tags
        if sock.forbidden_tags:
            socket_data["forbiddenTags"] = sock.forbidden_tags
        sockets.append(socket_data)

    # Build exits
    exits = []
    for ex in location.exits:
        exit_data: dict[str, Any] = {
            "id": ex.id,
            "entityId": ex.entity_id,
            "targetLocationId": ex.target_location_id,
            "socketId": ex.socket_id,
            "layer": ex.layer,
            "tags": ex.tags,
            "locked": ex.locked,
        }
        if ex.clickable_rect is not None:
            exit_data["clickableRect"] = {
                "x": ex.clickable_rect.x,
                "y": ex.clickable_rect.y,
                "w": ex.clickable_rect.w,
                "h": ex.clickable_rect.h,
            }
        exit_data["conditions"] = {
            "requiresTags": ex.conditions.requires_tags,
            "forbiddenTags": ex.conditions.forbidden_tags,
        }
        exits.append(exit_data)

    # Build placed entities
    placed = []
    for pe in location.placed_entities:
        placed.append({
            "instanceId": pe.instance_id,
            "entityId": pe.entity_id,
            "socketId": pe.socket_id,
            "layer": pe.layer or "",
            "sortOrder": pe.sort_order,
        })

    # Build layers
    if location.layers:
        layers: dict[str, Any] = {"mode": "custom", "order": location.layers}
    else:
        layers = {"mode": "project_default", "order": effective_layer_list}

    # Build location entry
    loc_data: dict[str, Any] = {
        "id": location.id,
        "catalogRoomId": location.catalog_room_id,
        "backgroundImage": effective_bg or "",
        "designSize": {"w": location.design_size.w, "h": location.design_size.h},
        "sockets": sockets,
        "exits": exits,
        "placedEntities": placed,
        "layers": layers,
    }

    # Collect referenced entity IDs from exits and placed entities
    referenced_entity_ids: set[str] = set()
    for ex in location.exits:
        if ex.entity_id:
            referenced_entity_ids.add(ex.entity_id)
    for pe in location.placed_entities:
        if pe.entity_id:
            referenced_entity_ids.add(pe.entity_id)

    # Build entity snapshots for referenced entities
    entity_list: list[dict[str, Any]] = []
    if entities:
        entity_map = {e.id: e for e in entities}
        for eid in sorted(referenced_entity_ids):
            if eid in entity_map:
                ent = entity_map[eid]
                ent_data: dict[str, Any] = {"id": ent.id, "tags": ent.tags}
                if ent.render:
                    ent_data["render"] = {
                        "image": ent.render.sprite,
                        "clickableRect": (
                            {"x": ent.render.clickable_rect.x, "y": ent.render.clickable_rect.y,
                             "w": ent.render.clickable_rect.w, "h": ent.render.clickable_rect.h}
                            if ent.render.clickable_rect else None
                        ),
                    }
                entity_list.append(ent_data)

    return {
        "version": 1,
        "project": {
            "designWidth": project.design_width,
            "designHeight": project.design_height,
            "imageRoot": image_root,
        },
        "activeLocationId": location.id,
        "entities": entity_list,
        "locations": [loc_data],
        "debug": {
            "showSockets": True,
            "showClickableRects": True,
            "showSafeArea": False,
            "showLayerNames": False,
        },
    }


def write_preview_snapshot(path: Path, snapshot: dict[str, Any]) -> None:
    write_json(path, snapshot)
