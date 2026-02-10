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
    kalshi_api_url: str = "https://trading-api.kalshi.com/trade-api/v2"
    kalshi_email: str = ""
    kalshi_password: str = ""
    manifold_api_url: str = "https://api.manifold.markets"

    # Pipeline thresholds
    min_edge_threshold: float = 0.05
    min_volume: float = 10000.0
    kelly_fraction: float = 0.33
    max_single_bet_fraction: float = 0.05
    re_estimate_trigger: float = 0.05
    scan_interval_hours: int = 4
    bankroll: float = 10000.0

    # Platform fees
    polymarket_fee: float = 0.02
    kalshi_fee: float = 0.07
    manifold_fee: float = 0.0

    # Model selection
    default_model: str = "claude-sonnet-4-5-20250929"
    high_value_model: str = "claude-opus-4-6"
    high_value_volume_threshold: float = 100000.0

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
