"""HTTP helpers: retries with backoff for transient errors, and SSRF-safe page fetching.

Agents cannot browse freely. They can only (a) call the configured search APIs and (b) fetch pages
whose URLs came from those search results, through `safe_fetch`, which allows only public http(s)
hosts, caps size and time, and accepts only HTML/text responses.
"""
from __future__ import annotations

import ipaddress
import logging
import socket
import time
from collections.abc import Callable
from typing import TypeVar
from urllib.parse import urlparse

import httpx

from src.search.base import ProviderError

logger = logging.getLogger(__name__)
T = TypeVar("T")

TRANSIENT_STATUS = {408, 425, 429, 500, 502, 503, 504}
MAX_FETCH_BYTES = 3 * 1024 * 1024


def with_retries(fn: Callable[[], T], attempts: int = 3, base_delay: float = 1.0,
                 sleep: Callable[[float], None] | None = None) -> T:
    """Call `fn`, retrying transient failures (timeouts, connection errors, 429/5xx) with exponential backoff."""
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status not in TRANSIENT_STATUS:
                raise ProviderError(f"HTTP {status} from {exc.request.url.host}") from exc
            last = exc
            retry_after = exc.response.headers.get("retry-after")
            delay = float(retry_after) if retry_after and retry_after.isdigit() else base_delay * 2 ** (attempt - 1)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last = exc
            delay = base_delay * 2 ** (attempt - 1)
        if attempt < attempts:
            logger.info("Transient error (%s); retrying in %.1fs", type(last).__name__, delay)
            (sleep or time.sleep)(min(delay, 20))
    raise ProviderError(f"Failed after {attempts} attempts: {type(last).__name__}") from last


class HttpClient:
    def __init__(self, timeout: float = 20.0, contact_email: str | None = None, transport: httpx.BaseTransport | None = None):
        agent = "DeepResearcherAI/0.1 (research assistant" + (f"; mailto:{contact_email}" if contact_email else "") + ")"
        self.client = httpx.Client(timeout=timeout, headers={"User-Agent": agent}, follow_redirects=False,
                                   transport=transport)

    def get_json(self, url: str, params: dict | None = None, headers: dict | None = None) -> dict:
        def call():
            response = self.client.get(url, params=params, headers=headers)
            response.raise_for_status()
            return response.json()
        return with_retries(call)

    def post_json(self, url: str, payload: dict, headers: dict | None = None) -> dict:
        def call():
            response = self.client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()
        return with_retries(call)

    def get_text(self, url: str, params: dict | None = None) -> str:
        def call():
            response = self.client.get(url, params=params)
            response.raise_for_status()
            return response.text
        return with_retries(call)

    def safe_fetch(self, url: str, max_redirects: int = 3) -> str | None:
        """Fetch a public web page's HTML. Returns None (never raises) when blocked or unavailable."""
        for _ in range(max_redirects + 1):
            if not is_public_http_url(url):
                logger.info("Blocked non-public URL")
                return None
            try:
                with self.client.stream("GET", url) as response:
                    if response.is_redirect:
                        url = str(response.next_request.url) if response.next_request else ""
                        continue
                    if response.status_code != 200:
                        return None
                    ctype = response.headers.get("content-type", "")
                    if "html" not in ctype and "text/plain" not in ctype:
                        return None
                    chunks, size = [], 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > MAX_FETCH_BYTES:
                            break
                        chunks.append(chunk)
                    return b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
            except (httpx.HTTPError, ValueError):
                return None
        return None


def is_public_http_url(url: str) -> bool:
    """Allow only http(s) URLs whose host resolves to public IP addresses (SSRF protection)."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    host = parsed.hostname
    if host in ("localhost",) or host.endswith((".local", ".internal")):
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return False
    return True
