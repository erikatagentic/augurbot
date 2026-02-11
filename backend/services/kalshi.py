"""Kalshi API client.

Kalshi is a US-regulated prediction market (CFTC-regulated exchange).

Supports two authentication modes:
  - RSA-PSS (recommended): Per-request signing with API key + private key PEM.
    No token expiry. Set KALSHI_API_KEY and KALSHI_PRIVATE_KEY_PATH.
  - Legacy Bearer token: Cookie-based login with email/password.
    Tokens expire every 30 minutes. Set KALSHI_EMAIL and KALSHI_PASSWORD.

RSA-PSS takes precedence when both are configured.

Prices are returned in CENTS (0-100) and must be divided by 100 for
the internal decimal (0.0-1.0) representation.
"""

import base64
import logging
import time

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from config import settings

logger = logging.getLogger(__name__)


class KalshiClient:
    """Client for the Kalshi trading API."""

    def __init__(self) -> None:
        self.base_url: str = settings.kalshi_api_url
        self.platform: str = "kalshi"
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._private_key = None
        self._api_key: str = settings.kalshi_api_key

    # ── Authentication ──

    def _is_rsa_configured(self) -> bool:
        """Check if RSA-PSS authentication is configured."""
        return bool(
            self._api_key
            and (settings.kalshi_private_key_path or settings.kalshi_private_key)
        )

    def _is_legacy_configured(self) -> bool:
        """Check if legacy email/password authentication is configured."""
        return bool(settings.kalshi_email and settings.kalshi_password)

    def is_configured(self) -> bool:
        """Check if any authentication method is configured."""
        return self._is_rsa_configured() or self._is_legacy_configured()

    def _load_private_key(self) -> None:
        """Load RSA private key (lazy, cached on instance).

        Supports two modes:
          - Inline PEM via KALSHI_PRIVATE_KEY env var (for cloud deploys)
          - File path via KALSHI_PRIVATE_KEY_PATH (for local dev)
        """
        if self._private_key is not None:
            return

        if settings.kalshi_private_key:
            # Inline PEM content from env var
            # Railway/cloud env vars may store literal \n — convert to real newlines
            raw = settings.kalshi_private_key.replace("\\n", "\n")

            # If PEM headers are missing, add them (bare base64 from dashboard)
            if "-----" not in raw:
                # Strip any whitespace/newlines and re-wrap at 64 chars
                body = raw.replace("\n", "").replace("\r", "").strip()
                body_lines = [body[i:i+64] for i in range(0, len(body), 64)]
                raw = (
                    "-----BEGIN RSA PRIVATE KEY-----\n"
                    + "\n".join(body_lines)
                    + "\n-----END RSA PRIVATE KEY-----\n"
                )
            elif "\n" not in raw.strip():
                # Headers present but newlines stripped
                parts = raw.split("-----")
                header = f"-----{parts[1]}-----"
                footer = f"-----{parts[-2]}-----"
                body = parts[3] if len(parts) >= 5 else ""
                body_lines = [body[i:i+64] for i in range(0, len(body), 64)]
                raw = header + "\n" + "\n".join(body_lines) + "\n" + footer + "\n"

            logger.info(
                "Kalshi: PEM starts with %s, length=%d, newlines=%d",
                repr(raw[:30]),
                len(raw),
                raw.count("\n"),
            )
            pem_data = raw.encode("utf-8")
            self._private_key = serialization.load_pem_private_key(
                pem_data, password=None
            )
            logger.info("Kalshi: loaded RSA private key from env var")
        elif settings.kalshi_private_key_path:
            # File path
            with open(settings.kalshi_private_key_path, "rb") as f:
                self._private_key = serialization.load_pem_private_key(
                    f.read(), password=None
                )
            logger.info("Kalshi: loaded RSA private key from file")
        else:
            raise ValueError(
                "Kalshi RSA key not configured. "
                "Set KALSHI_PRIVATE_KEY (inline PEM) or KALSHI_PRIVATE_KEY_PATH (file)."
            )

    def _sign_request(self, method: str, path: str) -> dict[str, str]:
        """Generate Kalshi RSA-PSS auth headers for a request.

        Signature = RSA-PSS-sign(timestamp + method + path)

        Args:
            method: HTTP method (GET, POST, etc.).
            path: Request path (e.g. /trade-api/v2/markets).

        Returns:
            Dict with KALSHI-ACCESS-KEY, KALSHI-ACCESS-SIGNATURE,
            KALSHI-ACCESS-TIMESTAMP headers.
        """
        self._load_private_key()
        timestamp = str(int(time.time() * 1000))
        message = f"{timestamp}{method.upper()}{path}"

        signature = self._private_key.sign(
            message.encode("utf-8"),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )

        return {
            "KALSHI-ACCESS-KEY": self._api_key,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode(
                "utf-8"
            ),
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
        }

    def _auth_headers(
        self, method: str = "GET", path: str = ""
    ) -> dict[str, str]:
        """Return authorization headers for authenticated requests.

        Uses RSA-PSS when configured, falls back to legacy Bearer token.

        Args:
            method: HTTP method for RSA signing.
            path: Request path for RSA signing.

        Returns:
            Dict with the appropriate auth headers.
        """
        if self._is_rsa_configured():
            return self._sign_request(method, path)
        return {"Authorization": f"Bearer {self._token}"}

    async def _ensure_auth(self) -> None:
        """Ensure authentication is ready.

        For RSA-PSS: no-op (signing is per-request).
        For legacy: login and obtain/refresh Bearer token.

        Raises:
            ValueError: If no credentials are configured.
            httpx.HTTPStatusError: If legacy login request fails.
        """
        if self._is_rsa_configured():
            return  # RSA signs per-request, no session token needed

        if not self._is_legacy_configured():
            raise ValueError(
                "Kalshi credentials not configured. "
                "Set KALSHI_API_KEY + KALSHI_PRIVATE_KEY_PATH (RSA), "
                "or KALSHI_EMAIL + KALSHI_PASSWORD (legacy)."
            )

        # Re-use existing token if it has more than 60 seconds remaining
        if self._token and time.time() < self._token_expires_at - 60:
            return

        logger.info("Kalshi: authenticating via legacy login")

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
        self._token_expires_at = time.time() + 25 * 60

        logger.info("Kalshi: authenticated successfully (legacy)")

    # ── Market Data ──

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
        path = "/trade-api/v2/markets"
        max_pages = 50  # Cap pagination to avoid exhausting all Kalshi markets
        page_count = 0

        async with httpx.AsyncClient(timeout=30.0) as client:
            while len(markets) < limit and page_count < max_pages:
                page_count += 1
                params: dict = {
                    "status": "open",
                    "limit": min(limit - len(markets), 100),
                }
                if cursor:
                    params["cursor"] = cursor

                logger.debug(
                    "Kalshi: fetching markets page (cursor=%s)", cursor
                )

                await self._ensure_auth()

                headers = self._auth_headers("GET", path)
                url = f"{self.base_url}/markets"

                resp = await client.get(
                    url,
                    params=params,
                    headers=headers,
                )
                if resp.status_code != 200:
                    logger.error(
                        "Kalshi: API returned %d: %s",
                        resp.status_code,
                        resp.text[:500],
                    )
                resp.raise_for_status()
                data: dict = resp.json()

                page: list[dict] = data.get("markets", [])
                if not page:
                    logger.info(
                        "Kalshi: no more pages, stopping pagination"
                    )
                    break

                # Log first market's volume-related fields for debugging
                if page_count == 1 and page:
                    sample = page[0]
                    logger.info(
                        "Kalshi: sample market keys=%s  volume=%s  "
                        "volume_24h=%s  dollar_volume=%s  open_interest=%s  "
                        "ticker=%s",
                        list(sample.keys())[:15],
                        sample.get("volume"),
                        sample.get("volume_24h"),
                        sample.get("dollar_volume"),
                        sample.get("open_interest"),
                        sample.get("ticker"),
                    )

                for raw in page:
                    volume = float(raw.get("volume", 0))
                    if volume < min_volume:
                        continue

                    markets.append(self.normalize_market(raw))

                    if len(markets) >= limit:
                        break

                cursor = data.get("cursor")
                if not cursor:
                    break

        logger.info(
            "Kalshi: fetched %d markets (min_volume=%.0f, pages=%d/%d)",
            len(markets),
            min_volume,
            page_count,
            max_pages,
        )
        return markets

    # ── Resolution Checking ──

    async def check_resolution(self, platform_id: str) -> dict | None:
        """Check if a Kalshi market has resolved.

        Args:
            platform_id: The Kalshi market ticker.

        Returns:
            Dict with resolved/outcome/cancelled status, or None on API error.
        """
        try:
            await self._ensure_auth()
            path = f"/trade-api/v2/markets/{platform_id}"

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{self.base_url}/markets/{platform_id}",
                    headers=self._auth_headers("GET", path),
                )
                resp.raise_for_status()
                data: dict = resp.json()

            market = data.get("market", data)
            status = market.get("status", "")

            if status != "finalized":
                return {"resolved": False, "outcome": None, "cancelled": False}

            result_str = market.get("result", "").lower()
            if result_str == "yes":
                return {"resolved": True, "outcome": True, "cancelled": False}
            elif result_str == "no":
                return {"resolved": True, "outcome": False, "cancelled": False}
            else:
                return {"resolved": True, "outcome": None, "cancelled": True}

        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning(
                "Kalshi: failed to check resolution for %s: %s",
                platform_id,
                exc,
            )
            return None

    async def check_resolutions_batch(
        self, platform_ids: list[str]
    ) -> dict[str, dict]:
        """Check resolution status for multiple markets.

        Args:
            platform_ids: List of Kalshi market tickers.

        Returns:
            Dict mapping platform_id to resolution result.
        """
        results: dict[str, dict] = {}
        for pid in platform_ids:
            result = await self.check_resolution(pid)
            if result is not None:
                results[pid] = result
        return results

    # ── Trade Data ──

    async def fetch_fills(self, limit: int = 500) -> list[dict]:
        """Fetch trade fill history from Kalshi portfolio API.

        Each fill represents a matched trade (a buy or sell that was executed).

        Args:
            limit: Maximum number of fills to return.

        Returns:
            List of raw fill dicts from Kalshi API. Each contains:
            fill_id, ticker, side (yes/no), action (buy/sell),
            count, yes_price, no_price, fee_cost, created_time.
        """
        await self._ensure_auth()

        fills: list[dict] = []
        cursor: str | None = None
        path = "/trade-api/v2/portfolio/fills"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                while len(fills) < limit:
                    params: dict = {
                        "limit": min(limit - len(fills), 100),
                    }
                    if cursor:
                        params["cursor"] = cursor

                    resp = await client.get(
                        f"{self.base_url}/portfolio/fills",
                        params=params,
                        headers=self._auth_headers("GET", path),
                    )
                    resp.raise_for_status()
                    data = resp.json()

                    page = data.get("fills", [])
                    if not page:
                        break
                    fills.extend(page)

                    cursor = data.get("cursor")
                    if not cursor:
                        break

            logger.info("Kalshi: fetched %d fills", len(fills))
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Kalshi: failed to fetch fills: %s", exc)

        return fills

    async def fetch_positions(self) -> list[dict]:
        """Fetch current open positions from Kalshi portfolio API.

        Returns:
            List of raw position dicts from Kalshi API.
        """
        await self._ensure_auth()
        path = "/trade-api/v2/portfolio/positions"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{self.base_url}/portfolio/positions",
                    headers=self._auth_headers("GET", path),
                )
                resp.raise_for_status()
                data = resp.json()

            positions = data.get("market_positions", [])
            logger.info("Kalshi: fetched %d positions", len(positions))
            return positions
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Kalshi: failed to fetch positions: %s", exc)
            return []

    # ── Normalization ──

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
