import pytest
from pydantic import ValidationError
from behemoth_location_tool.model.room import AmbientRule

def test_weighted_entity_list_must_sum_to_100() -> None:
    with pytest.raises(ValidationError):
        AmbientRule.model_validate({"mode": "weighted_entity_list", "entries": [{"entityId": "a", "weight": 60}, {"entityId": "b", "weight": 30}]})
