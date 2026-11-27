-- Bieżące decyzje redaktora per teza oraz niemutowalna historia zdarzeń audytu.
-- Izolacja per session_hash pozwala wielu sesjom niezależnie oceniać rekordy demo
-- bez wzajemnego nadpisywania decyzji i zdarzeń człowieka.
CREATE TABLE audit_claim_decisions (
    id uuid PRIMARY KEY,
    audit_id uuid NOT NULL REFERENCES audits(id) ON DELETE CASCADE,
    claim_id uuid NOT NULL REFERENCES audit_claims(id) ON DELETE CASCADE,
    session_hash text NOT NULL,
    decision text NOT NULL CHECK (
        decision IN (
            'agree_with_system',
            'request_source_or_verify',
            'consider_doc_update',
            'system_verdict_wrong'
        )
    ),
    justification text NOT NULL CHECK (justification ~ '\S'),
    role_label text NOT NULL CHECK (role_label IN ('editor', 'consultant')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (claim_id, session_hash)
);

CREATE INDEX audit_claim_decisions_audit_session_idx
    ON audit_claim_decisions (audit_id, session_hash);

CREATE TABLE audit_events (
    id uuid PRIMARY KEY,
    seq bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    audit_id uuid NOT NULL REFERENCES audits(id) ON DELETE CASCADE,
    claim_id uuid REFERENCES audit_claims(id) ON DELETE CASCADE,
    session_hash text,
    event_type text NOT NULL CHECK (
        event_type IN (
            'audit_created',
            'evaluation_completed',
            'evaluation_failed',
            'decision_saved',
            'decision_updated'
        )
    ),
    actor_type text NOT NULL CHECK (actor_type IN ('system', 'human')),
    role_label text CHECK (
        role_label IS NULL OR role_label IN ('editor', 'consultant')
    ),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (
        (actor_type = 'system' AND session_hash IS NULL)
        OR (actor_type = 'human' AND session_hash IS NOT NULL)
    )
);

CREATE INDEX audit_events_audit_created_idx
    ON audit_events (audit_id, created_at ASC, seq ASC);

-- Jednorazowy backfill zdarzeń systemowych dla audytów utworzonych przed migracją 0005.
INSERT INTO audit_events (
    id,
    audit_id,
    claim_id,
    session_hash,
    event_type,
    actor_type,
    role_label,
    payload,
    created_at
)
SELECT
    gen_random_uuid(),
    a.id,
    NULL,
    NULL,
    'audit_created',
    'system',
    NULL,
    jsonb_build_object('case_ref', a.case_ref),
    a.created_at
FROM audits AS a;

INSERT INTO audit_events (
    id,
    audit_id,
    claim_id,
    session_hash,
    event_type,
    actor_type,
    role_label,
    payload,
    created_at
)
SELECT
    gen_random_uuid(),
    a.id,
    NULL,
    NULL,
    'evaluation_completed',
    'system',
    NULL,
    jsonb_build_object(
        'note_verdict', a.note_verdict,
        'claims_total', a.claims_total
    ),
    COALESCE(a.completed_at, a.updated_at)
FROM audits AS a
WHERE a.status = 'completed';

INSERT INTO audit_events (
    id,
    audit_id,
    claim_id,
    session_hash,
    event_type,
    actor_type,
    role_label,
    payload,
    created_at
)
SELECT
    gen_random_uuid(),
    a.id,
    NULL,
    NULL,
    'evaluation_failed',
    'system',
    NULL,
    '{}'::jsonb,
    a.updated_at
FROM audits AS a
WHERE a.status = 'failed';
