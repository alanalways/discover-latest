-- 後台 Admin 所需：RPC get_user_by_email、user_subscriptions、ai_usage / ai_usage_logs
-- 在 Supabase SQL Editor 中執行（需專案權限）

-- 1) RPC：依 Email 查詢 auth.users（需 SECURITY DEFINER）
CREATE OR REPLACE FUNCTION public.get_user_by_email(email TEXT)
RETURNS TABLE (id UUID, email TEXT, created_at TIMESTAMPTZ)
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT id, email::TEXT, created_at
  FROM auth.users
  WHERE auth.users.email = get_user_by_email.email
  LIMIT 1;
$$;

-- 2) 訂閱表（若尚未建立）
CREATE TABLE IF NOT EXISTS public.user_subscriptions (
  user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  tier TEXT NOT NULL DEFAULT 'free',
  expires_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3) AI 用量：若使用「每日一筆 + count」可建 ai_usage
CREATE TABLE IF NOT EXISTS public.ai_usage (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  date DATE NOT NULL DEFAULT CURRENT_DATE,
  count INT NOT NULL DEFAULT 0,
  UNIQUE(user_id, date)
);

-- 若使用「每筆紀錄」則可建 ai_usage_logs，並以 RPC 或 count 查今日次數
-- CREATE TABLE IF NOT EXISTS public.ai_usage_logs (
--   id BIGSERIAL PRIMARY KEY,
--   user_id UUID NOT NULL,
--   action_type TEXT,
--   created_at TIMESTAMPTZ DEFAULT NOW()
-- );

-- increment_ai_usage RPC（與現有程式對齊）
CREATE OR REPLACE FUNCTION public.increment_ai_usage(p_user_id UUID, p_date DATE)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  INSERT INTO public.ai_usage (user_id, date, count)
  VALUES (p_user_id, p_date, 1)
  ON CONFLICT (user_id, date) DO UPDATE SET count = ai_usage.count + 1;
END;
$$;

-- 4) 投資組合 portfolios（user_id, symbol, shares, avg_price）
CREATE TABLE IF NOT EXISTS public.portfolios (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  symbol TEXT NOT NULL,
  shares INT NOT NULL DEFAULT 0,
  avg_price NUMERIC(12,4) NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, symbol)
);

-- 5) 價格提醒 price_alerts
CREATE TABLE IF NOT EXISTS public.price_alerts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  symbol TEXT NOT NULL,
  target_price NUMERIC(12,4) NOT NULL,
  condition TEXT NOT NULL CHECK (condition IN ('gte','lte')),
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  triggered_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS price_alerts_user_idx ON public.price_alerts(user_id);

-- RLS（可依需求調整）
ALTER TABLE public.user_subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.portfolios ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.price_alerts ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_all" ON public.price_alerts TO service_role USING (TRUE) WITH CHECK (TRUE);

-- 6) public.users 表的 RLS 政策（確保 service_role 完整存取）
-- 若 public.users 啟用了 RLS 但沒有 service_role policy，Admin API 會查不到任何使用者
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_all" ON public.users TO service_role USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY "users_select_own" ON public.users FOR SELECT TO authenticated USING (auth.uid() = id);

-- 7) 確保所有啟用 RLS 的表都有 service_role policy
CREATE POLICY "service_role_all" ON public.user_subscriptions TO service_role USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY "service_role_all" ON public.ai_usage TO service_role USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY "service_role_all" ON public.portfolios TO service_role USING (TRUE) WITH CHECK (TRUE);

-- 8) 資料庫大小查詢 RPC（用於容量偵測）
CREATE OR REPLACE FUNCTION get_db_size_mb()
RETURNS TABLE(size_mb NUMERIC) AS $$
BEGIN
    RETURN QUERY SELECT ROUND(pg_database_size(current_database()) / 1024.0 / 1024.0, 2) AS size_mb;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;


-- ================================================================
-- Phase 3-6 新增表
-- ================================================================

