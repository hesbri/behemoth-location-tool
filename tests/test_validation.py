from behemoth_location_tool.validation.validator import validate_unique_ids

def test_duplicate_ids_are_errors() -> None:
    report = validate_unique_ids(["a", "b", "a"], label="entity")
    assert report.has_errors
    assert report.diagnostics[0].code == "duplicate_id"
