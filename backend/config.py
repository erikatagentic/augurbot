from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Anthropic
    anthropic_api_key: str = ""

    # Supabase
    supabase_url: str = ""
    supabase_service_key: str = ""

    # Market APIs
    polymarket_api_url: str = "https://clob.polymarket.com"
    polymarket_gamma_url: str = "https://gamma-api.polymarket.com"
    kalshi_api_url: str = "https://api.elections.kalshi.com/trade-api/v2"
    kalshi_email: str = ""
    kalshi_password: str = ""
    kalshi_api_key: str = ""
    kalshi_private_key_path: str = ""
    kalshi_private_key: str = ""  # Inline PEM content (for Railway/cloud deploys)
    manifold_api_url: str = "https://api.manifold.markets"

    # Pipeline thresholds
    min_edge_threshold: float = 0.03
    min_volume: float = 50000.0
    kelly_fraction: float = 0.33
    max_single_bet_fraction: float = 0.05
    re_estimate_trigger: float = 0.05
    scan_interval_hours: int = 24
    bankroll: float = 10000.0

    # Cost optimization
    markets_per_platform: int = 100
    web_search_max_uses: int = 5
    price_check_enabled: bool = False
    price_check_interval_hours: int = 6
    estimate_cache_hours: float = 20.0

    # Resolution detection
    resolution_check_enabled: bool = True
    resolution_check_interval_hours: int = 1

    # Trade sync
    trade_sync_enabled: bool = False
    trade_sync_interval_hours: int = 4
    polymarket_wallet_address: str = ""
    polymarket_data_api_url: str = "https://data-api.polymarket.com"

    # Auto-trade
    auto_trade_enabled: bool = False
    auto_trade_min_ev: float = 0.05
    max_exposure_fraction: float = 0.25       # Max 25% of bankroll in open positions
    max_event_exposure_fraction: float = 0.10  # Max 10% per event (one game)

    # Close-date window
    max_close_hours: int = 48

    # Scan schedule (hours in Pacific Time)
    scan_times: list[int] = [8]

    # Notifications
    notifications_enabled: bool = False
    notification_email: str = ""
    notification_slack_webhook: str = ""
    notification_min_ev: float = 0.08
    resend_api_key: str = ""
    daily_digest_enabled: bool = True

    # Platform fees (Kalshi uses dynamic formula in calculator.py, not this flat value)
    polymarket_fee: float = 0.02
    kalshi_fee: float = 0.07  # Legacy — calculator.py uses 0.07 × price × (1-price) instead
    manifold_fee: float = 0.0

    # Model selection
    default_model: str = "claude-sonnet-4-5-20250929"
    high_value_model: str = "claude-opus-4-6"
    high_value_volume_threshold: float = 100000.0
    use_premium_model: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
