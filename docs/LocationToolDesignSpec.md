# Behemoth Location Authoring Tool — Design Spec v0.1

> Note (current project direction): despite historical references in this draft spec, the
> active tool implementation is v2-only. Normal-flow v1 fallback/import/migration support is
> intentionally out of scope and should remain disabled.

## 1. Goal

Build a standalone Python-based authoring tool for mansion-room locations in Behemoth.

The tool authors:

- room catalog entries
- actual mansion location instances
- sockets
- exits
- render layers
- entity/spawnable catalog data
- deterministic generated room contents
- validation data
- runtime-preview snapshots

The tool must preview rooms through the actual Behemoth runtime render path, not through an independent Python renderer. The Python app owns editable authoring data. The game/editor runtime owns preview interpretation, ECS spawning, hit-testing, and rendering.

The tool lives in its own git repository, but project-local metadata is stored inside the game project under a gitignored folder.

---

## 2. High-level architecture

### 2.1 Components

#### A. Python Authoring App

Responsibilities:

- Main editor UI.
- Owns the editable data model.
- Loads and saves JSON files.
- Provides undo/redo.
- Maintains room catalog, entity catalog, location instances, graph view, sockets, layers, exits, and generation rules.
- Runs validation.
- Launches the game preview runtime.
- Sends preview snapshots to the game runtime.
- Receives runtime validation/render/debug feedback.

#### B. Behemoth Preview Runtime

A special game/editor mode.

Responsibilities:

- Loads preview snapshots from the Python tool.
- Builds ECS entities using the same runtime code paths as the game.
- Uses the same renderer as the game.
- Displays the room in a separate game window.
- Shows ImGui debug overlays for sockets, clickable rectangles, render layers, selected entities, generated placements, and validation diagnostics.
- Provides runtime validation feedback to the Python tool.
- Does not author or save canonical data.

#### C. Shared JSON Data

The canonical data remains JSON-based.

The new format should be `version: 2`.

Main files:

```text
data/behemoth/game/entities.json
data/behemoth/game/entity_modules/*.json
data/behemoth/game/room_catalog.json
data/behemoth/game/locations.json
data/behemoth/game/tags.json
```

Tool-local project files:

```text
<game-root>/.behemoth_tool/project.json
<game-root>/.behemoth_tool/editor_settings.json
<game-root>/.behemoth_tool/preview/current_snapshot.json
<game-root>/.behemoth_tool/cache/
<game-root>/.behemoth_tool/schemas/
```

`.behemoth_tool/` must be ignored by the game git repo.

---

## 3. Python/runtime communication

Use local TCP control messages plus file-based payloads.

### 3.1 Recommended model

The Python tool starts a local TCP server, then launches the game preview runtime with connection parameters:

```text
Behemoth.exe --editor-preview --editor-host 127.0.0.1 --editor-port <port> --project-root <path>
```

The game connects to the Python tool as a client.

This is simple because Python can host the control server easily, and the game only needs a lightweight TCP client.

### 3.2 Payload strategy

Large preview payloads should not be sent directly over TCP.

Python writes:

```text
<game-root>/.behemoth_tool/preview/current_snapshot.json
```

Then sends:

```json
{
  "type": "load_preview_snapshot",
  "path": ".behemoth_tool/preview/current_snapshot.json"
}
```

The game loads the snapshot, rebuilds preview ECS data, and responds with:

```json
{
  "type": "preview_loaded",
  "ok": true,
  "diagnostics": []
}
```

### 3.3 Message types

Minimum protocol:

```json
{
  "type": "hello",
  "toolProtocolVersion": 1
}
```

```json
{
  "type": "load_preview_snapshot",
  "path": ".behemoth_tool/preview/current_snapshot.json"
}
```

```json
{
  "type": "select_object",
  "objectType": "socket",
  "id": "npc_left"
}
```

```json
{
  "type": "set_debug_overlay",
  "showSockets": true,
  "showClickableRects": true,
  "showSafeArea": false,
  "showLayerNames": false
}
```

```json
{
  "type": "validate_runtime"
}
```

```json
{
  "type": "runtime_validation_result",
  "errors": [],
  "warnings": []
}
```

---

## 4. Project model

### 4.1 Project root

A Behemoth authoring project points at a game root.

Example:

```json
{
  "version": 1,
  "projectName": "Behemoth Mansion",
  "gameRoot": "D:/Projects/Behemoth",
  "gameExecutable": "D:/Projects/Behemoth/bin/Behemoth.exe",
  "contentRoot": "data/behemoth",
  "imageRoot": "data/behemoth/assets/images",
  "gameDataRoot": "data/behemoth/game",
  "toolDataRoot": ".behemoth_tool",
  "designWidth": 1920,
  "designHeight": 1080,
  "previewPort": 38171
}
```

