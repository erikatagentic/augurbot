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
import re
import time
from datetime import datetime, timezone

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from config import settings
from services.http_utils import request_with_retry

logger = logging.getLogger(__name__)

# ── Market Filtering Helpers ──

# Categories to include
ALLOWED_CATEGORIES: set[str] = {"sports", "economics"}

# ── Series Ticker-Based Sport Detection (most reliable) ──
# Maps Kalshi series_ticker prefixes to sport type.
# Checked longest-prefix-first to avoid false matches.
_SPORT_SERIES_PREFIXES: dict[str, str] = {
    # College (check before pro leagues — longer prefixes)
    "KXNCAAMB": "NCAA Basketball",
    "KXNCAAWB": "NCAA Basketball",
    "KXNCAAF": "NCAA Football",
    "KXNCAABB": "NCAA Baseball",
    "KXNCAALAX": "Lacrosse",
    # Basketball
    "KXNBA": "NBA",
    "KXWNBA": "WNBA",
    "KXEUROLEAGUE": "Basketball",
    "KXEUROCUP": "Basketball",
    "KXFIBA": "Basketball",
    # Football
    "KXNFL": "NFL",
    "KXSB": "NFL",
    "KXAFC": "NFL",
    "KXNFC": "NFL",
    # Baseball
    "KXMLB": "MLB",
    # Hockey
    "KXNHL": "NHL",
    "KXAHL": "Hockey",
    "KXKHL": "Hockey",
    "KXSHL": "Hockey",
    "KXDEL": "Hockey",
    "KXLIIGA": "Hockey",
    "KXELH": "Hockey",
    # Soccer — all leagues
    "KXEPL": "Soccer",
    "KXUCL": "Soccer",
    "KXUEL": "Soccer",
    "KXUECL": "Soccer",
    "KXLALIGA": "Soccer",
    "KXBUNDESLIGA": "Soccer",
    "KXSERIEA": "Soccer",
    "KXLIGUE1": "Soccer",
    "KXMLS": "Soccer",
    "KXNWSL": "Soccer",
    "KXFACUP": "Soccer",
    "KXEFLCUP": "Soccer",
    "KXEFLCHAMPIONSHIP": "Soccer",
    "KXEREDIVISIE": "Soccer",
    "KXKNVBCUP": "Soccer",
    "KXSCOTTISHPREM": "Soccer",
    "KXSUPERLIG": "Soccer",
    "KXSUPERLEAGUEGREECE": "Soccer",
    "KXEKSTRAKLASA": "Soccer",
    "KXARGPREMDIV": "Soccer",
    "KXSAUDIPL": "Soccer",
    "KXALEAGUE": "Soccer",
    "KXDIMAYOR": "Soccer",
    "KXLIGAMX": "Soccer",
    "KXLIGAPORTUGAL": "Soccer",
    "KXBRASILEIRAO": "Soccer",
    "KXBELGIANPRO": "Soccer",
    "KXCROATIANHNL": "Soccer",
    "KXDANISHSUPER": "Soccer",
    "KXSWISSSUPER": "Soccer",
    "KXCOPADEL": "Soccer",
    "KXCOPPAITALIA": "Soccer",
    "KXDFBPOKAL": "Soccer",
    "KXCOUPEDEFRANCE": "Soccer",
    "KXCLUBWORLDCUP": "Soccer",
    "KXAFCCHAMPIONS": "Soccer",
    "KXJLEAGUE": "Soccer",
    "KXKLEAGUE": "Soccer",
    "KXWORLDCUP": "Soccer",
    # Tennis
    "KXATP": "Tennis",
    "KXWTA": "Tennis",
    "KXGRANDSLAM": "Tennis",
    "KXDAVISCUP": "Tennis",
    "KXLAVERCUP": "Tennis",
    "KXUNITEDCUP": "Tennis",
    # UFC / MMA / Boxing
    "KXUFC": "UFC/MMA",
    "KXBOXING": "Boxing",
    # Motorsport
    "KXF1": "F1",
    "KXNASCAR": "NASCAR",
    "KXINDY": "IndyCar",
    # Cricket
    "KXIPL": "Cricket",
    "KXWPL": "Cricket",
    "KXT20": "Cricket",
    "KXCRICKET": "Cricket",
    # Winter Olympics
    "KXWO": "Olympics",
    # Golf
    "KXPGA": "Golf",
    "KXLIV": "Golf",
    "KXMASTERS": "Golf",
    "KXTGL": "Golf",
    "KXUSOPENGOLF": "Golf",
    # Esports
    "KXCS2": "Esports",
    "KXLOL": "Esports",
    "KXVALORANT": "Esports",
    "KXDOTA2": "Esports",
    "KXCOD": "Esports",
    "KXPUBG": "Esports",
    "KXOVERWATCH": "Esports",
    "KXRAINBOW": "Esports",
    "KXBRAWL": "Esports",
    # Chess
    "KXCHESS": "Chess",
    "KXFIDE": "Chess",
    # Rugby
    "KXRUGBY": "Rugby",
    "KXSIXNATIONS": "Rugby",
    "KXNRL": "Rugby",
    # Darts
    "KXDARTS": "Darts",
    "KXPREMDARTS": "Darts",
    # Table Tennis
    "KXTABLETENNIS": "Table Tennis",
    "KXTTELITE": "Table Tennis",
    # Lacrosse
    "KXLAX": "Lacrosse",
}

