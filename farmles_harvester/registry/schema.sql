-- URL Registry schema. See plan: glimmering-launching-mitten.md.
-- Applied idempotently on every UrlRegistry open.

CREATE TABLE IF NOT EXISTS urls (
    url                     TEXT PRIMARY KEY,
    source_url              TEXT NOT NULL,
    source_lead_id          TEXT,
    source_url_count        INTEGER NOT NULL DEFAULT 1,
    candidate_score         INTEGER,
    candidate_status        TEXT,
    candidate_strength      TEXT,
    candidate_type          TEXT,
    last_outcome_class      TEXT,
    outcome_detail          TEXT,
    retry_posture           TEXT,
    last_error_at           TEXT,
    consecutive_failures    INTEGER NOT NULL DEFAULT 0,
    render_type             TEXT NOT NULL DEFAULT 'unknown',
    render_type_checked_at  TEXT,
    render_type_evidence    TEXT,
    markdown_status         TEXT NOT NULL DEFAULT 'not_attempted',
    markdown_word_count     INTEGER,
    markdown_path           TEXT,
    first_seen_at           TEXT NOT NULL,
    last_seen_at            TEXT NOT NULL,
    last_run_id             TEXT NOT NULL,
    times_seen              INTEGER NOT NULL DEFAULT 1,
    CHECK (
        (last_outcome_class IS NULL  AND retry_posture IS NULL) OR
        (last_outcome_class = 'ok'   AND retry_posture IS NULL) OR
        (last_outcome_class != 'ok'  AND retry_posture IN ('permanent','transient','unknown'))
    )
);

CREATE INDEX IF NOT EXISTS idx_urls_score      ON urls(candidate_score);
CREATE INDEX IF NOT EXISTS idx_urls_status     ON urls(candidate_status);
CREATE INDEX IF NOT EXISTS idx_urls_outcome    ON urls(last_outcome_class);
CREATE INDEX IF NOT EXISTS idx_urls_posture    ON urls(retry_posture);
CREATE INDEX IF NOT EXISTS idx_urls_source_url ON urls(source_url);

CREATE TABLE IF NOT EXISTS url_sources (
    url        TEXT NOT NULL,
    source_url TEXT NOT NULL,
    PRIMARY KEY (url, source_url)
);

CREATE INDEX IF NOT EXISTS idx_url_sources_source_url ON url_sources(source_url);

CREATE TABLE IF NOT EXISTS sources (
    source_url        TEXT PRIMARY KEY,
    relevance_label   TEXT,
    relevance_score   INTEGER,
    keyword_hits      INTEGER,
    negative_hits     INTEGER,
    total_word_count  INTEGER,
    page_count        INTEGER,
    first_seen_at     TEXT NOT NULL,
    last_seen_at      TEXT NOT NULL,
    last_run_id       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sources_label ON sources(relevance_label);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