### 4.2 Coordinate system

All room authoring uses unified project design-space coordinates.

Default:

```json
{
  "designWidth": 1920,
  "designHeight": 1080
}
```

The game renders this at its own runtime resolution using its viewport/design-space mapping.

Each room can override reference dimensions only if needed, but v1 should strongly prefer one global design space.

---

## 5. Canonical data files

### 5.1 `entities.json`

`entities.json` is a manifest, not a giant entity file.

Example:

```json
{
  "version": 2,
  "includes": [
    "entity_modules/items.json",
    "entity_modules/characters.json",
    "entity_modules/furniture.json",
    "entity_modules/exits.json"
  ]
}
```

Each included file contains shared entity definitions.

This gives modularity without losing a unified entity model.

### 5.2 Entity module file

Example:

```json
{
  "version": 2,
  "entities": [
    {
      "id": "lantern",
      "kind": "item",
      "name": "Rusty Lantern",
      "description": "A dented lantern, still functional.",
      "tags": [
        "entity.spawnable",
        "item.pickable",
        "item.light_source",
        "style.old_mansion"
      ],
      "render": {
        "sprite": "gameplay/items/lantern.png",
        "pivot": {
          "mode": "bottom"
        },
        "clickableRect": {
          "x": -32,
          "y": -96,
          "w": 64,
          "h": 96
        },
        "defaultLayer": "front_props"
      },
      "spawnRules": {
        "requiredContextTags": [],
        "forbiddenContextTags": [],
        "exclusiveGroups": [],
        "savePolicy": "persistent"
      },
      "interactions": [
        {
          "type": "action.interact.take",
          "needs_tags": ["item.pickable"],
          "effects": [
            {
              "effect": "effect.transfer",
              "params": {
                "effectParam.from": "effectTarget.world",
                "effectParam.to": "effectTarget.player"
              }
            }
          ]
        }
      ]
    }
  ]
}
```

### 5.3 Entity definition fields

Required:

```json
{
  "id": "string",
  "kind": "item | character | prop | furniture | exit | clue | container | custom",
  "name": "string",
  "description": "string",
  "tags": []
}
```

Optional:

```json
{
  "render": {},
  "spawnRules": {},
  "interactions": [],
  "character": {},
  "inventory": [],
  "editor": {}
}
```

### 5.4 Character entities

Characters should use the same entity model, with character-specific data under `character`.

Example:

```json
{
  "id": "gerald",
  "kind": "character",
  "name": "Old Man Gerald",
  "description": "Sunken eyes watch you from the corner.",
  "tags": [
    "entity.spawnable",
    "character.talkable",
    "npc.named"
  ],
  "render": {
    "defaultLayer": "characters"
  },
  "character": {
    "renderMode": "layered",
    "generate": {
      "mandatory": ["male"],
      "optional": []
    },
    "character_sheet": {
      "age": "72",
      "race": "Human",
      "profession": "Caretaker",
      "origin": "The mansion grounds",
      "family": "No close family remains.",
      "personality": "Haunted, secretive, exhausted, and protective.",
      "catchphrases": "Keep away from the library.",
      "character_notes": "Gerald witnessed something impossible in the upstairs library.",
      "world_lore": "The mansion is old, damp, and full of rooms that feel abandoned."
    }
  },
  "interactions": [
    {
      "type": "action.interact.talk",
      "effects": [
        {
          "effect": "effect.advance_dialogue",
          "params": {}
        }
      ]
    }
  ]
}
```

NPC rendering remains the responsibility of the entity definition/runtime, not the location tool.

---

## 6. Room catalog

### 6.1 Purpose

`room_catalog.json` defines reusable room templates/archetypes.

Examples:

- `entrance_hall`
- `kitchen`
- `library`
- `dining_room`
- `servants_quarters`
- `gallery`
- `study`

These are not necessarily actual visited locations. They are source templates used to create actual mansion location instances.

### 6.2 Example

