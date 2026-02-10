"""Kalshi API client.

Kalshi is a US-regulated prediction market (CFTC-regulated exchange).
Authentication tokens expire every 30 minutes, so the client automatically
re-authenticates when the token is within 5 minutes of expiry.

Prices are returned in CENTS (0-100) and must be divided by 100 for
the internal decimal (0.0-1.0) representation.
"""

import logging
import time

import httpx

from config import settings

logger = logging.getLogger(__name__)


class KalshiClient:
    """Client for the Kalshi trading API."""

    def __init__(self) -> None:
        self.base_url: str = settings.kalshi_api_url
        self.platform: str = "kalshi"
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    async def _ensure_auth(self) -> None:
        """Authenticate with Kalshi and obtain an API token.

        Tokens expire every 30 minutes. This method refreshes the token
        proactively at 25 minutes to avoid mid-request expiry.

        Raises:
            ValueError: If Kalshi credentials are not configured.
            httpx.HTTPStatusError: If the login request fails.
        """
        if not settings.kalshi_email or not settings.kalshi_password:
            raise ValueError(
                "Kalshi credentials not configured. "
                "Set KALSHI_EMAIL and KALSHI_PASSWORD environment variables."
            )

        # Re-use existing token if it has more than 60 seconds remaining
        if self._token and time.time() < self._token_expires_at - 60:
            return

        logger.info("Kalshi: authenticating (token expired or missing)")

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.base_url}/login",
                json={
                    "email": settings.kalshi_email,
                    "password": settings.kalshi_password,
                },
            )
            resp.raise_for_status()
            data: dict = resp.json()

        self._token = data.get("token", "")
        # Refresh before the 30-minute expiry: set internal expiry to 25 min
        self._token_expires_at = time.time() + 25 * 60

        logger.info("Kalshi: authenticated successfully")

    def _auth_headers(self) -> dict[str, str]:
        """Return authorization headers for authenticated requests.

        Returns:
            Dict with the Authorization header.
        """
        return {"Authorization": f"Bearer {self._token}"}

    async def fetch_markets(
        self,
        limit: int = 100,
        min_volume: float = 10000.0,
    ) -> list[dict]:
        """Fetch active markets from Kalshi.

        Uses cursor-based pagination. Markets are filtered by status=open
        and post-filtered by minimum volume.

        Args:
            limit: Maximum total number of markets to return.
            min_volume: Minimum volume filter.

        Returns:
            List of normalized market dicts.
        """
        await self._ensure_auth()

        markets: list[dict] = []
        cursor: str | None = None

        async with httpx.AsyncClient(timeout=30.0) as client:
            while len(markets) < limit:
                params: dict = {
                    "status": "open",
                    "limit": min(limit - len(markets), 100),
                }
                if cursor:
                    params["cursor"] = cursor

                logger.debug(
                    "Kalshi: fetching markets page (cursor=%s)", cursor
                )

                # Re-authenticate if token is near expiry
                await self._ensure_auth()

                resp = await client.get(
                    f"{self.base_url}/markets",
                    params=params,
                    headers=self._auth_headers(),
                )
                resp.raise_for_status()
                data: dict = resp.json()

                page: list[dict] = data.get("markets", [])
                if not page:
                    logger.info(
                        "Kalshi: no more pages, stopping pagination"
                    )
                    break

                for raw in page:
                    volume = float(raw.get("volume", 0))
                    if volume < min_volume:
                        continue

                    markets.append(self.normalize_market(raw))

                    if len(markets) >= limit:
                        break

                # Cursor for next page
                cursor = data.get("cursor")
                if not cursor:
                    break

        logger.info(
            "Kalshi: fetched %d markets (min_volume=%.0f)",
            len(markets),
            min_volume,
        )
        return markets

    def normalize_market(self, raw: dict) -> dict:
        """Map raw Kalshi API response to internal market format.

        Kalshi prices are in CENTS (0-100), so they are divided by 100
        to produce the standard decimal (0.0-1.0) representation.

        Args:
            raw: Raw market dict from the Kalshi API.

        Returns:
            Normalized market dict with standard field names.
        """
        # Price: Kalshi uses cents (0-100), convert to decimal
        price_cents = raw.get("yes_ask", 50)
        price_yes: float = price_cents / 100

        # Close date: prefer close_time, fall back to expiration_time
        close_date: str | None = raw.get("close_time") or raw.get(
            "expiration_time"
        )

        return {
            "platform": self.platform,
            "platform_id": raw.get("ticker", ""),
            "question": raw.get("title", raw.get("subtitle", "")),
            "description": raw.get("rules_primary", ""),
            "resolution_criteria": raw.get("rules_primary", ""),
            "category": raw.get("category", ""),
            "close_date": close_date,
            "price_yes": price_yes,
            "volume": float(raw.get("volume", 0)),
            "liquidity": float(raw.get("open_interest", 0)),
        }
