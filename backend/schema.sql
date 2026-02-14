-- AugurBot Database Schema
-- Run this in the Supabase SQL Editor (https://supabase.com/dashboard/project/vpcgzforjhcoxottoxxv/sql)

-- ══════════════════════════════════════════════
-- 1. TABLES
-- ══════════════════════════════════════════════

-- Markets tracked across all platforms
CREATE TABLE IF NOT EXISTS markets (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  platform        TEXT NOT NULL CHECK (platform IN ('polymarket', 'kalshi', 'manifold', 'metaculus')),
  platform_id     TEXT NOT NULL,
  question        TEXT NOT NULL,
  description     TEXT,
  resolution_criteria TEXT,
  category        TEXT,
  close_date      TIMESTAMPTZ,
  outcome_label   TEXT,
  status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'closed', 'resolved')),
  outcome         BOOLEAN,
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(platform, platform_id)
);

-- Price snapshots over time
CREATE TABLE IF NOT EXISTS market_snapshots (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  market_id       UUID NOT NULL REFERENCES markets(id) ON DELETE CASCADE,
  price_yes       NUMERIC(5,4) NOT NULL,
  price_no        NUMERIC(5,4),
  volume          NUMERIC(15,2),
  liquidity       NUMERIC(15,2),
  captured_at     TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_snapshots_market_time ON market_snapshots(market_id, captured_at DESC);

-- AI probability estimates
CREATE TABLE IF NOT EXISTS ai_estimates (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  market_id       UUID NOT NULL REFERENCES markets(id) ON DELETE CASCADE,
  probability     NUMERIC(5,4) NOT NULL,
  confidence      TEXT NOT NULL CHECK (confidence IN ('high', 'medium', 'low')),
  reasoning       TEXT NOT NULL,
  key_evidence    JSONB,
  key_uncertainties JSONB,
  model_used      TEXT NOT NULL,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_estimates_market_time ON ai_estimates(market_id, created_at DESC);

-- Bet recommendations (only when edge > threshold)
CREATE TABLE IF NOT EXISTS recommendations (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  market_id       UUID NOT NULL REFERENCES markets(id) ON DELETE CASCADE,
  estimate_id     UUID NOT NULL REFERENCES ai_estimates(id),
  snapshot_id     UUID NOT NULL REFERENCES market_snapshots(id),
  direction       TEXT NOT NULL CHECK (direction IN ('yes', 'no')),
  market_price    NUMERIC(5,4) NOT NULL,
  ai_probability  NUMERIC(5,4) NOT NULL,
  edge            NUMERIC(5,4) NOT NULL,
  ev              NUMERIC(5,4) NOT NULL,
  kelly_fraction  NUMERIC(5,4) NOT NULL,
  status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'expired', 'resolved')),
  created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_recommendations_active ON recommendations(status, ev DESC) WHERE status = 'active';

-- Performance tracking (populated when markets resolve)
CREATE TABLE IF NOT EXISTS performance_log (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  market_id       UUID NOT NULL REFERENCES markets(id),
  recommendation_id UUID REFERENCES recommendations(id),
  ai_probability  NUMERIC(5,4) NOT NULL,
  market_price    NUMERIC(5,4) NOT NULL,
  actual_outcome  BOOLEAN NOT NULL,
  pnl             NUMERIC(10,4),
  simulated_pnl   NUMERIC(10,4),
  brier_score     NUMERIC(5,4) NOT NULL,
  resolved_at     TIMESTAMPTZ DEFAULT NOW()
);

-- User trade tracking
CREATE TABLE IF NOT EXISTS trades (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  market_id         UUID NOT NULL REFERENCES markets(id) ON DELETE CASCADE,
  recommendation_id UUID REFERENCES recommendations(id),
  platform          TEXT NOT NULL CHECK (platform IN ('polymarket', 'kalshi', 'manifold')),
  direction         TEXT NOT NULL CHECK (direction IN ('yes', 'no')),
  entry_price       NUMERIC(5,4) NOT NULL,
  amount            NUMERIC(15,2) NOT NULL,
  shares            NUMERIC(15,4),
  status            TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed', 'cancelled')),
  exit_price        NUMERIC(5,4),
  pnl               NUMERIC(10,4),
  fees_paid         NUMERIC(10,4) DEFAULT 0,
  notes             TEXT,
  source            TEXT NOT NULL DEFAULT 'manual' CHECK (source IN ('manual', 'api_sync')),
  platform_trade_id TEXT,
  created_at        TIMESTAMPTZ DEFAULT NOW(),
  closed_at         TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_trades_market ON trades(market_id);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status) WHERE status = 'open';
CREATE INDEX IF NOT EXISTS idx_trades_created ON trades(created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_trades_platform_trade_id
  ON trades(platform, platform_trade_id)
  WHERE platform_trade_id IS NOT NULL;

-- Trade sync log (tracks automatic trade imports from platforms)
CREATE TABLE IF NOT EXISTS trade_sync_log (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  platform      TEXT NOT NULL CHECK (platform IN ('polymarket', 'kalshi')),
  status        TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
  trades_found  INT DEFAULT 0,
  trades_created INT DEFAULT 0,
  trades_updated INT DEFAULT 0,
  trades_skipped INT DEFAULT 0,
  error_message TEXT,
  started_at    TIMESTAMPTZ DEFAULT NOW(),
  completed_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_trade_sync_log_platform
  ON trade_sync_log(platform, completed_at DESC);

-- API cost tracking
CREATE TABLE IF NOT EXISTS cost_log (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  scan_id         TEXT,
  market_id       UUID REFERENCES markets(id),
  model_used      TEXT NOT NULL,
  input_tokens    INT NOT NULL DEFAULT 0,
  output_tokens   INT NOT NULL DEFAULT 0,
  estimated_cost  NUMERIC(10,6) NOT NULL DEFAULT 0,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cost_log_created ON cost_log(created_at DESC);

-- User configuration
CREATE TABLE IF NOT EXISTS config (
  key             TEXT PRIMARY KEY,
  value           JSONB NOT NULL,
  updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ══════════════════════════════════════════════
-- 2. RPC FUNCTIONS
-- ══════════════════════════════════════════════

-- Find markets that need AI research (no estimate or estimate is stale)
CREATE OR REPLACE FUNCTION get_markets_needing_research(hours_threshold INT DEFAULT 6)
RETURNS TABLE (
  id UUID,
  platform TEXT,
  platform_id TEXT,
  question TEXT,
  description TEXT,
  resolution_criteria TEXT,
  category TEXT,
  close_date TIMESTAMPTZ
) AS $$
BEGIN
  RETURN QUERY
  SELECT
    m.id,
    m.platform,
    m.platform_id,
    m.question,
    m.description,
    m.resolution_criteria,
    m.category,
    m.close_date
  FROM markets m
  LEFT JOIN LATERAL (
    SELECT ae.created_at
    FROM ai_estimates ae
    WHERE ae.market_id = m.id
    ORDER BY ae.created_at DESC
    LIMIT 1
  ) latest_estimate ON TRUE
  WHERE m.status = 'active'
    AND (
      latest_estimate.created_at IS NULL
      OR latest_estimate.created_at < NOW() - (hours_threshold || ' hours')::INTERVAL
    );
END;
$$ LANGUAGE plpgsql;

-- Get calibration data (bucketed predicted vs actual)
CREATE OR REPLACE FUNCTION get_calibration_data()
RETURNS TABLE (
  bucket TEXT,
  bucket_min NUMERIC,
  bucket_max NUMERIC,
  avg_predicted NUMERIC,
  avg_actual NUMERIC,
  count BIGINT
) AS $$
BEGIN
  RETURN QUERY
  WITH buckets AS (
    SELECT
      pl.ai_probability,
      CASE WHEN pl.actual_outcome THEN 1.0 ELSE 0.0 END AS outcome_numeric,
      CASE
        WHEN pl.ai_probability < 0.1 THEN '0-10%'
        WHEN pl.ai_probability < 0.2 THEN '10-20%'
        WHEN pl.ai_probability < 0.3 THEN '20-30%'
        WHEN pl.ai_probability < 0.4 THEN '30-40%'
        WHEN pl.ai_probability < 0.5 THEN '40-50%'
        WHEN pl.ai_probability < 0.6 THEN '50-60%'
        WHEN pl.ai_probability < 0.7 THEN '60-70%'
        WHEN pl.ai_probability < 0.8 THEN '70-80%'
        WHEN pl.ai_probability < 0.9 THEN '80-90%'
        ELSE '90-100%'
      END AS bucket_label,
      CASE
        WHEN pl.ai_probability < 0.1 THEN 0.0
        WHEN pl.ai_probability < 0.2 THEN 0.1
        WHEN pl.ai_probability < 0.3 THEN 0.2
        WHEN pl.ai_probability < 0.4 THEN 0.3
        WHEN pl.ai_probability < 0.5 THEN 0.4
        WHEN pl.ai_probability < 0.6 THEN 0.5
        WHEN pl.ai_probability < 0.7 THEN 0.6
        WHEN pl.ai_probability < 0.8 THEN 0.7
        WHEN pl.ai_probability < 0.9 THEN 0.8
        ELSE 0.9
      END AS bmin,
      CASE
        WHEN pl.ai_probability < 0.1 THEN 0.1
        WHEN pl.ai_probability < 0.2 THEN 0.2
        WHEN pl.ai_probability < 0.3 THEN 0.3
        WHEN pl.ai_probability < 0.4 THEN 0.4
        WHEN pl.ai_probability < 0.5 THEN 0.5
        WHEN pl.ai_probability < 0.6 THEN 0.6
        WHEN pl.ai_probability < 0.7 THEN 0.7
        WHEN pl.ai_probability < 0.8 THEN 0.8
        WHEN pl.ai_probability < 0.9 THEN 0.9
        ELSE 1.0
      END AS bmax
    FROM performance_log pl
  )
  SELECT
    b.bucket_label AS bucket,
    MIN(b.bmin) AS bucket_min,
    MAX(b.bmax) AS bucket_max,
    ROUND(AVG(b.ai_probability), 4) AS avg_predicted,
    ROUND(AVG(b.outcome_numeric), 4) AS avg_actual,
    COUNT(*) AS count
  FROM buckets b
  GROUP BY b.bucket_label, b.bmin
  ORDER BY b.bmin;
END;
$$ LANGUAGE plpgsql;

-- ══════════════════════════════════════════════
-- 3. DEFAULT CONFIG
-- ══════════════════════════════════════════════

INSERT INTO config (key, value) VALUES
  ('kelly_fraction', '0.33'),
  ('min_edge', '0.05'),
  ('max_single_bet', '0.05'),
  ('bankroll', '1000'),
  ('scan_interval_hours', '4'),
  ('min_volume', '10000'),
  ('reestimate_trigger', '0.05'),
  ('platforms_enabled', '{"polymarket": true, "kalshi": false, "manifold": true}')
ON CONFLICT (key) DO NOTHING;
