"""Polymarket API client.

Uses two base URLs:
  - Gamma API (https://gamma-api.polymarket.com) for market discovery
  - CLOB API  (https://clob.polymarket.com)      for live price data

Rate limiting: 0.7s sleep between CLOB API calls to stay under 100 req/min.
"""

import asyncio
import json
import logging

import httpx

from config import settings

logger = logging.getLogger(__name__)


class PolymarketClient:
    """Client for the Polymarket Gamma + CLOB APIs."""

    def __init__(self) -> None:
        self.gamma_url: str = settings.polymarket_gamma_url
        self.clob_url: str = settings.polymarket_api_url
        self.platform: str = "polymarket"

    async def fetch_markets(
        self,
        limit: int = 100,
        min_volume: float = 10000.0,
    ) -> list[dict]:
        """Fetch active markets from the Gamma API and enrich with live prices.

        Markets are sorted by volume descending and filtered by minimum volume.
        For each market that has a YES token id, a live midpoint price is
        fetched from the CLOB API (with rate-limiting sleeps).

        Args:
            limit: Maximum total number of markets to return.
            min_volume: Minimum volume in USD.

        Returns:
            List of normalized market dicts.
        """
        markets: list[dict] = []
        offset: int = 0
        page_size: int = min(limit, 100)  # Gamma API caps at 100 per request

        async with httpx.AsyncClient(timeout=30.0) as client:
            while len(markets) < limit:
                params: dict = {
                    "limit": page_size,
                    "offset": offset,
                    "closed": False,
                    "volume_num_min": min_volume,
                    "order": "volume",
                    "ascending": False,
                }

                logger.debug(
                    "Polymarket Gamma: fetching markets (offset=%d)", offset
                )
                resp = await client.get(
                    f"{self.gamma_url}/markets", params=params
                )
                resp.raise_for_status()
                page: list[dict] = resp.json()

                if not page:
                    logger.info(
                        "Polymarket Gamma: no more pages, stopping pagination"
                    )
                    break

                for raw in page:
                    # Extract YES token id for live price lookup
                    yes_token_id = self._extract_yes_token_id(raw)

                    # Fetch live midpoint price from CLOB API
                    price: float | None = None
                    if yes_token_id:
                        price = await self._fetch_price(client, yes_token_id)

                    markets.append(self.normalize_market(raw, price=price))

                    if len(markets) >= limit:
                        break

                offset += page_size

                # If the page returned fewer items than requested, we're done
                if len(page) < page_size:
                    break

        logger.info(
            "Polymarket: fetched %d markets (min_volume=%.0f)",
            len(markets),
            min_volume,
        )
        return markets

    async def fetch_price(self, token_id: str) -> float | None:
        """Fetch the current midpoint price for a token from the CLOB API.

        This is the public-facing method that creates its own HTTP client.

        Args:
            token_id: The CLOB token id (YES outcome).

        Returns:
            Midpoint price as a float, or None on failure.
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            return await self._fetch_price(client, token_id)

    async def _fetch_price(
        self,
        client: httpx.AsyncClient,
        token_id: str,
    ) -> float | None:
        """Internal: fetch midpoint price with rate-limiting sleep.

        Args:
            client: Shared httpx async client.
            token_id: The CLOB token id (YES outcome).

        Returns:
            Midpoint price as a float, or None on failure.
        """
        try:
            # Rate limit: stay under 100 req/min on CLOB API
            await asyncio.sleep(0.7)

            resp = await client.get(
                f"{self.clob_url}/midpoint",
                params={"token_id": token_id},
            )
            resp.raise_for_status()
            data: dict = resp.json()
            return float(data.get("mid", 0.5))
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning(
                "Polymarket CLOB: failed to fetch price for token %s: %s",
                token_id,
                exc,
            )
            return None

    async def fetch_positions(self, wallet_address: str) -> list[dict]:
        """Fetch current positions from Polymarket Data API.

        Uses the public Data API — no authentication needed, just the
        user's wallet address.

        Args:
            wallet_address: Ethereum/Polygon wallet address (0x...).

        Returns:
            List of raw position dicts with conditionId, outcomeIndex,
            size, avgPrice, currentValue, cashPnl, title, etc.
        """
        if not wallet_address:
            raise ValueError("Polymarket wallet address not provided")

        data_api_url = settings.polymarket_data_api_url
        positions: list[dict] = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            offset = 0
            page_size = 100

            while True:
                params = {
                    "user": wallet_address.lower(),
                    "limit": page_size,
                    "offset": offset,
                }
                resp = await client.get(
                    f"{data_api_url}/positions",
                    params=params,
                )
                resp.raise_for_status()
                page = resp.json()

                if not page:
                    break

                positions.extend(page)

                if len(page) < page_size:
                    break
                offset += page_size

        logger.info(
            "Polymarket: fetched %d positions for wallet %s...%s",
            len(positions),
            wallet_address[:6],
            wallet_address[-4:],
        )
        return positions

    async def check_resolution(self, platform_id: str) -> dict | None:
        """Check if a Polymarket market has resolved.

        Args:
            platform_id: The Polymarket condition ID.

        Returns:
            Dict with resolved/outcome/cancelled status, or None on API error.
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Rate limit: stay under 100 req/min on Gamma API
                await asyncio.sleep(0.7)

                resp = await client.get(
                    f"{self.gamma_url}/markets/{platform_id}"
                )
                resp.raise_for_status()
                data: dict = resp.json()

            if not data.get("resolved", False):
                return {"resolved": False, "outcome": None, "cancelled": False}

            # Determine outcome from outcomePrices
            outcome_prices = data.get("outcomePrices")
            if outcome_prices:
                yes_price = self._parse_outcome_prices(outcome_prices)
                if yes_price >= 0.95:
                    return {"resolved": True, "outcome": True, "cancelled": False}
                elif yes_price <= 0.05:
                    return {"resolved": True, "outcome": False, "cancelled": False}

            # Resolved but outcome unclear — treat as cancelled
            return {"resolved": True, "outcome": None, "cancelled": True}

        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning(
                "Polymarket: failed to check resolution for %s: %s",
                platform_id,
                exc,
            )
            return None

    async def check_resolutions_batch(
        self, platform_ids: list[str]
    ) -> dict[str, dict]:
        """Check resolution status for multiple markets.

        Args:
            platform_ids: List of Polymarket condition IDs.

        Returns:
            Dict mapping platform_id to resolution result.
        """
        results: dict[str, dict] = {}
        for pid in platform_ids:
            result = await self.check_resolution(pid)
            if result is not None:
                results[pid] = result
        return results

    def normalize_market(
        self,
        raw: dict,
        price: float | None = None,
    ) -> dict:
        """Map raw Gamma API response to internal market format.

        Args:
            raw: Raw market dict from the Gamma API.
            price: Live midpoint price from CLOB, or None.

        Returns:
            Normalized market dict with standard field names.
        """
        # Determine price_yes: prefer live CLOB price, fall back to Gamma data
        price_yes: float = 0.5
        if price is not None:
            price_yes = price
        else:
            outcome_prices = raw.get("outcomePrices")
            if outcome_prices:
                price_yes = self._parse_outcome_prices(outcome_prices)

        yes_token_id = self._extract_yes_token_id(raw)

        return {
            "platform": self.platform,
            "platform_id": str(raw.get("id", raw.get("conditionId", ""))),
            "question": raw.get("question", ""),
            "description": raw.get("description", ""),
            "resolution_criteria": raw.get(
                "resolutionSource", raw.get("description", "")
            ),
            "category": raw.get("category", ""),
            "close_date": raw.get("endDate"),
            "price_yes": price_yes,
            "volume": float(raw.get("volume", 0) or 0),
            "liquidity": float(raw.get("liquidity", 0) or 0),
            "yes_token_id": yes_token_id,
        }

    @staticmethod
    def _extract_yes_token_id(raw: dict) -> str | None:
        """Extract the YES token id from clobTokenIds.

        The field can be a JSON-encoded list string or a Python list.
        The first token is assumed to be the YES outcome.

        Args:
            raw: Raw market dict.

        Returns:
            YES token id string, or None if unavailable.
        """
        clob_token_ids = raw.get("clobTokenIds")
        if not clob_token_ids:
            return None

        # Handle comma-separated string
        if isinstance(clob_token_ids, str):
            # Could be a JSON array string like '["abc","def"]'
            try:
                parsed = json.loads(clob_token_ids)
                if isinstance(parsed, list) and parsed:
                    return str(parsed[0])
            except (json.JSONDecodeError, ValueError):
                pass
            # Or a plain comma-separated string
            parts = [p.strip() for p in clob_token_ids.split(",") if p.strip()]
            return parts[0] if parts else None

        # Handle list
        if isinstance(clob_token_ids, list) and clob_token_ids:
            return str(clob_token_ids[0])

        return None

    @staticmethod
    def _parse_outcome_prices(outcome_prices: str | list) -> float:
        """Parse the YES price from the outcomePrices field.

        The field can be a JSON-encoded list string like '["0.65","0.35"]'
        or a Python list. The first value is the YES price.

        Args:
            outcome_prices: Raw outcomePrices field.

        Returns:
            YES price as a float, defaulting to 0.5 on failure.
        """
        try:
            if isinstance(outcome_prices, str):
                parsed = json.loads(outcome_prices)
            else:
                parsed = outcome_prices

            if isinstance(parsed, list) and parsed:
                return float(parsed[0])
        except (json.JSONDecodeError, ValueError, IndexError):
            pass

        return 0.5
