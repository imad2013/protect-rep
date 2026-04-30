-- Initialize Data Protection Database

CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    source_ip INET,
    user_id VARCHAR(255),
    timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    processed BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_user ON events(user_id);

-- Create a user for the application
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'dataprotection') THEN
        CREATE ROLE dataprotection WITH LOGIN PASSWORD 'dataprotection';
    END IF;
END
$$;

GRANT ALL PRIVILEGES ON TABLE events TO dataprotection;
GRANT USAGE, SELECT ON SEQUENCE events_id_seq TO dataprotection;