-- 9) user_profiles — 投資人格檔案（P01）
CREATE TABLE IF NOT EXISTS public.user_profiles (
  user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  risk_tolerance TEXT DEFAULT 'moderate' CHECK (risk_tolerance IN ('conservative','moderate','aggressive')),
  investment_horizon TEXT DEFAULT 'medium' CHECK (investment_horizon IN ('short','medium','long')),
  experience_level TEXT DEFAULT 'beginner' CHECK (experience_level IN ('beginner','intermediate','expert')),
  goal TEXT,
  preferred_tone TEXT DEFAULT 'beginner' CHECK (preferred_tone IN ('beginner','professional')),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_all" ON public.user_profiles TO service_role USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY "profiles_select_own" ON public.user_profiles FOR SELECT TO authenticated USING (auth.uid() = user_id);
CREATE POLICY "profiles_update_own" ON public.user_profiles FOR UPDATE TO authenticated USING (auth.uid() = user_id);
CREATE POLICY "profiles_insert_own" ON public.user_profiles FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);

-- 10) strategy_templates — 自訂策略模板（P02/P03）
CREATE TABLE IF NOT EXISTS public.strategy_templates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  entry_rules JSONB DEFAULT '[]'::jsonb,
  exit_rules JSONB DEFAULT '[]'::jsonb,
  stop_loss_pct NUMERIC(6,2),
  take_profit_pct NUMERIC(6,2),
  max_position_pct NUMERIC(6,2) DEFAULT 25,
  tags JSONB DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS strategy_templates_user_idx ON public.strategy_templates(user_id);
ALTER TABLE public.strategy_templates ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_all" ON public.strategy_templates TO service_role USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY "templates_select_own" ON public.strategy_templates FOR SELECT TO authenticated USING (auth.uid() = user_id);
CREATE POLICY "templates_modify_own" ON public.strategy_templates FOR ALL TO authenticated USING (auth.uid() = user_id);

-- 11) trade_journal — 交易日誌（P13）
CREATE TABLE IF NOT EXISTS public.trade_journal (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  symbol TEXT NOT NULL,
  action TEXT NOT NULL CHECK (action IN ('buy','sell','short','cover')),
  price NUMERIC(12,4) NOT NULL,
  quantity NUMERIC(12,4) NOT NULL,
  note TEXT,
  strategy_template_id UUID REFERENCES public.strategy_templates(id) ON DELETE SET NULL,
  emotion TEXT CHECK (emotion IN ('calm','fomo','fear','greedy') OR emotion IS NULL),
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS trade_journal_user_idx ON public.trade_journal(user_id);
ALTER TABLE public.trade_journal ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_all" ON public.trade_journal TO service_role USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY "journal_select_own" ON public.trade_journal FOR SELECT TO authenticated USING (auth.uid() = user_id);
CREATE POLICY "journal_insert_own" ON public.trade_journal FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);

-- 12) signal_history — 訊號歷史（C18）
CREATE TABLE IF NOT EXISTS public.signal_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  symbol TEXT NOT NULL,
  signal_type TEXT NOT NULL,
  direction TEXT NOT NULL,
  confidence NUMERIC(6,2),
  entry_price NUMERIC(12,4),
  target_price NUMERIC(12,4),
  stop_price NUMERIC(12,4),
  horizon_days INT DEFAULT 20,
  source TEXT DEFAULT 'ai',
  features JSONB DEFAULT '{}'::jsonb,
  evaluated BOOLEAN DEFAULT FALSE,
  outcome TEXT,
  outcome_price NUMERIC(12,4),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  evaluated_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS signal_history_symbol_idx ON public.signal_history(symbol);
CREATE INDEX IF NOT EXISTS signal_history_created_idx ON public.signal_history(created_at);
ALTER TABLE public.signal_history ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_all" ON public.signal_history TO service_role USING (TRUE) WITH CHECK (TRUE);

-- 13) analysis_cache — 分析快取 L2（B06）
CREATE TABLE IF NOT EXISTS public.analysis_cache (
  id BIGSERIAL PRIMARY KEY,
  cache_key TEXT NOT NULL UNIQUE,
  symbol TEXT NOT NULL,
  tier TEXT DEFAULT 'free',
  analysis_text TEXT,
  summary_json JSONB,
  quality_pass BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '1 hour')
);
CREATE INDEX IF NOT EXISTS analysis_cache_key_idx ON public.analysis_cache(cache_key);
CREATE INDEX IF NOT EXISTS analysis_cache_expires_idx ON public.analysis_cache(expires_at);
ALTER TABLE public.analysis_cache ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_all" ON public.analysis_cache TO service_role USING (TRUE) WITH CHECK (TRUE);
