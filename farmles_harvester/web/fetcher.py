import requests as _requests
from dataclasses import dataclass, field


class FetchTimeoutError(Exception):
    pass


@dataclass
class FetchResponse:
    url: str
    status_code: int
    content_type: str
    text: str
    final_url: str | None = None
    redirect_chain: list[str] = field(default_factory=list)


class HttpFetcher:
    def __init__(self, timeout: int = 15, user_agent: str = "farmles-harvester/0.1"):
        self._timeout = timeout
        self._headers = {"User-Agent": user_agent}

    def fetch(self, url: str) -> FetchResponse:
        try:
            resp = _requests.get(
                url, timeout=self._timeout, headers=self._headers, allow_redirects=True
            )
        except _requests.Timeout:
            raise FetchTimeoutError(f"Request timed out: {url}")

        redirect_chain = [r.url for r in resp.history]
        final_url = resp.url if resp.history else None
        content_type = resp.headers.get("content-type", "")

        return FetchResponse(
            url=url,
            status_code=resp.status_code,
            content_type=content_type,
            text=resp.text,
            final_url=final_url,
            redirect_chain=redirect_chain,
        )