```json
{
  "version": 2,
  "rooms": [
    {
      "id": "catalog.entrance_hall.large",
      "name": "Large Entrance Hall",
      "description": "A broad entry chamber beneath a high ceiling.",
      "backgroundImage": "world/backgrounds/entrance_hall.png",
      "designSize": {
        "w": 1920,
        "h": 1080
      },
      "tags": [
        "room.entrance_hall",
        "room.indoors",
        "style.victorian",
        "mansion.public"
      ],
      "layers": {
        "mode": "project_default",
        "overrides": []
      },
      "sockets": [
        {
          "id": "socket_npc_left",
          "name": "NPC Left",
          "description": "A good standing position for an NPC near the left wall.",
          "x": 620,
          "y": 660,
          "rotation": 0,
          "scale": 1,
          "pivotMode": "bottom",
          "layer": "characters",
          "sortOrder": 0,
          "requiredTags": ["character.talkable"],
          "forbiddenTags": [],
          "ambientSpawnChance": 0,
          "ambientRule": {
            "mode": "tag_query",
            "requiredTags": ["character.talkable"],
            "forbiddenTags": []
          },
          "allowedEntityIds": [],
          "editor": {
            "notes": "Reserved for story/NPC placement. Ambient chance is intentionally zero."
          }
        }
      ]
    }
  ]
}
```

---

## 7. Actual mansion locations

### 7.1 Purpose

`locations.json` is adventure-specific.

It contains actual mansion location instances and their initial resolved state.

The game loads `locations.json` as the initial world state. During play, entities may mutate, move, be removed, be added, or change state. Savegames persist that mutated runtime state.

The room catalog is an authoring source. `locations.json` is the runtime initial state.

### 7.2 Example

```json
{
  "version": 2,
  "startLocation": "entrance_hall_01",
  "mansionSeed": 123456789,
  "graph": {
    "nodes": [
      {
        "locationId": "entrance_hall_01",
        "x": 400,
        "y": 300
      },
      {
        "locationId": "library_01",
        "x": 400,
        "y": 120
      }
    ]
  },
  "locations": [
    {
      "id": "entrance_hall_01",
      "catalogRoomId": "catalog.entrance_hall.large",
      "name": "Entrance Hall",
      "description": "A dimly lit hallway. Dust floats in the air.",
      "backgroundImage": "world/backgrounds/entrance_hall.png",
      "designSize": {
        "w": 1920,
        "h": 1080
      },
      "tags": [
        "room.entrance_hall",
        "room.indoors",
        "style.victorian"
      ],
      "layers": [
        "background",
        "exterior_view",
        "back_wall",
        "exit_behind",
        "back_props",
        "characters",
        "front_props",
        "exit_front",
        "foreground"
      ],
      "sockets": [],
      "exits": [],
      "placedEntities": []
    }
  ]
}
```

### 7.3 Consolidated/resolved data

When a location references a room catalog entry, the tool should resolve the catalog entry into the location instance.

The location should retain:

- `catalogRoomId`
- resolved `backgroundImage`
- resolved `designSize`
- resolved `tags`
- resolved `layers`
- resolved `sockets`
- generated default exits
- generated/applied placed entities

This makes `locations.json` self-sufficient for the game runtime.

Current implementation note: `locations.json` also retains the editor metadata
fields `backgroundOverridden` and `socketOverridden`. They are v2 schema fields
used by the Python tool to preserve catalog-inheritance intent while keeping the
resolved runtime data in the same file. The game runtime may ignore these fields.

---

## 8. Mansion graph view

The tool must include a Graph tab based on `locations.json`.

### 8.1 Purpose

The graph view displays actual mansion location instances, not room catalog entries.

It shows:

- location nodes
- start location
- exit links
- missing reciprocal links
- unreachable rooms
- default/back exits
- locked exits
- invalid targets

### 8.2 Storage

Graph layout positions are stored in `locations.json`, not only in tool-local metadata.

Recommended shape:

```json
{
  "graph": {
    "nodes": [
      {
        "locationId": "entrance_hall_01",
        "x": 400,
        "y": 300
      },
      {
        "locationId": "library_01",
        "x": 400,
        "y": 120
      }
    ]
  }
}
```

The game runtime can ignore this block.

### 8.3 Graph behavior

V1 graph features:

- Show location nodes.
- Drag nodes.
- Save graph positions.
- Show directed/undirected links from exit data.
- Highlight missing reciprocal exits.
- Highlight unreachable locations.
- Double-click node to open location editor.
- Show start location badge.
- Show warning badge if location lacks required default back exit.

Mansion procedural layout generation is out of scope for v1.

---

## 9. Exits

### 9.1 Directional commands are removed

The old `north/east/south/west` exit model should be deprecated.

All exits are clickable entities.

### 9.2 Exit data

