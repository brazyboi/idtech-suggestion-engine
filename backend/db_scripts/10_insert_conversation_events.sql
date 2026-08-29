-- Funnel event log for the chat agent (session_started, recommendation_shown,
-- lead_submitted). Lets the admin dashboard show a resolution-rate metric
-- instead of no conversion visibility at all.
CREATE TABLE IF NOT EXISTS conversation_events (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(255) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversation_events_type ON conversation_events(event_type);
CREATE INDEX IF NOT EXISTS idx_conversation_events_session ON conversation_events(session_id);
