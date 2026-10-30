CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS segment_vectors (
    segment_id text NOT NULL,
    model text NOT NULL,
    dimensions integer NOT NULL CHECK (dimensions = 256),
    text_sha256 text NOT NULL,
    embedding vector(256) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (segment_id, model, text_sha256)
);
CREATE TABLE IF NOT EXISTS query_vectors (
    query_sha256 text NOT NULL,
    model text NOT NULL,
    dimensions integer NOT NULL CHECK (dimensions = 256),
    embedding vector(256) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (query_sha256, model)
);