```json
{
  "id": "exit_to_library",
  "entityId": "exit.old_wooden_door",
  "targetLocationId": "library_01",
  "socketId": "socket_exit_north",
  "layer": "exit_front",
  "tags": [
    "exit.door",
    "exit.default_back"
  ],
  "locked": false,
  "clickableRect": {
    "x": -64,
    "y": -180,
    "w": 128,
    "h": 180
  },
  "conditions": {
    "requiresTags": [],
    "forbiddenTags": []
  }
}
```

### 9.3 Default bottom exit

When a non-start location instance is created, the tool automatically creates a default bottom/back exit.

Rules:

- Every non-start location must have a default bottom/back exit.
- The default exit is a real exit entity in location data.
- It has a configurable socket position, especially X coordinate.
- It can be moved.
- It can be locked.
- It can be retagged.
- It can be configured freely.
- It can only be removed from the start location.
- Validation error if any non-start location lacks it.

Suggested tag:

```text
exit.default_back
```

### 9.4 Reciprocal exits

For manually authored connections, validation should treat missing reciprocal exits as errors.

Example:

- `library_01` has exit to `entrance_hall_01`
- but `entrance_hall_01` has no exit back to `library_01`

Error:

```text
Location 'library_01' links to 'entrance_hall_01', but no reciprocal exit exists.
```

---

## 10. Sockets

### 10.1 Purpose

Sockets are spawn pivots.

They are not interactable by themselves. If something must be selectable/interactable, an entity must spawn there.

### 10.2 Socket transform

Sockets use:

```json
{
  "x": 960,
  "y": 640,
  "rotation": 0,
  "scale": 1
}
```

### 10.3 Pivot mode

Each socket defines how attached spawnables align to it:

```json
"pivotMode": "bottom"
```

Allowed values:

```text
bottom
center
spawnable_default
```

Meaning:

- `bottom`: socket position maps to the spawnable’s bottom pivot.
- `center`: socket position maps to the spawnable’s center pivot.
- `spawnable_default`: socket uses the entity's default pivot.

The spawnable may also define its own default pivot. Socket pivot mode wins for placement unless the socket says to use the spawnable default.

### 10.4 Socket fields

```json
{
  "id": "socket_npc_left",
  "name": "NPC Left",
  "description": "Good standing position for a character.",
  "x": 620,
  "y": 660,
  "rotation": 0,
  "scale": 1,
  "pivotMode": "bottom",
  "layer": "characters",
  "sortOrder": 0,
  "requiredTags": ["character.talkable"],
  "forbiddenTags": [],
  "ambientSpawnChance": 0,
  "ambientRule": {
    "mode": "tag_query",
    "requiredTags": ["character.talkable"],
    "forbiddenTags": []
  },
  "allowedEntityIds": [],
  "editor": {
    "notes": "Reserved for explicit NPC placement."
  }
}
```

### 10.5 Socket categories

Sockets do not use hardcoded categories.

Categories are expressed through tags.

Examples:

```text
socket.npc
socket.furniture
socket.exit
socket.clue
socket.small_item
socket.wall
socket.floor
socket.foreground
```

---

## 11. Spawn system

The tool and runtime should use two placement stages.

### 11.1 Stage A — Placement Pass

Explicit placement.

Used by:

- designers
- future procedural mansion generation
- future mystery/clue generation
- scripted room setup
- required NPC placement
- required item placement

The Placement Pass can place entities into sockets even if the socket’s `ambientSpawnChance` is `0`.

UI wording:

> Explicit Placement ignores Ambient Spawn Chance.

### 11.2 Stage B — Ambient Fill Pass

Random filler pass.

Used for:

- furniture
- non-critical props
- decorative interactables
- optional clutter

Only sockets not already filled by Stage A are considered.

The Ambient Fill Pass uses:

```json
"ambientSpawnChance": 75
```

If the roll succeeds, it chooses an entity from either:

- weighted explicit entity list
- tag query

### 11.3 Ambient rule: weighted entity list

```json
{
  "ambientSpawnChance": 80,
  "ambientRule": {
    "mode": "weighted_entity_list",
    "entries": [
      {
        "entityId": "old_armchair",
        "weight": 40
      },
      {
        "entityId": "small_table",
        "weight": 35
      },
      {
        "entityId": "umbrella_stand",
        "weight": 25
      }
    ]
  }
}
```

Weights must sum to 100.

Validation error if they do not.

### 11.4 Ambient rule: tag query

```json
{
  "ambientSpawnChance": 60,
  "ambientRule": {
    "mode": "tag_query",
    "requiredTags": [
      "entity.spawnable",
      "furniture.seating",
      "style.victorian"
    ],
    "forbiddenTags": [
      "furniture.modern"
    ]
  }
}
```

