import pytest

from farmles_harvester.models.record_contracts import (
    CANDIDATE_URL_REQUIRED,
    DISCOVERED_LINK_REQUIRED,
    MARKDOWN_PAGE_REQUIRED,
    NORMALIZED_SOURCE_LEAD_REQUIRED,
    VALIDATED_SOURCE_REQUIRED,
    has_required_fields,
    missing_fields,
    require_fields,
)

_REQUIRED = {"run_id", "source_slug"}
_COMPLETE = {"run_id": "r1", "source_slug": "example-com"}
_INCOMPLETE = {"run_id": "r1"}


class TestMissingFields:
    def test_returns_empty_set_when_all_present(self):
        assert missing_fields(_COMPLETE, _REQUIRED) == set()

    def test_returns_missing_field_names(self):
        assert missing_fields(_INCOMPLETE, _REQUIRED) == {"source_slug"}


class TestHasRequiredFields:
    def test_returns_true_when_complete(self):
        assert has_required_fields(_COMPLETE, _REQUIRED) is True

    def test_returns_false_when_incomplete(self):
        assert has_required_fields(_INCOMPLETE, _REQUIRED) is False


class TestRequireFields:
    def test_does_not_raise_when_complete(self):
        require_fields(_COMPLETE, _REQUIRED)  # must not raise

    def test_raises_value_error_with_missing_field_names(self):
        with pytest.raises(ValueError, match="source_slug"):
            require_fields(_INCOMPLETE, _REQUIRED)

    def test_extra_fields_are_allowed(self):
        record = {**_COMPLETE, "extra_debug_field": "allowed", "another_extra": 42}
        missing_fields(record, _REQUIRED) == set()
        assert has_required_fields(record, _REQUIRED) is True
        require_fields(record, _REQUIRED)  # must not raise


class TestContractConstants:
    def test_all_constants_exist_and_are_sets(self):
        for constant in [
            NORMALIZED_SOURCE_LEAD_REQUIRED,
            VALIDATED_SOURCE_REQUIRED,
            DISCOVERED_LINK_REQUIRED,
            CANDIDATE_URL_REQUIRED,
            MARKDOWN_PAGE_REQUIRED,
        ]:
            assert isinstance(constant, (set, frozenset))
            assert len(constant) > 0
