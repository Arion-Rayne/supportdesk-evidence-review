CREATE TABLE documents (
    id uuid PRIMARY KEY,
    source_id text NOT NULL,
    sha256 text NOT NULL,
    metadata jsonb NOT NULL,
    is_current boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_id, sha256)
);
CREATE UNIQUE INDEX current_source ON documents(source_id) WHERE is_current;

CREATE TABLE segments (
    id uuid PRIMARY KEY,
    document_id uuid NOT NULL REFERENCES documents(id),
    origin_document_id uuid NOT NULL REFERENCES documents(id),
    segment_id text NOT NULL,
    payload jsonb NOT NULL,
    UNIQUE (document_id, origin_document_id, segment_id)
);

CREATE TABLE tickets (
    id uuid PRIMARY KEY,
    question text NOT NULL CHECK (length(trim(question)) > 0 AND length(question) <= 2000),
    synthetic boolean NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE runs (
    id uuid PRIMARY KEY,
    ticket_id uuid NOT NULL REFERENCES tickets(id),
    method text NOT NULL,
    result jsonb NOT NULL,
    latency_ms double precision NOT NULL,
    model_name text,
    usage jsonb,
    status text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE reviews (
    id uuid PRIMARY KEY,
    ticket_id uuid NOT NULL REFERENCES tickets(id),
    run_id uuid NOT NULL REFERENCES runs(id),
    draft text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
