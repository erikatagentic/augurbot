"""Shared HTTP utilities with retry logic for platform API clients.

Retries on transient failures: 5xx server errors, 429 rate limits,
connection errors, and timeouts. Does NOT retry on other 4xx client
errors (auth issues, bad requests).
"""

import logging

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception,
)

logger = logging.getLogger(__name__)


def _is_retryable(exc: BaseException) -> bool:
    """Check if an exception warrants a retry."""
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.PoolTimeout)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status >= 500 or status == 429:
            return True
    return False


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception(_is_retryable),
)
async def request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    **kwargs,
) -> httpx.Response:
    """Make an HTTP request with automatic retry on transient failures.

    Retries up to 3 times with exponential backoff (1s, 2s, 4s) on:
      - Connection errors
      - Timeouts
      - HTTP 5xx responses
      - HTTP 429 rate limit responses

    Args:
        client: httpx async client.
        method: HTTP method (GET, POST, etc.).
        url: Request URL.
        **kwargs: Passed through to ``client.request()``.

    Returns:
        The HTTP response.

    Raises:
        httpx.HTTPStatusError: On non-retryable HTTP errors (4xx).
        httpx.ConnectError: If all retries are exhausted.
    """
    resp = await client.request(method, url, **kwargs)
    resp.raise_for_status()
    return resp