# Pre-sorted by prefix length (descending) for longest-match-first
_SORTED_SPORT_PREFIXES: list[tuple[str, str]] = sorted(
    _SPORT_SERIES_PREFIXES.items(), key=lambda x: len(x[0]), reverse=True
)

# ── Keyword-Based Sport Detection (fallback) ──
_SPORT_KEYWORDS: dict[str, list[str]] = {
    "NBA": ["nba", "basketball", "lakers", "celtics", "warriors", "bucks",
            "76ers", "knicks", "bulls", "heat", "suns", "nuggets", "clippers",
            "mavericks", "rockets", "hawks", "nets", "cavaliers", "timberwolves",
            "thunder", "grizzlies", "pacers", "pelicans", "magic", "spurs",
            "raptors", "pistons", "hornets", "wizards", "blazers", "jazz"],
    "NFL": ["nfl", "football", "super bowl", "chiefs", "eagles", "49ers",
            "cowboys", "ravens", "bills", "dolphins", "packers", "bengals",
            "lions", "jets", "patriots", "steelers", "broncos", "chargers",
            "raiders", "colts", "jaguars", "texans", "titans", "commanders",
            "giants", "bears", "saints", "falcons", "buccaneers", "panthers",
            "cardinals", "rams", "seahawks", "vikings"],
    "MLB": ["mlb", "baseball", "yankees", "dodgers", "astros", "braves",
            "mets", "phillies", "padres", "cubs", "red sox", "white sox",
            "guardians", "mariners", "orioles", "twins", "rays", "rangers",
            "blue jays", "brewers", "diamondbacks", "reds", "pirates",
            "royals", "tigers", "nationals", "rockies", "athletics", "marlins"],
    "NHL": ["nhl", "hockey", "rangers", "bruins", "oilers", "panthers",
            "avalanche", "maple leafs", "lightning", "hurricanes", "stars",
            "jets", "wild", "penguins", "capitals", "islanders", "flames",
            "canucks", "senators", "flyers", "blue jackets", "predators",
            "kraken", "blackhawks", "devils", "red wings", "sabres", "ducks",
            "sharks", "coyotes", "blues"],
    "NCAA": ["ncaa", "college", "march madness", "cfp", "college football",
             "college basketball", "bowl game"],
    "Soccer": ["soccer", "premier league", "la liga", "bundesliga",
               "champions league", "mls", "world cup", "serie a", "ligue 1",
               "arsenal", "chelsea", "liverpool", "man city", "manchester city",
               "manchester united", "man united", "tottenham",
               "west ham", "everton", "brighton", "newcastle", "aston villa",
               "crystal palace", "wolves", "brentford", "fulham", "bournemouth",
               "nottingham", "burnley", "luton", "sheffield",
               "barcelona", "real madrid", "atletico", "bayern",
               "juventus", "inter milan", "ac milan", "psg", "dortmund",
               "eredivisie", "liga mx", "scottish premiership", "copa del rey",
               "saudi pro league", "a-league"],
    "UFC/MMA": ["ufc", "mma", "fight night", "bellator"],
    "Tennis": ["tennis", "atp", "wta", "grand slam", "wimbledon",
              "us open", "french open", "australian open", "davis cup"],
    "Golf": ["golf", "pga", "masters", "us open golf", "ryder cup",
             "liv golf"],
    "Olympics": ["olympics", "winter games", "freestyle skiing", "snowboarding",
                 "alpine skiing", "cross country skiing", "biathlon", "bobsled",
                 "luge", "skeleton", "figure skating", "speed skating",
                 "short track", "curling", "nordic combined", "ski jumping",
                 "ski mountaineering"],
    "F1": ["formula 1", "f1", "grand prix"],
    "NASCAR": ["nascar", "daytona", "cup series"],
    "Cricket": ["cricket", "ipl", "t20", "test match", "odi"],
    "Boxing": ["boxing", "heavyweight", "middleweight", "welterweight"],
    "Esports": ["cs2", "counter-strike", "league of legends", "valorant",
                "dota 2", "call of duty", "overwatch"],
    "Rugby": ["rugby", "six nations", "all blacks", "nrl"],
    "Chess": ["chess", "fide", "grandmaster"],
}


