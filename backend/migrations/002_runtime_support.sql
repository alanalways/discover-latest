-- Runtime support tables / RPCs for membership, usage, alerts, and admin features

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    user_id TEXT UNIQUE,
    email TEXT,
    name TEXT,
    tier TEXT NOT NULL DEFAULT 'free',
    role TEXT NOT NULL DEFAULT 'user',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_subscriptions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL UNIQUE,
    tier TEXT NOT NULL DEFAULT 'free',
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ai_usage (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL,
    date DATE NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, date)
);

CREATE TABLE IF NOT EXISTS report_ratings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    report_id UUID NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    rating INTEGER NOT NULL,
    comment TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(report_id, user_id)
);

CREATE TABLE IF NOT EXISTS portfolios (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    shares INTEGER NOT NULL DEFAULT 0,
    avg_price NUMERIC NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, symbol)
);

CREATE TABLE IF NOT EXISTS alerts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    target_price NUMERIC NOT NULL,
    condition TEXT NOT NULL,
    triggered BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pending_upgrades (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL,
    user_email TEXT,
    user_name TEXT,
    plan TEXT NOT NULL,
    billing_cycle TEXT NOT NULL DEFAULT 'monthly',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE OR REPLACE VIEW decrypted_secrets AS
SELECT
    v.name,
    v.secret AS decrypted_secret
FROM (
    SELECT NULL::TEXT AS name, NULL::TEXT AS secret
) v
WHERE FALSE;

CREATE OR REPLACE FUNCTION increment_ai_usage(p_user_id TEXT, p_date DATE)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO ai_usage (user_id, date, count)
    VALUES (p_user_id, p_date, 1)
    ON CONFLICT (user_id, date)
    DO UPDATE SET
        count = ai_usage.count + 1,
        updated_at = NOW();
END;
$$;

CREATE OR REPLACE FUNCTION get_db_size_mb()
RETURNS NUMERIC
LANGUAGE sql
AS $$
    SELECT ROUND(pg_database_size(current_database()) / 1024.0 / 1024.0, 2);
$$;

CREATE OR REPLACE FUNCTION pg_database_size_mb()
RETURNS NUMERIC
LANGUAGE sql
AS $$
    SELECT ROUND(pg_database_size(current_database()) / 1024.0 / 1024.0, 2);
$$;

CREATE INDEX IF NOT EXISTS idx_users_tier ON users(tier);
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_tier ON user_subscriptions(tier);
CREATE INDEX IF NOT EXISTS idx_ai_usage_user_date ON ai_usage(user_id, date DESC);
CREATE INDEX IF NOT EXISTS idx_portfolios_user ON portfolios(user_id);
CREATE INDEX IF NOT EXISTS idx_alerts_user ON alerts(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pending_upgrades_status ON pending_upgrades(status, created_at DESC);
