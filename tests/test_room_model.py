import pytest
from pydantic import ValidationError
from behemoth_location_tool.model.room import AmbientRule, WeightedFillEntry


def test_weighted_entity_list_must_sum_to_100() -> None:
    with pytest.raises(ValidationError):
        AmbientRule.model_validate({
            "mode": "weighted_entity_list",
            "entries": [{"entityId": "a", "weight": 60}, {"entityId": "b", "weight": 30}],
        })


def test_weighted_entity_list_valid_when_sums_to_100() -> None:
    rule = AmbientRule.model_validate({
        "mode": "weighted_entity_list",
        "entries": [{"entityId": "a", "weight": 60}, {"entityId": "b", "weight": 40}],
    })
    assert rule.mode == "weighted_entity_list"
    assert len(rule.entries) == 2


def test_tag_query_mode_valid_by_default() -> None:
    rule = AmbientRule.model_validate({"mode": "tag_query"})
    assert rule.mode == "tag_query"


def test_none_mode_valid() -> None:
    rule = AmbientRule.model_validate({"mode": "none"})
    assert rule.mode == "none"
    assert rule.entries == []
    assert rule.fill_entries == []


def test_weighted_entries_must_sum_to_100() -> None:
    with pytest.raises(ValidationError):
        AmbientRule.model_validate({
            "mode": "weighted_entries",
            "fillEntries": [
                {"type": "entity", "entityId": "a", "weight": 30},
                {"type": "entity", "entityId": "b", "weight": 30},
            ],
        })


def test_weighted_entries_valid_when_sums_to_100() -> None:
    rule = AmbientRule.model_validate({
        "mode": "weighted_entries",
        "fillEntries": [
            {"type": "entity", "entityId": "a", "weight": 50},
            {"type": "tag_query", "requiredTags": ["npc"], "weight": 50},
        ],
    })
    assert rule.mode == "weighted_entries"
    assert len(rule.fill_entries) == 2
    assert rule.fill_entries[0].type == "entity"
    assert rule.fill_entries[1].type == "tag_query"


def test_weighted_fill_entry_defaults() -> None:
    entry = WeightedFillEntry.model_validate({"type": "entity", "weight": 10})
    assert entry.entity_id == ""
    assert entry.required_tags == []
    assert entry.forbidden_tags == []