_NON_SPORT_KEYWORDS: list[str] = [
    "temperature", "weather", "wind speed", "rainfall", "snowfall",
    "humidity", "billboard", "grammy", "oscar", "emmy", "election",
    "stock", "nasdaq", "s&p",
    "crypto", "bitcoin", "ethereum",
    # Economics terms moved to _ECONOMICS_KEYWORDS — no longer block detection
]

# ── Economics Detection ──

# Known Kalshi series tickers for economic indicator markets
_ECONOMICS_SERIES: set[str] = {
    "KXGDP", "KXCPI", "KXFED", "KXUNRATE", "KXPCE", "KXISM",
    "KXRETAIL", "KXHOUSING", "KXPAYROLL", "KXJOBLESS", "KXNFP",
    "KXJOB",
}

# Map series prefix → indicator type
_SERIES_TO_INDICATOR: dict[str, str] = {
    "KXGDP": "GDP",
    "KXCPI": "CPI",
    "KXFED": "Fed Rate",
    "KXUNRATE": "Unemployment",
    "KXPCE": "PCE",
    "KXISM": "ISM",
    "KXRETAIL": "Retail Sales",
    "KXHOUSING": "Housing",
    "KXPAYROLL": "Payrolls",
    "KXNFP": "Payrolls",
    "KXJOBLESS": "Jobless Claims",
    "KXJOB": "Jobs Report",
}

# Keyword-based fallback for economics detection
_ECONOMICS_KEYWORDS: dict[str, list[str]] = {
    "GDP": ["real gdp", "gdp increase", "gdp growth", "gdp decrease"],
    "CPI": ["cpi rise", "cpi increase", "consumer price index", "cpi fall"],
    "Fed Rate": ["federal funds rate", "fed rate", "fomc", "interest rate"],
    "Unemployment": ["unemployment rate", "unemployment rise"],
    "PCE": ["pce inflation", "pce price", "personal consumption"],
    "Payrolls": ["nonfarm payroll", "nonfarm payrolls", "jobs report", "jobs added"],
    "Jobless Claims": ["jobless claims", "initial claims", "weekly claims"],
    "Retail Sales": ["retail sales"],
    "Housing": ["housing starts", "new home sales", "existing home sales"],
    "ISM": ["ism manufacturing", "ism services", "purchasing managers"],
}


def _detect_economics(raw: dict) -> str | None:
    """Detect if a Kalshi market is an economics/macro indicator market.

    Returns the indicator type (e.g. "GDP", "CPI") or None.

    Note: Kalshi removed ``series_ticker`` from market objects (Feb 2026).
    We extract the series prefix from ``event_ticker`` as a fallback.
    """
    # 1. Check series/event ticker (most reliable)
    series_ticker = (
        raw.get("series_ticker")
        or raw.get("event_ticker", "").split("-")[0]
        or ""
    ).upper()
    for prefix, indicator in _SERIES_TO_INDICATOR.items():
        if series_ticker.startswith(prefix):
            return indicator

    # 2. Keyword fallback in title/subtitle text
    text = " ".join([
        raw.get("title", ""),
        raw.get("subtitle", ""),
        raw.get("yes_sub_title", ""),
    ]).lower()

    for indicator, keywords in _ECONOMICS_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return indicator

    return None


