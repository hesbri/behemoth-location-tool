# Behemoth Location Tool

Python desktop authoring tool for Behemoth mansion rooms, sockets, exits, render layers, entity catalogs, deterministic ambient generation, validation, and game-runtime preview.

This repository is intentionally separate from the Behemoth game repository. It edits canonical game data inside a selected Behemoth game project and stores editor-local state under:

```text
<game-root>/.behemoth_tool/
```

That folder should be ignored by the game repository.

## Requirements

- Windows
- Python 3.11
- A local Behemoth game repository/build
- The Behemoth game executable built for editor preview

## Quick start

From the location-tool repository root:

```bat
py -3.11 -m venv .venv
.venv\Scripts\activate.bat
pip install -e .[dev]
run_tool.bat projects\behemoth.json
```

Convenience scripts:

```bat
scripts\bootstrap.ps1   # create venv + install dependencies
run_tool.bat            # open the tool
scripts\test_tool.bat   # compile + run all tests
smoke_preview.bat       # preview protocol smoke test
```

## Running the tool

```bat
run_tool.bat projects\behemoth.json
```

The project JSON file contains path configuration for the game root, executable, content root, image root, game data root, and preview port.

Relative paths in the project JSON are resolved relative to the project JSON file itself, except paths that are explicitly defined relative to the game root.

## Running tests

Use the test script from the tool repository root:

```bat
scripts\test_tool.bat
```

This activates `.venv`, runs:

```bat
python -m compileall src
python -m pytest -q
```

and returns nonzero on any failure.

You can also run pytest directly:

```bat
.venv\Scripts\python.exe -m pytest tests\ -q
```

## Project configuration

Open the **Project** tab to view and edit project paths.

| Field | Meaning |
|---|---|
| Project Name | Display name for the configured project |
| Game Root | Root directory of the Behemoth game project |
| Game Executable | Path to the launcher/executable, usually relative to Game Root |
| Content Root | Runtime content mount root, usually `data/behemoth` |
| Image Root | Root of image assets, usually `data/behemoth/assets/images` |
| Game Data Root | Canonical game data folder, usually `data/behemoth/game` |
| Tool Data Root | Editor-local scratch folder, usually `.behemoth_tool` |
| Design Width / Height | Reference design resolution |
| Preview Port | TCP port used by editor preview |

The Project tab also shows resolved absolute paths. Use this to verify that the tool is writing to the intended game repository.

Use **Save Project Config** to save project path changes.

Use **Save Game Data** or `Ctrl+S` to save authored game data.

## Canonical game data

The tool writes canonical Behemoth game data under:

```text
<game-root>/<gameDataRoot>/
```

Primary files:

```text
entities.json
entity_modules/*.json
room_catalog.json
locations.json
tags.json
```

The normal workflow uses the canonical schema only. Existing import tools, if present, are conversion helpers that write canonical output.

## Authoring room catalog entries

Room catalog entries define reusable room templates.

1. Open **Room Catalog**.
2. Click **Add Room**.
3. Set ID, name, description, tags, background image, design size, and layers.
4. Add sockets for exits, furniture, NPCs, or props.
5. Configure each socket’s transform, pivot mode, layer, tags, and ambient fill rules.
6. Save with `Ctrl+S`.

Room catalog sockets are templates. Actual locations inherit them unless the location explicitly overrides sockets.

## Creating locations

Locations are actual mansion room instances used by the game.

1. Open **Locations**.
2. Click **Add Location**.
3. Select a catalog room.
4. Configure the location name, description, tags, exits, and placed entities.
5. Add reciprocal exits between connected locations.
6. Save with `Ctrl+S`.

Locations inherit background and sockets from their catalog room unless explicitly overridden.

Non-start locations must have at least one default/back exit tagged:

```text
exit.default_back
```

## Exits

Exits are clickable entities that move the player to another location.

An exit should define:

```text
id
entityId
targetLocationId
socketId
layer
tags
locked
clickableRect
conditions
```

`socketId` references a socket in the same location’s effective socket list.

## Placed entities

Placed entities are actual entity instances placed in a location.

A placed entity should define:

```text
instanceId
entityId
socketId
layer
sortOrder
savePolicy
placementSource
```

`entityId` references the entity catalog.

`socketId` references the owning location’s effective sockets.

## Ambient generation

The **Generate** tab previews deterministic ambient placement before applying changes.

Workflow:

1. Open **Generate**.
2. Select a location.
3. Review generated placements.
4. Click **Apply** to write generated entities into `placedEntities`.
5. Save with `Ctrl+S`.

Applied generated entities use:

```text
placementSource: "ambient_fill"
```

so they can be distinguished from manually placed entities.

Ambient generation is deterministic for the same seed and input data.

## Validation

Open **Validate** and click **Validate All**.

Validation checks include:

- duplicate IDs in the correct scope
- invalid tags
- missing assets
- missing entity references
- missing socket references
- missing layers
- invalid weighted ambient rules
- missing default back exits
- missing reciprocal exits
- unreachable locations
- runtime diagnostics, when preview runtime validation is available

Use the severity dropdown and search box to filter diagnostics.

## Preview

The Preview tab starts a local TCP server and can launch the Behemoth game in editor-preview mode.

Typical workflow:

1. Open **Preview**.
2. Click **Start Preview**.
3. Click **Launch Game**.
4. Wait for the connection indicator to turn green.
5. Select a location in the Locations tab.
6. Click **Refresh Snapshot** if needed.

The tool writes preview snapshots to:

```text
<game-root>/.behemoth_tool/preview/current_snapshot.json
```

The Preview tab shows the exact command used to launch the game.

## Path rules

Authoring data should store asset paths relative to the configured image root.

Good:

```text
world/backgrounds/entrance.png
props/lantern.png
characters/gerald/body.png
```

Avoid machine-absolute paths in game data:

```text
E:\Projects\Brutalist\data\behemoth\assets\images\...
```

The tool validates missing assets and warns when paths are not portable.

## Repository layout

```text
src/behemoth_location_tool/
  app.py
  io/
  model/
  preview/
  ui/
  validation/

tests/
scripts/
projects/
docs/
```

## Design reference

The main design document is:

```text
docs/LocationToolDesignSpec.md
```

Use it as the reference for concepts, schema intent, and authoring workflow.

## Development workflow

Run before committing:

```bat
scripts\test_tool.bat
smoke_preview.bat
```

Recommended commit checks:

```bat
git status
git diff
git diff --cached
```

The tool repository and game repository are separate. Commit tool changes here and game/runtime/data changes in the Behemoth game repository.

## Troubleshooting

### Validation reports `Unexpected UTF-8 BOM`

The tool reads JSON with BOM tolerance, but committed JSON should be UTF-8 without BOM. Re-save affected files as UTF-8 without BOM.

### Preview does not connect

Check:

- Preview server is started.
- Preview port matches the project config.
- Game executable path is valid.
- The game was launched with editor-preview arguments.
- Firewall is not blocking localhost TCP.

### Preview loads but reports missing assets

Check that asset paths are relative to Image Root and that the files exist under:

```text
<game-root>/<imageRoot>/
```

### Tool writes to the wrong folder

Open the Project tab and inspect resolved paths. Relative paths should resolve from the project config and game root as shown there.
