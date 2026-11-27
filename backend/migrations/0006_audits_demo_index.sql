-- Częściowy indeks wspierający odczyt wspólnych przykładów demo na liście /analizy.
CREATE INDEX IF NOT EXISTS audits_demo_updated_idx
    ON audits (updated_at DESC)
    WHERE is_demo = true;
