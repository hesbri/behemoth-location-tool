"""Generate tab — preview-first deterministic ambient fill, then Apply."""
from __future__ import annotations

import random
from dataclasses import dataclass

from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from behemoth_location_tool.generation.ambient_fill import GenerationSeed, should_spawn
from behemoth_location_tool.model.entity import EntityDefinition
from behemoth_location_tool.model.location import (
    LocationInstance,
    LocationsFile,
    PlacedEntity,
    get_effective_sockets,
)
from behemoth_location_tool.model.room import RoomCatalog, SocketDefinition
from behemoth_location_tool.model.tags import matches_all, matches_none


@dataclass
class _GenRow:
    socket_id: str
    entity_id: str = ""
    placement_source: str = ""
    reject_reason: str = ""

    @property
    def placed(self) -> bool:
        return bool(self.entity_id)


def _candidate_ok(
    entity: EntityDefinition,
    location_tags: list[str],
    socket: SocketDefinition,
    used_groups: set[str],
) -> bool:
    tags = set(entity.tags)
    sr = entity.spawn_rules

    if socket.required_tags and not matches_all(tags, socket.required_tags):
        return False
    if socket.forbidden_tags and not matches_none(tags, socket.forbidden_tags):
        return False

    context_tags = set(location_tags) | set(socket.required_tags)
    if sr.required_context_tags and not matches_all(context_tags, sr.required_context_tags):
        return False
    if sr.forbidden_context_tags and not matches_none(context_tags, sr.forbidden_context_tags):
        return False

    if any(g in used_groups for g in sr.exclusive_groups):
        return False

    if socket.allowed_entity_ids and entity.id not in socket.allowed_entity_ids:
        return False

    return True


# ---- generation logic --------------------------------------------------

def _run_ambient_fill(
    location: LocationInstance,
    sockets: list[SocketDefinition],
    entities: list[EntityDefinition],
    mansion_seed: int,
) -> list[_GenRow]:
    used_groups: set[str] = set()
    filled = {pe.socket_id for pe in location.placed_entities}
    entity_map = {e.id: e for e in entities}
    rows: list[_GenRow] = []

    for socket in sockets:
        if socket.id in filled:
            continue

        row = _GenRow(socket_id=socket.id)
        seed = GenerationSeed(
            mansion_seed=mansion_seed,
            location_id=location.id,
            socket_id=socket.id,
            pass_name="ambient_fill",
        )

        if not should_spawn(seed, socket.ambient_spawn_chance):
            row.reject_reason = f"spawn roll failed (chance={socket.ambient_spawn_chance}%)"
            rows.append(row)
            continue

        rule = socket.ambient_rule
        if rule.mode == "none":
            row.reject_reason = "ambient rule mode=none"
            rows.append(row)
            continue

        chosen: EntityDefinition | None = None

        if rule.mode == "tag_query":
            candidates = [
                e for e in entities
                if _candidate_ok(e, location.tags, socket, used_groups)
                and (not rule.required_tags or matches_all(set(e.tags), rule.required_tags))
                and (not rule.forbidden_tags or matches_none(set(e.tags), rule.forbidden_tags))
            ]
            if candidates:
                rng = random.Random(seed.to_int())
                chosen = rng.choice(candidates)

        elif rule.mode in ("weighted_entity_list", "weighted_entries"):
            entries = rule.entries if rule.mode == "weighted_entity_list" else rule.fill_entries
            pool: list[tuple[EntityDefinition, int]] = []
            for entry in entries:
                eid = getattr(entry, "entity_id", "")
                if eid:
                    ent = entity_map.get(eid)
                    if ent is not None and _candidate_ok(ent, location.tags, socket, used_groups):
                        pool.append((ent, entry.weight))
            if pool:
                rng = random.Random(seed.to_int())
                total = sum(w for _, w in pool)
                roll = rng.randint(1, total)
                cumulative = 0
                for ent, w in pool:
                    cumulative += w
                    if roll <= cumulative:
                        chosen = ent
                        break

        if chosen is None:
            row.reject_reason = "no matching candidates"
        else:
            row.entity_id = chosen.id
            row.placement_source = "ambient_fill"
            used_groups.update(chosen.spawn_rules.exclusive_groups)

        rows.append(row)

    return rows


# ---- widget ------------------------------------------------------------

