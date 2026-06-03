NORMALIZED_SOURCE_LEAD_REQUIRED: frozenset[str] = frozenset({
    "run_id",
    "source_slug",
    "input_url",
    "normalized_url",
    "input_line",
    "normalized_at",
})

VALIDATED_SOURCE_REQUIRED: frozenset[str] = frozenset({
    "run_id",
    "source_slug",
    "normalized_url",
    "final_url",
    "validation_status",
    "validated_at",
})

DISCOVERED_LINK_REQUIRED: frozenset[str] = frozenset({
    "run_id",
    "source_slug",
    "source_url",
    "discovered_url",
    "link_text",
    "is_internal",
    "follow_allowed",
})

CANDIDATE_URL_REQUIRED: frozenset[str] = frozenset({
    "run_id",
    "source_slug",
    "source_url",
    "candidate_url",
    "candidate_type",
    "candidate_score",
    "candidate_status",
})

MARKDOWN_PAGE_REQUIRED: frozenset[str] = frozenset({
    "run_id",
    "source_slug",
    "candidate_url",
    "candidate_type",
    "fetch_status",
    "markdown_path",
    "markdown_filename",
    "generated_at",
})


def missing_fields(record: dict, required_fields: set[str]) -> set[str]:
    return required_fields - record.keys()


def has_required_fields(record: dict, required_fields: set[str]) -> bool:
    return not missing_fields(record, required_fields)


def require_fields(record: dict, required_fields: set[str]) -> None:
    missing = missing_fields(record, required_fields)
    if missing:
        raise ValueError(f"Missing required fields: {sorted(missing)}")
