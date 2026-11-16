"""Async HTTP client for the Hava (hava.io) REST API.

The API is documented at https://app.swaggerhub.com/apis-docs/H252/hava
(OpenAPI 3.0.1, vendored in ``reference/hava-openapi-1.1.6.json``). It is a
flat, Bearer-token REST API rooted at ``https://api.hava.io``; self-hosted
installs expose the same surface on their own host (``HAVA_ENDPOINT``).
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, Mapping
from urllib.parse import urljoin, urlsplit

import httpx

from . import auth
from .errors import HavaConfigError, HavaError

DEFAULT_TIMEOUT = 60.0

_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)

__all__ = [
    "as_results",
    "HavaClient",
    "HavaError",
    "HavaConfigError",
    "get_client",
    "set_client",
    "job_id_from_location",
]


def _clean(params: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Drop ``None`` values so unset optional arguments are not sent."""
    if not params:
        return None
    cleaned = {k: v for k, v in params.items() if v is not None}
    return cleaned or None


def _error_details(response: httpx.Response) -> str:
    """Render a Hava error body (a list of ``{code,title,detail,path}``)."""
    try:
        payload = response.json()
    except ValueError:
        return (response.text or "").strip()[:500]
    if isinstance(payload, dict):
        payload = payload.get("errors", payload)
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        return str(payload)[:500]
    parts: list[str] = []
    for item in payload:
        if not isinstance(item, dict):
            parts.append(str(item))
            continue
        detail = item.get("detail") or item.get("title") or item.get("code") or ""
        path = item.get("path")
        parts.append(f"{path}: {detail}" if path else str(detail))
    return "; ".join(p for p in parts if p)[:500]


def _describe_error(response: httpx.Response, method: str, path: str) -> str:
    status = response.status_code
    details = _error_details(response)
    suffix = f" Details: {details}" if details else ""
    where = f"{method.upper()} {path}"
    if status == 401:
        return (
            f"Hava rejected the API token (401 Unauthorized on {where}). It is expired, "
            f"revoked, or for a different endpoint. Update the HAVA_API_TOKEN "
            f"configuration value with a fresh token.{suffix}"
        )
    if status == 403:
        return (
            f"Hava denied access (403 Forbidden on {where}). The token's account does not "
            f"have permission for this resource, or the plan does not include API "
            f"access (Teams/Business or self-hosted required).{suffix}"
        )
    if status == 404:
        return (
            f"Hava returned 404 Not Found for {where}. Check the ID belongs to this "
            f"account - hava_list_diagrams returns valid diagram and view IDs.{suffix}"
        )
    if status == 422:
        return f"Hava rejected the request as invalid (422 on {where}).{suffix}"
    if status == 429:
        retry = response.headers.get("retry-after")
        wait = f" Retry after {retry}s." if retry else ""
        return f"Hava rate limit exceeded (429 on {where}).{wait}{suffix}"
    if status >= 500:
        return f"Hava returned a server error ({status} on {where}). Retry shortly.{suffix}"
    return f"Hava request failed with HTTP {status} on {where}.{suffix}"


class HavaClient:
    """Thin async wrapper around the Hava REST API.

    Redirects are deliberately *not* followed: ``GET /jobs/{id}`` answers with
    ``303 See Other`` plus a ``location`` header pointing at the finished
    artifact, and that header is the payload we care about.
    """

    def __init__(
        self,
        token: str | None = None,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._explicit_token = token
        self.base_url = (base_url or auth.default_base_url()).rstrip("/")
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()

    # -- auth ------------------------------------------------------------- #

    @property
    def token(self) -> str:
        """The Bearer token, resolved lazily so startup never needs one."""
        if self._explicit_token:
            return self._explicit_token
        return auth.require()

    def credential(self) -> auth.Credential | None:
        """The resolved credential and its origin, or ``None`` if not logged in."""
        if self._explicit_token:
            return auth.Credential(self._explicit_token, "explicit")
        return auth.resolve()

    # -- transport -------------------------------------------------------- #

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            async with self._lock:
                if self._client is None or self._client.is_closed:
                    self._client = httpx.AsyncClient(
                        base_url=self.base_url,
                        timeout=httpx.Timeout(self.timeout),
                        follow_redirects=False,
                        headers={"Accept": "application/json"},
                    )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any | None = None,
    ) -> httpx.Response:
        """Perform an authenticated request, raising ``HavaError`` on failure."""
        client = await self._http()
        try:
            response = await client.request(
                method,
                path,
                params=_clean(params),
                json=json,
                headers={"Authorization": f"Bearer {self.token}"},
            )
        except httpx.TimeoutException as exc:
            raise HavaError(
                f"Hava API request timed out after {self.timeout:g}s "
                f"({method.upper()} {path})."
            ) from exc
        except httpx.HTTPError as exc:
            raise HavaError(
                f"Could not reach the Hava API at {self.base_url} "
                f"({method.upper()} {path}): {exc}"
            ) from exc
        if response.status_code >= 400:
            raise HavaError(_describe_error(response, method, path))
        return response

    async def get_json(self, path: str, **kwargs: Any) -> Any:
        response = await self.request("GET", path, **kwargs)
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise HavaError(
                f"Hava returned a non-JSON body for GET {path} "
                f"(content-type {response.headers.get('content-type')!r})."
            ) from exc

    # -- helpers ---------------------------------------------------------- #

    def absolute_url(self, location: str) -> str:
        """Turn a ``location`` header into an absolute URL."""
        if location.startswith(("http://", "https://")):
            return location
        return urljoin(self.base_url + "/", location.lstrip("/"))

    def is_api_host(self, url: str) -> bool:
        """True when ``url`` points at the Hava API itself (so it needs the token)."""
        return urlsplit(url).netloc == urlsplit(self.base_url).netloc

    async def download(self, url: str, timeout: float = 300.0) -> tuple[bytes, str | None]:
        """Fetch an export artifact. Presigned URLs are fetched unauthenticated."""
        headers: dict[str, str] = {}
        if self.is_api_host(url):
            headers["Authorization"] = f"Bearer {self.token}"
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout), follow_redirects=True
        ) as client:
            try:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise HavaError(
                    f"Downloading the export failed with HTTP "
                    f"{exc.response.status_code} from {url}."
                ) from exc
            except httpx.HTTPError as exc:
                raise HavaError(f"Downloading the export from {url} failed: {exc}") from exc
        return response.content, response.headers.get("content-type")


def as_results(payload: Any) -> list[Any]:
    """Normalise a Hava list response.

    Most list endpoints answer ``{"total_size": n, "results": [...]}``, but the
    spec documents ``GET /sources`` as a bare array and the live API returns the
    object form, so accept both.
    """
    if isinstance(payload, dict):
        return list(payload.get("results") or [])
    return list(payload or [])


def job_id_from_location(location: str) -> str | None:
    """Extract a job UUID from a ``location`` header such as ``/jobs/<uuid>``."""
    if not location:
        return None
    match = _UUID_RE.search(location)
    if match:
        return match.group(0)
    tail = urlsplit(location).path.rstrip("/").rsplit("/", 1)[-1]
    return tail or None


_default_client: HavaClient | None = None


def get_client() -> HavaClient:
    """Return the process-wide client, created on first use."""
    global _default_client
    if _default_client is None:
        _default_client = HavaClient()
    return _default_client


def set_client(client: HavaClient | None) -> None:
    """Replace the process-wide client (used by tests)."""
    global _default_client
    _default_client = client