def _detect_sport(raw: dict) -> str | None:
    """Detect the sport type from Kalshi market metadata.

    Detection order (most reliable first):
    1. Series/event ticker prefix (e.g. KXWTAMATCH → Tennis)
    2. Keyword matching in title/subtitle/event_ticker
    3. "X vs Y" pattern fallback

    Note: Kalshi removed ``series_ticker`` from market objects (Feb 2026).
    We now extract the series prefix from ``event_ticker`` as a fallback
    (e.g. ``KXNBAGAME-26FEB19DETNYK`` → prefix ``KXNBAGAME``).
    """
    # 1. Series/event ticker prefix — most reliable
    series_ticker = (
        raw.get("series_ticker")
        or raw.get("event_ticker", "").split("-")[0]
        or ""
    ).upper()
    if series_ticker:
        for prefix, sport in _SORTED_SPORT_PREFIXES:
            if series_ticker.startswith(prefix):
                return sport

    # 2. Keyword fallback
    text = " ".join([
        raw.get("title", ""),
        raw.get("subtitle", ""),
        raw.get("yes_sub_title", ""),
        raw.get("event_ticker", ""),
    ]).lower()

    # Reject obvious non-sport markets before keyword matching
    if any(ns in text for ns in _NON_SPORT_KEYWORDS):
        return None

    for sport, keywords in _SPORT_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return sport

    # 3. Fallback: "X vs Y" pattern is almost always sports
    if " vs " in text or " vs. " in text:
        return "Unknown Sport"

    return None


# ── Game Date Extraction ──

_MONTH_MAP: dict[str, int] = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

_GAME_DATE_RE = re.compile(
    r"(\d{2})(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(\d{2})"
)


def extract_game_date(event_ticker: str) -> str | None:
    """Extract the actual game/event date from a Kalshi event ticker.

    Kalshi embeds the game date in event tickers as YYMMMDD:
      - KXNBAGAME-26FEB19DETNYK → 2026-02-19
      - KXATPMATCH-26FEB17KOVSVA → 2026-02-17
      - KXEPLGAME-26MAR01CHELIV → 2026-03-01

    Returns:
        ISO format datetime string (UTC midnight) or None.
    """
    match = _GAME_DATE_RE.search(event_ticker.upper())
    if not match:
        return None
    year = 2000 + int(match.group(1))
    month = _MONTH_MAP[match.group(2)]
    day = int(match.group(3))
    try:
        dt = datetime(year, month, day, tzinfo=timezone.utc)
        return dt.isoformat()
    except ValueError:
        return None


def _is_parlay(raw: dict) -> bool:
    """Detect parlay/combo markets by their garbled title pattern.

    Parlay titles look like: 'yes New York,yes Los Angeles C,yes TCU...'
    Also catches 2-part combos like 'yes Over 243.5,yes UNLV'.
    Any title starting with 'yes ' or 'no ' is a combo outcome, not
    a standalone market question.
    """
    title = raw.get("title", "")
    lower = title.lower().strip()

    # Titles starting with "yes " or "no " are combo outcomes
    if lower.startswith(("yes ", "no ")):
        return True

    # Multi-part comma-separated with yes/no prefixes
    parts = [p.strip() for p in title.split(",")]
    if len(parts) >= 2:
        yes_no_parts = sum(
            1 for p in parts if p.lower().startswith(("yes ", "no "))
        )
        if yes_no_parts >= 2:
            return True

    return False


