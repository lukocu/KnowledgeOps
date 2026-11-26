-- Dokumenty syntetyczne (migawka synthetic@v1) z metadanymi oraz wynik `conflicting`
-- w zapisanych odpowiedziach. Metadane są NULL dla dokumentów TechQA.
ALTER TABLE documents
    ADD COLUMN is_synthetic boolean NOT NULL DEFAULT false,
    ADD COLUMN doc_date text,
    ADD COLUMN product_version text,
    ADD COLUMN audience text;

-- Nazwa domyślna ograniczenia kolumnowego z 0002: answers_outcome_check.
ALTER TABLE answers DROP CONSTRAINT answers_outcome_check;
ALTER TABLE answers
    ADD CONSTRAINT answers_outcome_check
    CHECK (outcome IN ('answered', 'abstained', 'conflicting', 'failed'));