class GenerateTab(QWidget):
    """Preview-first deterministic ambient fill, then Apply."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._locations_file: LocationsFile | None = None
        self._catalog: RoomCatalog | None = None
        self._entities: list[EntityDefinition] = []
        self._preview_rows: list[_GenRow] = []
        self._build_ui()

    # ---- public API ----

    def set_locations_file(self, lf: LocationsFile) -> None:
        self._locations_file = lf
        self._refresh_combo()
        self._seed_spin.setValue(lf.mansion_seed)

    def set_catalog(self, catalog: RoomCatalog | None) -> None:
        self._catalog = catalog

    def set_entities(self, entities: list[EntityDefinition]) -> None:
        self._entities = list(entities)

    # ---- UI ----

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        settings = QGroupBox("Generation Settings")
        slay = QVBoxLayout(settings)

        row = QHBoxLayout()
        row.addWidget(QLabel("Location:"))
        self._combo = QComboBox()
        row.addWidget(self._combo, 1)
        slay.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Mansion Seed:"))
        self._seed_spin = QSpinBox()
        self._seed_spin.setRange(0, 2_147_483_647)
        row2.addWidget(self._seed_spin, 1)
        slay.addLayout(row2)

        root.addWidget(settings)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Socket", "Entity", "Source", "Status"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        root.addWidget(self._table, 1)

        btn_row = QHBoxLayout()
        self._gen_btn = QPushButton("Generate Preview")
        self._gen_btn.clicked.connect(self._on_generate)
        self._apply_btn = QPushButton("Apply to Location")
        self._apply_btn.setEnabled(False)
        self._apply_btn.clicked.connect(self._on_apply)
        self._discard_btn = QPushButton("Discard Preview")
        self._discard_btn.setEnabled(False)
        self._discard_btn.clicked.connect(self._on_discard)
        btn_row.addWidget(self._gen_btn)
        btn_row.addWidget(self._apply_btn)
        btn_row.addWidget(self._discard_btn)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

    def _refresh_combo(self) -> None:
        self._combo.clear()
        if self._locations_file is None:
            return
        for loc in self._locations_file.locations:
            self._combo.addItem(f"{loc.name} ({loc.id})", loc.id)

    def _current_location(self) -> LocationInstance | None:
        if self._locations_file is None:
            return None
        loc_id = self._combo.currentData()
        for loc in self._locations_file.locations:
            if loc.id == loc_id:
                return loc
        return None

    def _on_generate(self) -> None:
        location = self._current_location()
        if location is None:
            QMessageBox.warning(self, "No Location", "Select a location first.")
            return
        seed = self._seed_spin.value()
        effective_sockets = get_effective_sockets(location, self._catalog)
        self._preview_rows = _run_ambient_fill(location, effective_sockets, self._entities, seed)
        self._table.setRowCount(0)
        for row in self._preview_rows:
            r = self._table.rowCount()
            self._table.insertRow(r)
            self._table.setItem(r, 0, QTableWidgetItem(row.socket_id))
            self._table.setItem(r, 1, QTableWidgetItem(row.entity_id or "—"))
            self._table.setItem(r, 2, QTableWidgetItem(row.placement_source or "—"))
            status = "placed" if row.placed else f"skipped: {row.reject_reason}"
            self._table.setItem(r, 3, QTableWidgetItem(status))
        has_placed = any(r.placed for r in self._preview_rows)
        self._apply_btn.setEnabled(has_placed)
        self._discard_btn.setEnabled(True)

    def _on_apply(self) -> None:
        location = self._current_location()
        if location is None or not self._preview_rows:
            return
        for row in self._preview_rows:
            if not row.placed:
                continue
            instance_id = f"{location.id}__{row.socket_id}__{row.entity_id}"
            pe = PlacedEntity(
                instance_id=instance_id,
                entity_id=row.entity_id,
                socket_id=row.socket_id,
                placement_source=row.placement_source,
            )
            location.placed_entities.append(pe)
        self._preview_rows = []
        self._table.setRowCount(0)
        self._apply_btn.setEnabled(False)
        self._discard_btn.setEnabled(False)

    def _on_discard(self) -> None:
        self._preview_rows = []
        self._table.setRowCount(0)
        self._apply_btn.setEnabled(False)
        self._discard_btn.setEnabled(False)