For v1, tag-query matches can be selected uniformly.

No global spawnable weights in v1.

---

## 12. Tag filtering

### 12.1 Matching rule

A spawnable can spawn in a socket only if:

1. It has all required tags from the location.
2. It has all required tags from the socket.
3. It has all required tags from the ambient rule or explicit placement request.
4. It has none of the forbidden tags from the location.
5. It has none of the forbidden tags from the socket.
6. It has none of the forbidden tags from the ambient rule or explicit placement request.
7. Its own `spawnRules.requiredContextTags` are satisfied by the combined location/socket context.
8. Its own `spawnRules.forbiddenContextTags` are not present in the combined location/socket context.
9. Its exclusive groups have not already been used in this location instance.

### 12.2 No deep copy of location filters

Location filters and socket filters are combined at evaluation time.

Sockets do not copy location filters.

Changing a location tag/filter should affect all socket evaluations immediately.

### 12.3 Hierarchical matching

Tag matching must be hierarchical.

Example:

```text
furniture.chair.armchair
```

satisfies:

```text
furniture.chair
```

This requires the tool validator and the runtime validator to use the same tag hierarchy semantics.

### 12.4 Spawnable context requirements

Spawnables can define rules about where they are allowed to appear.

Example:

```json
{
  "spawnRules": {
    "requiredContextTags": ["room.indoors", "style.victorian"],
    "forbiddenContextTags": ["room.exterior", "room.burned"],
    "exclusiveGroups": ["unique.fireplace"],
    "savePolicy": "persistent"
  }
}
```

---

## 13. Exclusive groups

Use exclusive groups to enforce “only one of this type per location”.

Do not mutate location tags during generation.

Example:

```json
{
  "id": "large_fireplace",
  "tags": [
    "entity.spawnable",
    "furniture.fireplace"
  ],
  "spawnRules": {
    "exclusiveGroups": [
      "unique.fireplace"
    ]
  }
}
```

Generation maintains a transient set per location:

```text
usedExclusiveGroups = { "unique.fireplace" }
```

If another candidate has `unique.fireplace`, it is rejected.

This supports rules like:

- only one fireplace per room
- only one large clock per room
- only one piano per room
- only one hidden safe per room
- only one major clue container per room

---

## 14. Placed entities

### 14.1 Purpose

`placedEntities` stores the resolved initial state of a location.

The game should not regenerate the room every time the player enters. Generation happens in the tool or during mansion creation, then is stored as initial state.

### 14.2 Example

```json
{
  "placedEntities": [
    {
      "instanceId": "entrance_hall_01__socket_npc_left__gerald",
      "entityId": "gerald",
      "socketId": "socket_npc_left",
      "layer": "characters",
      "sortOrder": 0,
      "savePolicy": "persistent",
      "placementSource": "explicit"
    },
    {
      "instanceId": "entrance_hall_01__socket_table_right__small_table",
      "entityId": "small_table",
      "socketId": "socket_table_right",
      "layer": "front_props",
      "sortOrder": 0,
      "savePolicy": "persistent",
      "placementSource": "ambient_fill"
    }
  ]
}
```

### 14.3 Required fields

```json
{
  "instanceId": "string",
  "entityId": "string",
  "socketId": "string"
}
```

### 14.4 Optional fields

```json
{
  "layer": "string",
  "sortOrder": 0,
  "savePolicy": "persistent | transient | regenerate_on_new_game",
  "placementSource": "explicit | ambient_fill | manual | runtime"
}
```

Default:

```json
"savePolicy": "persistent"
```

### 14.5 Socket identity at runtime

Every spawned entity should know:

- `LocationId`
- `SocketId`
- `PlacedInstanceId`
- `LayerId`

This enables future interactions like:

- chest opens and spawns key in same socket
- cupboard moves and reveals hidden exit behind it
- container state changes what is visible in the socket
- debug tools show where an entity came from

---

## 15. Render layers

### 15.1 Project default layers

Use project-level default layers.

Recommended default mansion stack:

```json
[
  "background",
  "exterior_view",
  "back_wall",
  "exit_behind",
  "back_props",
  "characters",
  "front_props",
  "exit_front",
  "foreground"
]
```

`debug_overlay` is not a gameplay layer. It is ImGui/tool-only.

### 15.2 Per-room overrides

Rooms may override or extend layers, but v1 should encourage project defaults.

Example:

