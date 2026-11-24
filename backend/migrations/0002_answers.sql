-- Zapisane odpowiedzi anonimowej sesji. Celowo BRAK kluczy obcych do snapshots,
-- documents i chunks: reimport migawki kasuje je kaskadowo, a odpowiedzi muszą przetrwać.
-- snapshot_id i chunk_set_id to tylko tekstowe wskazanie stanu korpusu z chwili odpowiedzi.
CREATE TABLE answers (
    id uuid PRIMARY KEY,
    session_hash text NOT NULL, -- SHA-256 tokenu sesji; sam token nie jest przechowywany
    question text NOT NULL,
    outcome text NOT NULL CHECK (outcome IN ('answered', 'abstained', 'failed')),
    snapshot_id text NOT NULL,
    chunk_set_id text NOT NULL,
    result jsonb, -- NULL dla outcome = 'failed'
    config jsonb NOT NULL, -- model, k, wersje promptów, zestaw fragmentów
    error text,
    trace_id text,
    duration_ms integer,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX answers_session_created_idx ON answers (session_hash, created_at DESC);
