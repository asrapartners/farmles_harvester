from dataclasses import dataclass


@dataclass
class FakeResponse:
    url: str
    status_code: int
    content_type: str
    text: str


class FakeFetcher:
    def __init__(self, pages: dict[str, FakeResponse]):
        self._pages = pages
        self.requested_urls: list[str] = []

    def fetch(self, url: str) -> FakeResponse:
        self.requested_urls.append(url)
        if url not in self._pages:
            raise KeyError(f"URL not registered in FakeFetcher: {url!r}")
        return self._pages[url]
