-- Count reservations, including failed/uncertain attempts, across restarts.
CREATE TABLE model_call_attempts (
    id uuid PRIMARY KEY,
    batch text NOT NULL,
    provider text NOT NULL,
    requested_model text NOT NULL,
    actual_model text,
    status text NOT NULL CHECK (status IN ('reserved', 'success', 'failed')),
    usage jsonb,
    latency_ms double precision,
    error_code text,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX model_attempt_batch ON model_call_attempts(batch);
