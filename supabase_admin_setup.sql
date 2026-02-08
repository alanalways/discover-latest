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

-- RLS（可依需求調整）
ALTER TABLE public.user_subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.portfolios ENABLE ROW LEVEL SECURITY;
