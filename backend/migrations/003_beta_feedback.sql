-- 免費 Beta 回饋表：蒐集 UX / bug / idea / content / speed 回饋

CREATE TABLE IF NOT EXISTS beta_feedback (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    category TEXT NOT NULL DEFAULT 'general',
    message TEXT NOT NULL,
    page TEXT,
    contact_email TEXT,
    rating INTEGER,
    would_recommend BOOLEAN,
    user_id TEXT,
    user_email TEXT,
    user_name TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_beta_feedback_created_at ON beta_feedback(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_beta_feedback_category ON beta_feedback(category);