```json
{
  "layers": {
    "mode": "custom",
    "order": [
      "background",
      "back_wall",
      "custom_mirror_reflection",
      "characters",
      "foreground"
    ]
  }
}
```

### 15.3 Sorting

Render order:

1. layer order
2. explicit `sortOrder`
3. optional Y fallback

Since rooms are side-view and Y represents height rather than true depth, Y sorting must not be the primary sorting rule.

### 15.4 Hit-testing

Clickable hit-testing follows layer order.

Highest rendered clickable entity wins.

Tie-breakers:

1. highest layer
2. highest `sortOrder`
3. latest/explicit interaction priority
4. stable instance ID order

---

## 16. Clickable rectangles

V1 supports rectangles only.

Spawnables define clickable rectangles relative to their pivot.

Example:

```json
{
  "render": {
    "clickableRect": {
      "x": -64,
      "y": -160,
      "w": 128,
      "h": 160
    }
  }
}
```

The runtime transforms this using:

- socket position
- socket rotation
- socket scale
- pivot mode
- entity render scale

V1 may ignore rotation for clickable rect hit-testing if needed, but the data model should preserve rotation.

Tool and runtime must support a debug toggle:

```text
Show clickable volumes
```

---

## 17. Entity render data

### 17.1 Static sprite entity

```json
{
  "render": {
    "sprite": "world/furniture/old_armchair.png",
    "defaultLayer": "front_props",
    "pivot": {
      "mode": "bottom",
      "x": 0,
      "y": 0
    },
    "clickableRect": {
      "x": -90,
      "y": -140,
      "w": 180,
      "h": 140
    }
  }
}
```

### 17.2 Layered character entity

```json
{
  "render": {
    "defaultLayer": "characters"
  },
  "character": {
    "renderMode": "layered",
    "generate": {
      "mandatory": ["male"],
      "optional": []
    }
  }
}
```

The location tool does not need to know how the layered character is rendered beyond preview/runtime validation.

---

## 18. Conditions

Do not fully implement runtime conditions in v1.

Reserve the schema shape.

```json
{
  "conditions": {
    "requiresTags": [],
    "forbiddenTags": [],
    "requiresFlags": [],
    "forbiddenFlags": []
  }
}
```

V1 behavior:

- tag conditions can be validated
- flag conditions can be stored
- flag conditions do not need full preview simulation
- preview can display “flag conditions not evaluated” warning

This avoids turning the location editor into a full game-state simulator too early.

---

## 19. Generation workflow

### 19.1 Generate tab

The tool includes a Generate tab for the active location.

Workflow:

1. Select location instance.
2. Pick generation seed or use mansion seed.
3. Run generation.
4. Preview result without modifying `locations.json`.
5. Inspect generated placements.
6. Apply result.
7. Applied result writes to `locations.json`.

### 19.2 Determinism

Generation is deterministic from:

```text
mansionSeed + locationId + socketId + generationPass
```

The mansion has one seed.

```json
{
  "mansionSeed": 123456789
}
```

### 19.3 No runtime regeneration on room entry

The game must not regenerate rooms when entering them.

The game loads initial `placedEntities`.

Savegames persist runtime mutations after play begins.

---

## 20. Tool UI

### 20.1 Main tabs

Recommended tabs:

1. Project
2. Room Catalog
3. Locations
4. Graph
5. Entities / Spawnables
6. Generate
7. Validate
8. Preview / Runtime

### 20.2 Room Catalog tab

Used to create and edit reusable room entries.

Features:

- create room catalog entry
- assign background
- edit room name/description
- edit room tags
- edit layers
- add/edit/delete sockets
- configure socket transform
- configure socket pivot mode
- configure socket layer
- configure socket ambient spawn chance
- configure socket ambient rule
- configure socket notes
- preview room catalog entry

### 20.3 Locations tab

Used to edit actual mansion location instances.

Features:

- create location from room catalog entry
- set location ID
- set display name
- set description
- override tags
- inspect resolved sockets/layers
- edit default exit
- edit placed entities
- open Generate tab for selected location
- open live preview

### 20.4 Graph tab

Used to view actual mansion layout.

Features:

- graph nodes from `locations.json`
- drag node positions
- show exit links
- show reciprocal-link status
- show unreachable status
- show start location
- open selected location
- display validation badges

### 20.5 Entities / Spawnables tab

Used to edit shared entity catalog.

Features:

- list included entity module files
- create entity
- edit entity kind
- edit tags
- edit sprite
- edit clickable rectangle
- edit render defaults
- edit spawn rules
- edit interactions
- validate entity assets
- preview sprite bounds/pivot

