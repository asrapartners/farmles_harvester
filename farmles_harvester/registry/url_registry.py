from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

SCHEMA_VERSION = "1"
_SCHEMA_PATH = Path(__file__).parent / "schema.sql"
_SQLITE_MAX_PARAMS = 500

OUTCOME_CLASSES = frozenset({
    "ok",
    "policy_rejected",
    "dns_error",
    "tls_error",
    "connect_error",
    "timeout",
    "http_4xx",
    "http_5xx",
    "rate_limited",
    "redirect_loop",
    "blocked",
    "soft_404",
    "wrong_content_type",
    "empty",
    "parked",
    "boilerplate_only",
    "size_exceeded",
})

RETRY_POSTURES = frozenset({"permanent", "transient", "unknown"})

MARKDOWN_STATUSES = frozenset({"generated", "empty", "boilerplate_only", "not_attempted"})


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _chunked(items: list[Any], size: int) -> Iterator[list[Any]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


class UrlRegistry:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._apply_schema()
        self._in_transaction = False

    def _apply_schema(self) -> None:
        sql = _SCHEMA_PATH.read_text(encoding="utf-8")
        self._conn.executescript(sql)
        for col in ("source_lead_id", "source_url", "source_url_count"):
            try:
                self._conn.execute(f"ALTER TABLE urls DROP COLUMN {col}")
            except Exception:
                pass
        try:
            self._conn.execute("ALTER TABLE urls ADD COLUMN markdown_strength TEXT")
        except Exception:
            pass
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
        if row is None:
            self._conn.execute(
                "INSERT INTO meta(key, value) VALUES ('schema_version', ?)",
                (SCHEMA_VERSION,),
            )

    @property
    def schema_version(self) -> str:
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
        return row["value"]

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "UrlRegistry":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        if self._in_transaction:
            yield
            return
        self._conn.execute("BEGIN")
        self._in_transaction = True
        try:
            yield
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        finally:
            self._in_transaction = False

    # ---- reads (urls) ----

    def get(self, url: str) -> dict | None:
        row = self._conn.execute("SELECT * FROM urls WHERE url = ?", (url,)).fetchone()
        return dict(row) if row else None

    def get_many(self, urls: Iterable[str]) -> dict[str, dict]:
        out: dict[str, dict] = {}
        url_list = list(urls)
        for chunk in _chunked(url_list, _SQLITE_MAX_PARAMS):
            placeholders = ",".join(["?"] * len(chunk))
            rows = self._conn.execute(
                f"SELECT * FROM urls WHERE url IN ({placeholders})", chunk
            ).fetchall()
            for r in rows:
                out[r["url"]] = dict(r)
        return out

    def contains(self, url: str) -> bool:
        row = self._conn.execute("SELECT 1 FROM urls WHERE url = ?", (url,)).fetchone()
        return row is not None

    def contains_many(self, urls: Iterable[str]) -> dict[str, bool]:
        url_list = list(urls)
        found: set[str] = set()
        for chunk in _chunked(url_list, _SQLITE_MAX_PARAMS):
            placeholders = ",".join(["?"] * len(chunk))
            rows = self._conn.execute(
                f"SELECT url FROM urls WHERE url IN ({placeholders})", chunk
            ).fetchall()
            found.update(r["url"] for r in rows)
        return {u: (u in found) for u in url_list}

    def query(
        self,
        *,
        where: str | None = None,
        params: Iterable[Any] = (),
        order_by: str | None = None,
        limit: int | None = None,
    ) -> Iterator[dict]:
        sql = "SELECT * FROM urls"
        if where:
            sql += f" WHERE {where}"
        if order_by:
            sql += f" ORDER BY {order_by}"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        for row in self._conn.execute(sql, tuple(params)):
            yield dict(row)

    def count(self, *, where: str | None = None, params: Iterable[Any] = ()) -> int:
        sql = "SELECT COUNT(*) AS n FROM urls"
        if where:
            sql += f" WHERE {where}"
        row = self._conn.execute(sql, tuple(params)).fetchone()
        return int(row["n"])

    # ---- reads (junction & sources) ----

    def sources_of(self, url: str) -> Iterator[str]:
        for row in self._conn.execute(
            "SELECT source_url FROM url_sources WHERE url = ? ORDER BY source_url",
            (url,),
        ):
            yield row["source_url"]

    def urls_from(self, source_url: str) -> Iterator[str]:
        for row in self._conn.execute(
            "SELECT url FROM url_sources WHERE source_url = ? ORDER BY url",
            (source_url,),
        ):
            yield row["url"]

    def get_source(self, source_url: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM sources WHERE source_url = ?", (source_url,)
        ).fetchone()
        return dict(row) if row else None

    # ---- writes (urls) ----

    def upsert(self, row: dict, *, run_id: str, now: str | None = None) -> None:
        self.upsert_many([row], run_id=run_id, now=now)

    def upsert_many(
        self, rows: Iterable[dict], *, run_id: str, now: str | None = None
    ) -> None:
        rows = list(rows)
        if not rows:
            return
        ts = now or _utcnow_iso()
        with self.transaction():
            for r in rows:
                url = r["url"]
                source_url = r.get("source_url")
                if source_url:
                    self._conn.execute(
                        "INSERT OR IGNORE INTO url_sources(url, source_url) VALUES (?, ?)",
                        (url, source_url),
                    )
                self._conn.execute(
                    """
                    INSERT INTO urls (
                        url,
                        candidate_score, candidate_status, candidate_strength, candidate_type,
                        first_seen_at, last_seen_at, last_run_id, times_seen
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                    ON CONFLICT(url) DO UPDATE SET
                        candidate_score    = excluded.candidate_score,
                        candidate_status   = excluded.candidate_status,
                        candidate_strength = excluded.candidate_strength,
                        candidate_type     = excluded.candidate_type,
                        last_seen_at       = excluded.last_seen_at,
                        last_run_id        = excluded.last_run_id,
                        times_seen         = urls.times_seen + 1
                    """,
                    (
                        url,
                        r.get("candidate_score"),
                        r.get("candidate_status"),
                        r.get("candidate_strength"),
                        r.get("candidate_type"),
                        ts,
                        ts,
                        run_id,
                    ),
                )

    def record_outcome(
        self,
        url: str,
        *,
        outcome_class: str,
        retry_posture: str | None,
        detail: dict | str | None,
        run_id: str,
        now: str | None = None,
    ) -> None:
        self.record_outcome_many(
            [
                {
                    "url": url,
                    "outcome_class": outcome_class,
                    "retry_posture": retry_posture,
                    "detail": detail,
                }
            ],
            run_id=run_id,
            now=now,
        )

    def record_outcome_many(
        self, rows: Iterable[dict], *, run_id: str, now: str | None = None
    ) -> None:
        rows = list(rows)
        if not rows:
            return
        ts = now or _utcnow_iso()
        with self.transaction():
            for r in rows:
                outcome_class = r["outcome_class"]
                posture = r.get("retry_posture")
                self._validate_outcome(outcome_class, posture)
                detail = r.get("detail")
                detail_text = self._encode_detail(detail)
                if outcome_class == "ok":
                    self._conn.execute(
                        """
                        UPDATE urls SET
                            last_outcome_class   = ?,
                            outcome_detail       = ?,
                            retry_posture        = NULL,
                            consecutive_failures = 0,
                            last_seen_at         = ?,
                            last_run_id          = ?
                        WHERE url = ?
                        """,
                        (outcome_class, detail_text, ts, run_id, r["url"]),
                    )
                else:
                    self._conn.execute(
                        """
                        UPDATE urls SET
                            last_outcome_class   = ?,
                            outcome_detail       = ?,
                            retry_posture        = ?,
                            last_error_at        = ?,
                            consecutive_failures = consecutive_failures + 1,
                            last_seen_at         = ?,
                            last_run_id          = ?
                        WHERE url = ?
                        """,
                        (outcome_class, detail_text, posture, ts, ts, run_id, r["url"]),
                    )

    def record_markdown_outcome(
        self,
        url: str,
        *,
        status: str,
        strength: str | None = None,
        word_count: int | None = None,
        path: str | None = None,
        run_id: str,
        now: str | None = None,
    ) -> None:
        if status not in MARKDOWN_STATUSES:
            raise ValueError(f"invalid markdown status: {status!r}")
        ts = now or _utcnow_iso()
        self._conn.execute(
            """
            UPDATE urls SET
                markdown_status     = ?,
                markdown_strength   = ?,
                markdown_word_count = ?,
                markdown_path       = ?,
                last_seen_at        = ?,
                last_run_id         = ?
            WHERE url = ?
            """,
            (status, strength, word_count, path, ts, run_id, url),
        )

    def record_source(self, url: str, source_url: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO url_sources(url, source_url) VALUES (?, ?)",
            (url, source_url),
        )

    # ---- writes (sources) ----

    def upsert_source(
        self,
        source_url: str,
        *,
        relevance_label: str | None = None,
        relevance_score: int | None = None,
        keyword_hits: int | None = None,
        negative_hits: int | None = None,
        total_word_count: int | None = None,
        page_count: int | None = None,
        run_id: str,
        now: str | None = None,
    ) -> None:
        self.upsert_source_many(
            [
                {
                    "source_url": source_url,
                    "relevance_label": relevance_label,
                    "relevance_score": relevance_score,
                    "keyword_hits": keyword_hits,
                    "negative_hits": negative_hits,
                    "total_word_count": total_word_count,
                    "page_count": page_count,
                }
            ],
            run_id=run_id,
            now=now,
        )

    def upsert_source_many(
        self, rows: Iterable[dict], *, run_id: str, now: str | None = None
    ) -> None:
        rows = list(rows)
        if not rows:
            return
        ts = now or _utcnow_iso()
        with self.transaction():
            for r in rows:
                self._conn.execute(
                    """
                    INSERT INTO sources (
                        source_url, relevance_label, relevance_score,
                        keyword_hits, negative_hits, total_word_count, page_count,
                        first_seen_at, last_seen_at, last_run_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_url) DO UPDATE SET
                        relevance_label  = excluded.relevance_label,
                        relevance_score  = excluded.relevance_score,
                        keyword_hits     = excluded.keyword_hits,
                        negative_hits    = excluded.negative_hits,
                        total_word_count = excluded.total_word_count,
                        page_count       = excluded.page_count,
                        last_seen_at     = excluded.last_seen_at,
                        last_run_id      = excluded.last_run_id
                    """,
                    (
                        r["source_url"],
                        r.get("relevance_label"),
                        r.get("relevance_score"),
                        r.get("keyword_hits"),
                        r.get("negative_hits"),
                        r.get("total_word_count"),
                        r.get("page_count"),
                        ts,
                        ts,
                        run_id,
                    ),
                )

    # ---- delete & maintenance ----

    def delete(self, url: str) -> None:
        with self.transaction():
            self._conn.execute("DELETE FROM url_sources WHERE url = ?", (url,))
            self._conn.execute("DELETE FROM urls WHERE url = ?", (url,))

    def delete_where(self, where: str, params: Iterable[Any] = ()) -> int:
        cur = self._conn.execute(f"DELETE FROM urls WHERE {where}", tuple(params))
        return cur.rowcount

    def vacuum(self) -> None:
        self._conn.execute("VACUUM")

    # ---- internals ----

    @staticmethod
    def _validate_outcome(outcome_class: str, posture: str | None) -> None:
        if outcome_class not in OUTCOME_CLASSES:
            raise ValueError(f"invalid outcome_class: {outcome_class!r}")
        if outcome_class == "ok":
            if posture is not None:
                raise ValueError("retry_posture must be None when outcome_class is 'ok'")
        else:
            if posture not in RETRY_POSTURES:
                raise ValueError(
                    f"retry_posture must be one of {sorted(RETRY_POSTURES)} for failure outcomes"
                )

    @staticmethod
    def _encode_detail(detail: dict | str | None) -> str | None:
        if detail is None:
            return None
        if isinstance(detail, str):
            return detail
        import json
        return json.dumps(detail, separators=(",", ":"), sort_keys=True)
