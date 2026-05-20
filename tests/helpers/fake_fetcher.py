from dataclasses import dataclass, field


@dataclass
class FakeResponse:
    url: str
    status_code: int
    content_type: str
    text: str
    final_url: str | None = None
    redirect_chain: list[str] = field(default_factory=list)


class FakeFetcher:
    def __init__(self, pages: dict[str, FakeResponse], exceptions: dict[str, Exception] | None = None):
        self._pages = pages
        self._exceptions = exceptions or {}
        self.requested_urls: list[str] = []

    def fetch(self, url: str) -> FakeResponse:
        self.requested_urls.append(url)
        if url in self._exceptions:
            raise self._exceptions[url]
        if url not in self._pages:
            raise KeyError(f"URL not registered in FakeFetcher: {url!r}")
        return self._pages[url]