### 20.6 Generate tab

Used to test and apply procedural room filling.

Features:

- run Placement Pass
- run Ambient Fill Pass
- show generated placed entities
- show rejected candidates with reasons
- show exclusive group conflicts
- preview result
- Apply to `locations.json`

### 20.7 Validate tab

Dedicated panel for all errors/warnings.

Sources:

- JSON schema validation
- Python semantic validation
- asset validation
- runtime validation from game preview mode

---

## 21. Undo/redo

The Python tool must support undo/redo from day one.

Use command-based undo/redo.

Examples:

- add socket
- move socket
- edit socket tags
- change background
- add entity
- change clickable rect
- generate preview result
- apply generated result
- move graph node
- add exit
- delete exit

Do not rely on raw file snapshots only. Fine-grained commands make the editor usable.

Autosave can be added later, but should not replace explicit Save.

---

## 22. Validation

### 22.1 Validation levels

Each diagnostic has:

```json
{
  "severity": "error | warning | info",
  "code": "string",
  "message": "string",
  "file": "string",
  "objectId": "string"
}
```

### 22.2 Errors

Errors block export or should make export clearly unsafe.

Required errors:

- duplicated location ID
- duplicated entity ID
- duplicated room catalog ID
- duplicated socket ID inside same room/location
- invalid JSON
- invalid schema
- missing referenced entity ID
- missing referenced room catalog ID
- missing referenced socket ID
- missing target location ID
- missing reciprocal exit
- unreachable room
- non-start location lacks default/back exit
- weighted list does not sum to 100
- invalid tag reference
- invalid layer reference
- startLocation does not exist

### 22.3 Warnings

Warnings do not block export.

Required warnings:

- missing background image
- missing sprite image
- socket has no matching spawnables
- entity has no clickable rectangle but is interactable
- flag condition stored but not evaluated in preview
- room overrides project design size
- location has no sockets
- location has no exits
- entity marked spawnable but has no render data
- exclusive group referenced by only one entity
- ambient spawn chance is 0 but ambient rule is configured

### 22.4 Runtime validation

The Python tool sends a validation request to the preview runtime.

The game runtime checks:

- C++ parser compatibility
- ECS construction
- layer resolution
- render component construction
- texture load success where possible
- clickable rect to `DesignBoundsComp`
- generated character preview compatibility
- interaction data compatibility

The result is returned to Python and shown in the Validate tab.

---

## 23. JSON Schema

Use JSON Schema.

Required schema files:

```text
.behemoth_tool/schemas/entities.schema.json
.behemoth_tool/schemas/room_catalog.schema.json
.behemoth_tool/schemas/locations.schema.json
.behemoth_tool/schemas/tags.schema.json
```

JSON Schema catches structural errors.

Custom validators catch semantic errors.

Do both.

---

## 24. Runtime/C++ requirements

This is not the full C++ implementation plan, but the design depends on these runtime changes.

### 24.1 Editor preview mode

Add launch mode:

```text
--editor-preview
```

Supports:

- TCP connection to Python host
- loading preview snapshot files
- hot-rebuilding preview ECS
- rendering selected location
- returning diagnostics

### 24.2 Map loader v2

Add support for `locations.json` version 2.

Must load:

- actual location instances
- resolved room data
- sockets
- render layers
- clickable exits
- placed entities
- graph data ignored by runtime

Keep version 1 loader as legacy fallback.

### 24.3 Entity loader

Add shared entity definition loader.

Must support:

- `entities.json` include manifest
- entity modules
- item-like entities
- character-like entities
- furniture/prop entities
- exit entities
- interactions
- render data
- spawn rules

### 24.4 Socket/location components

Add components similar to:

```cpp
struct SocketIdComp
{
    SID SocketId;
};

struct PlacedInstanceIdComp
{
    SID InstanceId;
};

struct RenderLayerComp
{
    SID LayerId;
    int SortOrder = 0;
};

struct ClickableRectComp
{
    int X;
    int Y;
    int W;
    int H;
};

struct PivotComp
{
    EPivotMode Mode;
};
```

Exact naming can differ.

### 24.5 Scene layout replacement

`Scene::RebuildLayoutCache()` must stop distributing characters evenly and items left-to-right when v2 authored placement is active.

Instead:

- load placed entity socket
- resolve socket transform
- resolve entity sprite/layer data
- compute design bounds
- sort by layer
- render in layer order

Keep old auto layout as legacy version 1 fallback.

### 24.6 Selection/hit-testing

Selection must use clickable rectangles/design bounds from placed entities and exits.

