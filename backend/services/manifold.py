"""Manifold Markets API client.

Used primarily for development and testing (play-money markets).
"""

import logging
from datetime import datetime, timezone

import httpx

from config import settings

logger = logging.getLogger(__name__)


class ManifoldClient:
    """Client for the Manifold Markets API."""

    def __init__(self) -> None:
        self.base_url: str = settings.manifold_api_url
        self.platform: str = "manifold"

    async def fetch_markets(
        self,
        limit: int = 100,
        min_volume: float = 0,
    ) -> list[dict]:
        """Fetch active binary markets from Manifold.

        Uses the /v0/markets endpoint with pagination via the `before`
        parameter (set to the last market id from the previous page).

        Args:
            limit: Maximum total number of markets to return.
            min_volume: Minimum volume filter (USD-equivalent).

        Returns:
            List of normalized market dicts.
        """
        markets: list[dict] = []
        before: str | None = None
        page_size: int = min(limit, 1000)  # Manifold allows up to 1000 per page

        async with httpx.AsyncClient(timeout=30.0) as client:
            while len(markets) < limit:
                params: dict = {
                    "limit": page_size,
                    "sort": "last-bet-time",
                }
                if before is not None:
                    params["before"] = before

                logger.debug(
                    "Manifold: fetching markets page (before=%s)", before
                )
                resp = await client.get(
                    f"{self.base_url}/v0/markets", params=params
                )
                resp.raise_for_status()
                page: list[dict] = resp.json()

                if not page:
                    logger.info("Manifold: no more pages, stopping pagination")
                    break

                for raw in page:
                    # Only include active binary markets above volume threshold
                    if raw.get("outcomeType") != "BINARY":
                        continue
                    if raw.get("isResolved", False):
                        continue
                    if raw.get("volume", 0) < min_volume:
                        continue

                    markets.append(self.normalize_market(raw))

                    if len(markets) >= limit:
                        break

                # Set cursor for next page
                before = page[-1].get("id")

                # If the page returned fewer items than requested, we're done
                if len(page) < page_size:
                    break

        logger.info(
            "Manifold: fetched %d markets (min_volume=%.0f)",
            len(markets),
            min_volume,
        )
        return markets

    async def check_resolution(self, platform_id: str) -> dict | None:
        """Check if a Manifold market has resolved.

        Args:
            platform_id: The Manifold market ID.

        Returns:
            Dict with resolved/outcome/cancelled status, or None on API error.
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{self.base_url}/v0/market/{platform_id}"
                )
                resp.raise_for_status()
                data: dict = resp.json()

            if not data.get("isResolved", False):
                return {"resolved": False, "outcome": None, "cancelled": False}

            resolution = data.get("resolution", "")
            if resolution == "YES":
                return {"resolved": True, "outcome": True, "cancelled": False}
            elif resolution == "NO":
                return {"resolved": True, "outcome": False, "cancelled": False}
            else:
                # MKT (partial) or CANCEL — treat as cancelled
                return {"resolved": True, "outcome": None, "cancelled": True}

        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning(
                "Manifold: failed to check resolution for %s: %s",
                platform_id,
                exc,
            )
            return None

    async def check_resolutions_batch(
        self, platform_ids: list[str]
    ) -> dict[str, dict]:
        """Check resolution status for multiple markets.

        Args:
            platform_ids: List of Manifold market IDs.

        Returns:
            Dict mapping platform_id to resolution result.
        """
        results: dict[str, dict] = {}
        for pid in platform_ids:
            result = await self.check_resolution(pid)
            if result is not None:
                results[pid] = result
        return results

    def normalize_market(self, raw: dict) -> dict:
        """Map raw Manifold API response to internal market format.

        Args:
            raw: Raw market dict from the Manifold API.

        Returns:
            Normalized market dict with standard field names.
        """
        # Parse close date from epoch milliseconds
        close_date: str | None = None
        close_time_ms = raw.get("closeTime")
        if close_time_ms is not None:
            try:
                close_date = datetime.fromtimestamp(
                    close_time_ms / 1000, tz=timezone.utc
                ).isoformat()
            except (ValueError, OSError, TypeError):
                logger.warning(
                    "Manifold: invalid closeTime %s for market %s",
                    close_time_ms,
                    raw.get("id"),
                )

        # Category: first item of groupSlugs if available
        group_slugs: list[str] = raw.get("groupSlugs", []) or []
        category: str | None = group_slugs[0] if group_slugs else None

        return {
            "platform": self.platform,
            "platform_id": raw["id"],
            "question": raw["question"],
            "description": raw.get("textDescription", ""),
            "resolution_criteria": raw.get("textDescription", ""),
            "category": category,
            "close_date": close_date,
            "price_yes": raw.get("probability", 0.5),
            "volume": raw.get("volume", 0),
            "liquidity": raw.get("totalLiquidity", 0),
        }
