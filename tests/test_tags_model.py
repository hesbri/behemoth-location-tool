from __future__ import annotations

from behemoth_location_tool.model.tags import TagIndex, extract_known_tags, matches, matches_all, matches_none


def test_matches_hierarchical() -> None:
    assert matches("furniture.chair.armchair", "furniture.chair")
    assert matches("furniture.chair", "furniture.chair")
    assert not matches("furniture.table", "furniture.chair")


def test_matches_all_and_none() -> None:
    tags = {"entity.spawnable", "furniture.chair.armchair", "style.victorian"}
    assert matches_all(tags, ["entity.spawnable", "furniture.chair"])
    assert matches_none(tags, ["furniture.table", "style.modern"])
    assert not matches_none(tags, ["style"])


def test_extract_known_tags_from_nested_tree() -> None:
    data = {
        "version": 2,
        "tags": {
            "furniture": {"chair": {"armchair": {}}},
            "style": {"victorian": {}},
        },
    }
    known = extract_known_tags(data)
    assert "furniture" in known
    assert "furniture.chair" in known
    assert "furniture.chair.armchair" in known
    assert "style.victorian" in known


def test_tag_index_knows_hierarchical_references() -> None:
    index = TagIndex(known_tags={"furniture.chair.armchair", "style.victorian"})
    assert index.is_known("furniture.chair")
    assert index.is_known("furniture.chair.armchair")
    assert not index.is_known("space.scifi")
