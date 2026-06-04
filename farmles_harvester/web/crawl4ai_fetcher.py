import asyncio
from pathlib import Path


class Crawl4AIFetcher:
    """Batch browser-fetcher for JS-rendered pages using crawl4ai."""

    def __init__(self, max_concurrent: int = 5, use_cache: bool = False):
        self._max_concurrent = max_concurrent
        self._use_cache = use_cache

    def fetch_batch(
        self, records: list[dict]
    ) -> tuple[list[dict], list[dict]]:
        """Browser-fetch all URLs in records. Returns (ok_results, error_records).

        Each record must have: candidate_url, source_slug, markdown_path.
        ok_results follow the d01_browser_fetched_pages schema.
        error_records have: candidate_url, error.
        """
        return asyncio.run(self._fetch_all(records))

    async def _fetch_all(
        self, records: list[dict]
    ) -> tuple[list[dict], list[dict]]:
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
        from crawl4ai.content_filter_strategy import PruningContentFilter
        from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

        browser_config = BrowserConfig(headless=True)
        crawler_config = CrawlerRunConfig(
            page_timeout=60000,
            wait_for="js:document.body.innerText.length > 500",
            remove_overlay_elements=True,
            cache_mode=CacheMode.ENABLED if self._use_cache else CacheMode.BYPASS,
            markdown_generator=DefaultMarkdownGenerator(
                content_filter=PruningContentFilter(threshold=0.4, threshold_type="fixed")
            ),
        )

        url_to_record = {r["candidate_url"]: r for r in records}
        urls = list(url_to_record)

        ok_results: list[dict] = []
        error_records: list[dict] = []

        async with AsyncWebCrawler(config=browser_config) as crawler:
            crawl_results = await crawler.arun_many(
                urls=urls,
                config=crawler_config,
                max_concurrent=self._max_concurrent,
            )

        for cr in crawl_results:
            record = url_to_record[cr.url]

            if not cr.success:
                error_records.append({
                    "candidate_url": cr.url,
                    "error": cr.error_message or "unknown error",
                })
                continue

            md_obj = cr.markdown
            if hasattr(md_obj, "fit_markdown"):
                markdown = md_obj.fit_markdown or md_obj.raw_markdown or ""
            else:
                markdown = str(md_obj) if md_obj else ""

            md_path = Path(record["markdown_path"])
            bytes_before = md_path.stat().st_size if md_path.exists() else 0
            overwritten = bytes_before > 0

            md_path.parent.mkdir(parents=True, exist_ok=True)
            md_path.write_text(markdown, encoding="utf-8")

            bytes_after = md_path.stat().st_size
            bytes_incr_pcnt = round(
                min((bytes_after - bytes_before) / max(bytes_before, 1) * 100, 100.0), 1
            )

            ok_results.append({
                "candidate_url": cr.url,
                "source_slug": record["source_slug"],
                "markdown_path": record["markdown_path"],
                "word_count": len(markdown.split()),
                "overwritten": overwritten,
                "bytes_before": bytes_before,
                "bytes_after": bytes_after,
                "bytes_incr_pcnt": bytes_incr_pcnt,
                "fetch_status": "ok",
            })

        return ok_results, error_records
