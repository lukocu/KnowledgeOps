-- Zapisane audyty notatek ze spraw i ich zweryfikowane tezy. Celowo BRAK kluczy
-- obcych do snapshots, documents i chunks: reimport migawki kasuje je kaskadowo,
-- a wyniki audytów muszą przetrwać. snapshot_id i chunk_set_ids to tekstowe
-- wskazanie stanu korpusu z chwili analizy.
CREATE TABLE audits (
    id uuid PRIMARY KEY,
    session_hash text NOT NULL,
    is_demo boolean NOT NULL DEFAULT false,
    case_ref text,
    case_description text NOT NULL,
    resolution_note text NOT NULL,
    status text NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    stage text NOT NULL CHECK (
        stage IN (
            'queued',
            'extracting',
            'retrieving',
            'verifying',
            'aggregating',
            'completed',
            'failed'
        )
    ),
    claims_total integer NOT NULL DEFAULT 0,
    claims_done integer NOT NULL DEFAULT 0,
    note_verdict text CHECK (
        note_verdict IN ('full', 'partial', 'contradiction', 'insufficient')
    ),
    case_context jsonb,
    snapshot_id text NOT NULL,
    chunk_set_ids text[] NOT NULL,
    config jsonb NOT NULL,
    error text,
    trace_id text,
    duration_ms integer,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);

CREATE TABLE audit_claims (
    id uuid PRIMARY KEY,
    audit_id uuid NOT NULL REFERENCES audits(id) ON DELETE CASCADE,
    claim_index smallint NOT NULL,
    claim_label text NOT NULL,
    claim_text text NOT NULL,
    source_excerpt text NOT NULL,
    source_start integer,
    source_end integer,
    search_query text NOT NULL,
    verdict text NOT NULL CHECK (
        verdict IN ('supported', 'contradicted', 'insufficient')
    ),
    rationale text NOT NULL,
    scope_note text,
    evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
    checked_docs jsonb NOT NULL DEFAULT '[]'::jsonb,
    error text,
    UNIQUE (audit_id, claim_index)
);

CREATE INDEX audits_session_created_idx ON audits (session_hash, created_at DESC);
CREATE INDEX audit_claims_audit_idx ON audit_claims (audit_id, claim_index);
