-- Schemat migawki TechQA: dokumenty, zestawy fragmentów i fragmenty z indeksami wyszukiwania.
-- Rozszerzenia tworzone tutaj, żeby schemat powstawał także na bazie bez db/init.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_search;

CREATE TABLE snapshots (
    id text PRIMARY KEY, -- techqa@<rewizja>
    source text NOT NULL,
    revision text NOT NULL,
    manifest jsonb NOT NULL, -- nazwa pliku -> SHA-256
    imported_at timestamptz NOT NULL DEFAULT now()
);

-- Klucze obce mają ON DELETE CASCADE (wycofanie migawki jednym DELETE) i nie są DEFERRABLE.
CREATE TABLE documents (
    snapshot_id text NOT NULL REFERENCES snapshots (id) ON DELETE CASCADE,
    doc_id text NOT NULL, -- nazwa pliku bez .txt
    canonical_doc_id text NOT NULL, -- równa doc_id dla dokumentu kanonicznego
    title text NOT NULL,
    raw_text text NOT NULL,
    raw_sha256 text NOT NULL,
    text text NOT NULL, -- znormalizowana treść
    text_sha256 text NOT NULL,
    PRIMARY KEY (snapshot_id, doc_id)
);

CREATE TABLE chunk_sets (
    id text PRIMARY KEY,
    snapshot_id text NOT NULL REFERENCES snapshots (id) ON DELETE CASCADE,
    variant text NOT NULL,
    config jsonb NOT NULL,
    config_sha256 text NOT NULL,
    chunk_count int, -- NULL do końca importu
    state_sha256 text, -- NULL do końca importu
    built_at timestamptz
);

CREATE TABLE chunks (
    id text PRIMARY KEY,
    chunk_set_id text NOT NULL REFERENCES chunk_sets (id) ON DELETE CASCADE,
    snapshot_id text NOT NULL,
    doc_id text NOT NULL,
    ordinal int NOT NULL,
    headings text[] NOT NULL,
    start_offset int NOT NULL, -- przesunięcia w znakach znormalizowanej treści
    end_offset int NOT NULL,
    text text NOT NULL,
    text_sha256 text NOT NULL,
    tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
    FOREIGN KEY (snapshot_id, doc_id) REFERENCES documents (snapshot_id, doc_id) ON DELETE CASCADE,
    UNIQUE (chunk_set_id, doc_id, ordinal),
    CHECK (start_offset >= 0 AND end_offset > start_offset)
);

CREATE INDEX chunks_snapshot_doc_idx ON chunks (snapshot_id, doc_id);
CREATE INDEX chunks_tsv_idx ON chunks USING gin (tsv);

-- Jedyny indeks ParadeDB na tabeli. Sprawdzone na pg_search 0.27.0: stemmer=english
-- i stopwords_language=english działają razem ('Running the servers' -> {run,server}).
CREATE INDEX chunks_search_idx ON chunks USING paradedb (
    id,
    chunk_set_id,
    (text::pdb.simple('stemmer=english', 'stopwords_language=english'))
);