def _best_price_cents(raw: dict) -> int:
    """Pick the best available price (in cents) from a Kalshi market dict.

    Kalshi returns 0 for all price fields on thin/fresh markets with no
    order-book activity.  Use a fallback chain so we get a real price
    whenever one exists:

        last_price  →  bid/ask midpoint  →  yes_ask  →  yes_bid  →  0

    Returning 0 signals "no valid price" — the scanner should skip.
    """
    last = raw.get("last_price", 0) or 0
    if last > 0:
        return int(last)

    bid = raw.get("yes_bid", 0) or 0
    ask = raw.get("yes_ask", 0) or 0
    if bid > 0 and ask > 0:
        return int((bid + ask) / 2)
    if ask > 0:
        return int(ask)
    if bid > 0:
        return int(bid)

    return 0


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
            resp = await request_with_retry(
                client, "POST",
                f"{self.base_url}/login",
                json={
                    "email": settings.kalshi_email,
                    "password": settings.kalshi_password,
                },
            )
            data: dict = resp.json()

        self._token = data.get("token", "")
        self._token_expires_at = time.time() + 25 * 60

        logger.info("Kalshi: authenticated successfully (legacy)")

    # ── Market Data ──

    async def fetch_markets(
        self,
        limit: int = 100,
        min_volume: float = 10000.0,
        categories: set[str] | None = None,
        min_close_ts: int | None = None,
        max_close_ts: int | None = None,
    ) -> list[dict]:
        """Fetch active markets from Kalshi.

        Uses cursor-based pagination. Markets are filtered by status=open
        and post-filtered by minimum volume, category, and parlay detection.

        Args:
            limit: Maximum total number of markets to return.
            min_volume: Minimum volume filter.
            categories: Allowed category set (default: ALLOWED_CATEGORIES).
            min_close_ts: Only return markets closing AFTER this Unix ts.
            max_close_ts: Only return markets closing BEFORE this Unix ts.

        Returns:
            List of normalized market dicts.
        """
        if categories is None:
            categories = ALLOWED_CATEGORIES
        await self._ensure_auth()

        markets: list[dict] = []
        cursor: str | None = None
        path = "/trade-api/v2/markets"
        max_pages = 50  # Cap pagination to avoid exhausting all Kalshi markets
        page_count = 0
        parlay_skipped = 0

        async with httpx.AsyncClient(timeout=30.0) as client:
            while len(markets) < limit and page_count < max_pages:
                page_count += 1
                params: dict = {
                    "status": "open",
                    "limit": 1000,  # Fetch max per page; filter client-side
                }
                if cursor:
                    params["cursor"] = cursor
                if min_close_ts is not None:
                    params["min_close_ts"] = min_close_ts
                if max_close_ts is not None:
                    params["max_close_ts"] = max_close_ts

                logger.debug(
                    "Kalshi: fetching markets page (cursor=%s)", cursor
                )

                await self._ensure_auth()

                headers = self._auth_headers("GET", path)
                url = f"{self.base_url}/markets"

                try:
                    resp = await request_with_retry(
                        client, "GET", url,
                        params=params,
                        headers=headers,
                    )
                except httpx.HTTPStatusError as exc:
                    logger.error(
                        "Kalshi: API returned %d: %s",
                        exc.response.status_code,
                        exc.response.text[:500],
                    )
                    raise
                data: dict = resp.json()

                page: list[dict] = data.get("markets", [])
                if not page:
                    logger.info(
                        "Kalshi: no more pages, stopping pagination"
                    )
                    break

                # Log category and volume stats on first page for debugging
                if page_count == 1 and page:
                    vols = [float(m.get("volume", 0)) for m in page]
                    max_vol = max(vols) if vols else 0
                    nonzero = sum(1 for v in vols if v > 0)
                    cats_seen = {m.get("category", "unknown") for m in page}
                    logger.info(
                        "Kalshi: page 1 has %d markets, max_vol=%.0f, "
                        "nonzero_vol=%d/%d, categories=%s",
                        len(page), max_vol, nonzero, len(page), cats_seen,
                    )

                for raw in page:
                    # Skip parlay/combo markets
                    if _is_parlay(raw):
                        parlay_skipped += 1
                        continue

                    # Category detection: sports first, then economics
                    sport = _detect_sport(raw)
                    econ = _detect_economics(raw) if not sport else None

                    if categories:
                        if sport and "sports" not in categories:
                            continue
                        elif econ and "economics" not in categories:
                            continue
                        elif not sport and not econ:
                            # Fallback to Kalshi's native category
                            cat = (raw.get("category") or "").lower()
                            if cat not in categories:
                                continue

                    volume = float(raw.get("volume", 0))
                    # Skip volume filter for sports and economics
                    # (sports: fresh markets start at $0; economics: CPI
                    # markets often have <$5K volume but are still valuable)
                    if not sport and not econ and volume < min_volume:
                        continue

                    markets.append(self.normalize_market(raw))

                    if len(markets) >= limit:
                        break

                cursor = data.get("cursor")
                if not cursor:
                    break

        logger.info(
            "Kalshi: fetched %d markets (min_volume=%.0f, pages=%d/%d, parlays_skipped=%d)",
            len(markets),
            min_volume,
            page_count,
            max_pages,
            parlay_skipped,
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
                resp = await request_with_retry(
                    client, "GET",
                    f"{self.base_url}/markets/{platform_id}",
                    headers=self._auth_headers("GET", path),
                )
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

                    resp = await request_with_retry(
                        client, "GET",
                        f"{self.base_url}/portfolio/fills",
                        params=params,
                        headers=self._auth_headers("GET", path),
                    )
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
                resp = await request_with_retry(
                    client, "GET",
                    f"{self.base_url}/portfolio/positions",
                    headers=self._auth_headers("GET", path),
                )
                data = resp.json()

            positions = data.get("market_positions", [])
            logger.info("Kalshi: fetched %d positions", len(positions))
            return positions
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Kalshi: failed to fetch positions: %s", exc)
            return []

    async def fetch_orders(
        self,
        status: str | None = None,
        limit: int = 200,
    ) -> list[dict]:
        """Fetch orders from Kalshi portfolio API.

        Args:
            status: Filter by order status ('resting', 'canceled', 'executed').
                    None fetches all orders.
            limit: Max results per page (max 200).

        Returns:
            List of raw order dicts from Kalshi API.
        """
        await self._ensure_auth()
        path = "/trade-api/v2/portfolio/orders"
        orders: list[dict] = []
        cursor: str | None = None

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                while True:
                    params: dict = {"limit": min(limit, 200)}
                    if status:
                        params["status"] = status
                    if cursor:
                        params["cursor"] = cursor

                    resp = await request_with_retry(
                        client, "GET",
                        f"{self.base_url}/portfolio/orders",
                        params=params,
                        headers=self._auth_headers("GET", path),
                    )
                    data = resp.json()

                    page = data.get("orders", [])
                    orders.extend(page)

                    cursor = data.get("cursor")
                    if not cursor or not page:
                        break

            logger.info(
                "Kalshi: fetched %d orders (status=%s)",
                len(orders), status or "all",
            )
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Kalshi: failed to fetch orders: %s", exc)

        return orders

    # ── Order Placement ──

    async def place_order(
        self,
        ticker: str,
        side: str,
        count: int,
        yes_price: int,
    ) -> dict:
        """Place a limit buy order on Kalshi.

        Args:
            ticker: Market ticker (e.g., KXEPLGAME-26MAR01CHELIV-CHE).
            side: ``"yes"`` or ``"no"``.
            count: Number of contracts to buy.
            yes_price: Price in cents (1-99).

        Returns:
            Order response dict from Kalshi API.
        """
        await self._ensure_auth()
        path = "/trade-api/v2/portfolio/orders"
        headers = self._auth_headers("POST", path)
        body = {
            "ticker": ticker,
            "action": "buy",
            "side": side,
            "count": count,
            "type": "limit",
            "yes_price": yes_price,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await request_with_retry(
                client,
                "POST",
                f"{self.base_url}/portfolio/orders",
                json=body,
                headers=headers,
            )

        order = resp.json()
        logger.info(
            "Kalshi: placed order — ticker=%s side=%s count=%d price=%d¢ status=%s",
            ticker,
            side,
            count,
            yes_price,
            order.get("order", {}).get("status", "unknown"),
        )
        return order

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
        # Price: Kalshi uses cents (0-100), convert to decimal.
        # Thin/fresh markets return 0 for all price fields. Use a
        # fallback chain: last_price → bid/ask midpoint → yes_ask → 0.
        price_cents = _best_price_cents(raw)
        price_yes: float = price_cents / 100

        # Close date: prefer close_time, fall back to expiration_time
        close_date: str | None = raw.get("close_time") or raw.get(
            "expiration_time"
        )

        # Title: prefer clean title, fall back to subtitle or event_ticker
        title = raw.get("title", "")
        subtitle = raw.get("yes_sub_title", "") or raw.get("subtitle", "")
        event_ticker = raw.get("event_ticker", "")

        # If title looks garbled (parlay-like), prefer subtitle
        if title and "," in title and len(title.split(",")) >= 3:
            question = subtitle or event_ticker or title
        elif title:
            question = title
        elif subtitle:
            question = subtitle
        else:
            question = event_ticker or "Unknown market"

        sport = _detect_sport(raw)
        econ = _detect_economics(raw) if not sport else None

        # Set category based on detection
        if sport:
            category = "sports"
        elif econ:
            category = "economics"
        else:
            category = raw.get("category", "")

        return {
            "platform": self.platform,
            "platform_id": raw.get("ticker", ""),
            "question": question,
            "description": raw.get("rules_primary", ""),
            "resolution_criteria": raw.get("rules_primary", ""),
            "category": category,
            "close_date": close_date,
            "outcome_label": subtitle or None,
            "price_yes": price_yes,
            "volume": float(raw.get("volume", 0)),
            "liquidity": float(raw.get("open_interest", 0)),
            "event_ticker": event_ticker,
            "sport_type": sport,
            "economic_indicator": econ,
            "game_date": extract_game_date(event_ticker),
        }
