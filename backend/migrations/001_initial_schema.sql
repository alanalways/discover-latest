-- DiscoverLatest 2.0 — 初始資料庫 Schema
-- 版本：001
-- 在 Supabase SQL Editor 執行此檔案
-- 警告：禁止修改 predictions / outcomes 表的欄位結構

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ─────────────────────────────────────────────────────────
-- 1. 使用者偏好
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_prefs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL UNIQUE,
    risk_tolerance TEXT DEFAULT 'moderate',
    preferred_timeframe TEXT DEFAULT 'swing',
    watchlist JSONB DEFAULT '[]',
    notification_line BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────
-- 2. 報告主表
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,
    report_type TEXT NOT NULL,
    tier TEXT NOT NULL,
    technical_output JSONB,
    fundamental_output JSONB,
    chips_output JSONB,
    event_output JSONB,
    macro_output JSONB,
    sentiment_output JSONB,
    arbitration_log JSONB,
    final_report TEXT NOT NULL,
    rating TEXT,
    target_price_low NUMERIC,
    target_price_high NUMERIC,
    confidence_score NUMERIC,
    total_gemini_calls INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    generation_time_ms INTEGER,
    triggered_by TEXT DEFAULT 'user',
    user_id TEXT,
    is_archived BOOLEAN DEFAULT FALSE,
    archived_at TIMESTAMPTZ,
    archive_path TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_reports_symbol ON reports(symbol);
CREATE INDEX idx_reports_created ON reports(created_at DESC);
CREATE INDEX idx_reports_not_archived ON reports(is_archived) WHERE is_archived = FALSE;

-- ─────────────────────────────────────────────────────────
-- 3. 預測記錄（演進引擎核心，禁止改欄位結構）
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS predictions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    report_id UUID NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,
    predicted_direction TEXT NOT NULL,
    predicted_target_low NUMERIC,
    predicted_target_high NUMERIC,
    timeframe TEXT NOT NULL,
    prediction_date DATE NOT NULL DEFAULT CURRENT_DATE,
    verify_date DATE NOT NULL,
    is_verified BOOLEAN DEFAULT FALSE,
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_predictions_to_verify ON predictions(verify_date, is_verified)
    WHERE is_verified = FALSE;

-- ─────────────────────────────────────────────────────────
-- 4. 實際結果（準確率回測官填入）
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS outcomes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    prediction_id UUID NOT NULL REFERENCES predictions(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    actual_price_at_prediction NUMERIC NOT NULL,
    actual_price_at_verify NUMERIC NOT NULL,
    actual_direction TEXT NOT NULL,
    actual_change_pct NUMERIC,
    direction_correct BOOLEAN NOT NULL,
    target_hit BOOLEAN,
    score NUMERIC,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────
-- 5. Prompt 版本控制
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS prompt_versions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_name TEXT NOT NULL,
    version INTEGER NOT NULL,
    prompt_content TEXT NOT NULL,
    model_assigned TEXT NOT NULL,
    accuracy_score NUMERIC,
    usage_count INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT FALSE,
    evolved_from_version INTEGER,
    evolution_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(agent_name, version)
);

-- ─────────────────────────────────────────────────────────
-- 6. 工作佇列
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS job_queue (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_type TEXT NOT NULL,
    priority INTEGER DEFAULT 5,
    status TEXT DEFAULT 'pending',
    payload JSONB NOT NULL,
    result JSONB,
    error_message TEXT,
    assigned_agent TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    scheduled_for TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_job_queue_runnable ON job_queue(status, priority, scheduled_for)
    WHERE status = 'pending';

-- ─────────────────────────────────────────────────────────
-- 7. Agent 行為日誌
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agent_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_name TEXT NOT NULL,
    job_id UUID,
    report_id UUID,
    action TEXT NOT NULL,
    gemini_model_used TEXT,
    tokens_used INTEGER DEFAULT 0,
    duration_ms INTEGER,
    status TEXT NOT NULL,
    error_detail TEXT,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_agent_logs_recent ON agent_logs(created_at DESC);

-- ─────────────────────────────────────────────────────────
-- 8. 封存索引
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS archive_index (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_table TEXT NOT NULL,
    source_ids UUID[] NOT NULL,
    archive_path TEXT NOT NULL,
    archive_tier TEXT NOT NULL,
    file_size_bytes BIGINT,
    checksum TEXT,
    record_count INTEGER,
    date_range_start DATE,
    date_range_end DATE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────
-- 9. 公開準確率視圖（無需登入可查）
-- ─────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW public_accuracy_stats AS
SELECT
    p.symbol,
    p.market,
    p.timeframe,
    COUNT(*) AS total_predictions,
    SUM(CASE WHEN o.direction_correct THEN 1 ELSE 0 END) AS correct_count,
    ROUND(AVG(CASE WHEN o.direction_correct THEN 1.0 ELSE 0.0 END) * 100, 1) AS accuracy_pct,
    MIN(p.prediction_date) AS tracking_since
FROM predictions p
JOIN outcomes o ON p.id = o.prediction_id
WHERE p.is_verified = TRUE
GROUP BY p.symbol, p.market, p.timeframe;