Hit-test order follows render layer order.

Directional movement commands are deprecated for v2 locations.

Movement happens by interacting with exit entities.

### 24.7 ImGui debug

Runtime preview/debug mode must include toggles:

- show sockets
- show socket names
- show clickable volumes
- show render layers
- show safe area
- show placed instance IDs
- show selected entity data
- show location entity data
- show generation results
- show validation diagnostics

---

## 25. Preview snapshot format

The preview snapshot is a temporary file written by Python.

It does not need to be identical to final game data, but should be close.

Example:

```json
{
  "version": 1,
  "project": {
    "designWidth": 1920,
    "designHeight": 1080,
    "imageRoot": "data/behemoth/assets/images"
  },
  "activeLocationId": "entrance_hall_01",
  "entities": [],
  "locations": [],
  "debug": {
    "showSockets": true,
    "showClickableRects": true,
    "showSafeArea": false
  }
}
```

The preview snapshot may inline resolved entities and locations to avoid making the preview runtime chase many files during every small edit.

---

## 26. Export behavior

Export is destructive.

The project is versioned in git, so the tool writes directly to game data files.

Still, export should:

1. validate
2. show errors/warnings
3. block on errors unless forced
4. write pretty formatted stable JSON
5. preserve deterministic ordering where easy

Stable ordering is low-cost and should be implemented:

- sorted IDs
- stable object member order
- stable include order
- stable generated instance IDs

---

## 27. Legacy compatibility

Version 1 files remain loadable by the game.

The tool may import v1 data and convert to v2.

Legacy behavior:

- old `locations[].items` become placed entities in generated default item sockets or legacy placement area
- old `locations[].characters` become placed entities in generated default character sockets
- old directional exits become clickable exit entities with generated sockets

The conversion does not need to be perfect. It only needs to preserve current sample data enough to bootstrap the new workflow.

---

## 28. Initial v1 implementation scope

### In scope

- Python desktop app.
- Windows only.
- Project root selection.
- Room catalog editor.
- Location instance editor.
- Entity catalog editor.
- Socket authoring.
- Layer authoring.
- Exit authoring.
- Graph view from `locations.json`.
- Generate tab with preview-first/apply-later workflow.
- Validate tab.
- JSON Schema.
- Local TCP preview protocol.
- Game preview mode.
- Same render path preview.
- Runtime debug overlays.
- v2 data model.
- v1 legacy fallback/import.

### Out of scope

- Mansion procedural graph generation.
- Mystery generation.
- Full flag-condition simulation.
- Animated background authoring.
- Polygon/mask clickable areas.
- Multi-user collaboration.
- Cross-platform support.
- Web app.
- Embedded game viewport inside Python window.
- Runtime regeneration on room entry.

---

## 29. Recommended file layout

### Game data

```text
data/behemoth/game/
  entities.json
  entity_modules/
    items.json
    characters.json
    furniture.json
    exits.json
  room_catalog.json
  locations.json
  tags.json
```

### Tool-local data

```text
.behemoth_tool/
  project.json
  editor_settings.json
  preview/
    current_snapshot.json
  schemas/
    entities.schema.json
    room_catalog.schema.json
    locations.schema.json
  cache/
```

### Tool repo

Separate repository, for example:

```text
behemoth-location-tool/
  pyproject.toml
  src/
    behemoth_tool/
      app.py
      model/
      ui/
      validation/
      preview/
      io/
      generation/
      schemas/
  tests/
```

---

## 30. Recommended Python stack

Use **PySide6 / Qt**.

Reasons:

- solid desktop UI
- good tree/table/property editors
- good graphics scene support for room/graph editing
- good Windows support
- can host image previews and custom scene editors
- undo/redo support maps well to `QUndoStack`
- separate game preview window avoids native embedding complexity

Core libraries:

```text
PySide6
pydantic or dataclasses + custom validation
jsonschema
Pillow
watchdog
```

---

## 31. Design principles

1. Python owns authoring data.
2. Game owns preview interpretation.
3. Preview must use the real render path.
4. Generation writes initial state, not runtime behavior.
5. Runtime does not regenerate rooms on entry.
6. Sockets are pivots, not entities.
7. Exits are entities.
8. Directions are deprecated.
9. Tags drive placement categories.
10. Layers drive visual order and hit-test priority.
11. Room catalog defines reusable templates.
12. `locations.json` defines actual mansion state.
13. Validation exists both in Python and C++ runtime.
14. v2 schema is canonical.
15. v1 remains legacy-compatible.
