from farmles_harvester.registry.evaluation import (
    evaluate_markdown_strength,
    evaluate_url_strength,
    should_process_url,
)


def _url_row(**overrides) -> dict:
    base = {
        "candidate_strength": "medium",
        "last_outcome_class": "ok",
        "retry_posture": None,
        "markdown_word_count": None,
    }
    base.update(overrides)
    return base


class TestEvaluateUrlStrength:
    def test_new_url_processes(self):
        assert evaluate_url_strength(None).should_process is True

    def test_strong_meets_default_threshold(self):
        assert evaluate_url_strength(_url_row(candidate_strength="strong")).should_process is True

    def test_medium_below_strong_threshold(self):
        v = evaluate_url_strength(_url_row(candidate_strength="medium"))
        assert v.should_process is False

    def test_weak_skipped(self):
        assert evaluate_url_strength(_url_row(candidate_strength="weak")).should_process is False

    def test_medium_threshold_allows_medium(self):
        v = evaluate_url_strength(_url_row(candidate_strength="medium"), min_strength="medium")
        assert v.should_process is True

    def test_permanent_failure_skipped_even_if_strong(self):
        row = _url_row(candidate_strength="strong", last_outcome_class="http_4xx", retry_posture="permanent")
        assert evaluate_url_strength(row).should_process is False

    def test_permanent_failure_ignored_when_disabled(self):
        row = _url_row(candidate_strength="strong", last_outcome_class="http_4xx", retry_posture="permanent")
        assert evaluate_url_strength(row, skip_permanent_failures=False).should_process is True

    def test_transient_failure_not_skipped(self):
        row = _url_row(candidate_strength="strong", last_outcome_class="timeout", retry_posture="transient")
        assert evaluate_url_strength(row).should_process is True


class TestEvaluateMarkdownStrength:
    def test_new_url_processes(self):
        assert evaluate_markdown_strength(None).should_process is True

    def test_word_count_at_threshold_processes(self):
        assert evaluate_markdown_strength(_url_row(markdown_word_count=150)).should_process is True

    def test_word_count_below_threshold_skipped(self):
        assert evaluate_markdown_strength(_url_row(markdown_word_count=149)).should_process is False

    def test_missing_word_count_skipped(self):
        assert evaluate_markdown_strength(_url_row(markdown_word_count=None)).should_process is False

    def test_custom_threshold(self):
        assert evaluate_markdown_strength(_url_row(markdown_word_count=50), min_word_count=40).should_process is True

    def test_permanent_failure_skipped(self):
        row = _url_row(markdown_word_count=500, last_outcome_class="http_4xx", retry_posture="permanent")
        assert evaluate_markdown_strength(row).should_process is False


def _source_row(**overrides) -> dict:
    base = {"relevance_label": "confirmed"}
    base.update(overrides)
    return base


class TestShouldProcessUrl:
    def test_both_new_processes(self):
        assert should_process_url(None, None).should_process is True

    def test_url_permanent_failure_blocks_regardless_of_source(self):
        url = _url_row(candidate_strength="strong", last_outcome_class="http_4xx", retry_posture="permanent")
        assert should_process_url(url, _source_row(relevance_label="confirmed")).should_process is False

    def test_url_weak_blocks_regardless_of_source(self):
        assert should_process_url(_url_row(candidate_strength="weak"), _source_row()).should_process is False

    def test_low_confidence_source_blocks(self):
        url = _url_row(candidate_strength="strong")
        assert should_process_url(url, _source_row(relevance_label="low_confidence")).should_process is False

    def test_confirmed_source_passes(self):
        assert should_process_url(_url_row(candidate_strength="strong"), _source_row(relevance_label="confirmed")).should_process is True

    def test_likely_source_passes(self):
        assert should_process_url(_url_row(candidate_strength="strong"), _source_row(relevance_label="likely")).should_process is True

    def test_uncertain_source_passes(self):
        assert should_process_url(_url_row(candidate_strength="strong"), _source_row(relevance_label="uncertain")).should_process is True

    def test_unscored_source_none_passes(self):
        assert should_process_url(_url_row(candidate_strength="strong"), None).should_process is True
