"""Import migawki syntetycznej `synthetic@v1`: autorskie dokumenty z metadanymi.

Dokumenty przechodzą przez ten sam `normalize_body()` i `chunk_document()` co TechQA,
więc fragmenty mają te same offsety i niezmienniki. Import jest transakcyjny
i idempotentny; kasuje wyłącznie wiersze migawki `synthetic@v1`.
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from app.techqa.chunking import ChunkerConfig, chunk_document
from app.techqa.importer import Comparison, ImportFailure
from app.techqa.normalize import normalize_body

SYNTHETIC_SNAPSHOT_ID = "synthetic@v1"
SYNTHETIC_SOURCE = "synthetic"
SYNTHETIC_REVISION = "v1"
DOCUMENTS_PATH = Path(__file__).resolve().parent / "documents.json"

# Stały klucz blokady doradczej importu syntetycznego (osobny od TechQA).
SYNTHETIC_IMPORT_LOCK_KEY = 7_204_002


def synthetic_chunk_set_id(config: ChunkerConfig) -> str:
    return f"{SYNTHETIC_SNAPSHOT_ID}/{config.variant}"


@dataclass(frozen=True)
class SyntheticDocument:
    doc_id: str
    title: str
    doc_date: str | None
    product_version: str | None
    audience: str | None
    body: str


@dataclass
class SyntheticImportReport:
    snapshot_id: str
    chunk_set_id: str
    documents: int
    chunks: int
    state_sha256: str
    comparison: Comparison


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def load_synthetic_documents(path: Path) -> list[SyntheticDocument]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data["snapshot_id"] != SYNTHETIC_SNAPSHOT_ID:
            raise ImportFailure(
                f"Plik {path.name} opisuje migawkę {data['snapshot_id']!r},"
                f" oczekiwano {SYNTHETIC_SNAPSHOT_ID!r}"
            )
        documents = [
            SyntheticDocument(
                doc_id=str(item["doc_id"]),
                title=str(item["title"]),
                doc_date=item.get("doc_date"),
                product_version=item.get("product_version"),
                audience=item.get("audience"),
                body=str(item["body"]),
            )
            for item in data["documents"]
        ]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ImportFailure(f"Nieprawidłowy plik {path}: {exc}") from exc
    ids = [d.doc_id for d in documents]
    if len(set(ids)) != len(ids):
        raise ImportFailure(f"Powtórzone doc_id w {path.name}")
    return sorted(documents, key=lambda d: d.doc_id)


def _state_hash(
    conn: psycopg.Connection, config: ChunkerConfig, chunk_set_id: str
) -> str:
    """SHA-256 posortowanych wierszy migawki z bazy (bez znaczników czasu)."""
    digest = hashlib.sha256()

    def feed(value: Any) -> None:
        digest.update(_canonical_json(value).encode("utf-8"))
        digest.update(b"\n")

    feed(["snapshot", SYNTHETIC_SNAPSHOT_ID])
    feed(["config", asdict(config)])
    for row in conn.execute(
        "SELECT doc_id, title, is_synthetic, doc_date, product_version, audience,"
        " raw_sha256, text_sha256 FROM documents WHERE snapshot_id = %s"
        ' ORDER BY doc_id COLLATE "C"',
        (SYNTHETIC_SNAPSHOT_ID,),
    ).fetchall():
        feed(["document", *row])
    for row in conn.execute(
        "SELECT id, doc_id, ordinal, headings, start_offset, end_offset, text_sha256"
        ' FROM chunks WHERE chunk_set_id = %s ORDER BY id COLLATE "C"',
        (chunk_set_id,),
    ).fetchall():
        feed(["chunk", *row])
    return digest.hexdigest()


def import_synthetic_snapshot(
    conn: psycopg.Connection, docs_path: Path, config: ChunkerConfig
) -> SyntheticImportReport:
    """Zastępuje migawkę `synthetic@v1` jedną transakcją; TechQA zostaje nietknięte."""
    documents = load_synthetic_documents(docs_path)
    chunk_set_id = synthetic_chunk_set_id(config)
    prepared = []
    for doc in documents:
        text = normalize_body(doc.body)
        prepared.append((doc, text, chunk_document(text, config)))
    manifest = {docs_path.name: _sha(docs_path.read_text(encoding="utf-8"))}

    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (SYNTHETIC_IMPORT_LOCK_KEY,))
        row = conn.execute(
            "SELECT state_sha256 FROM chunk_sets WHERE id = %s", (chunk_set_id,)
        ).fetchone()
        had_previous = row is not None
        previous = row[0] if row else None

        conn.execute(
            "DELETE FROM chunks WHERE chunk_set_id IN"
            " (SELECT id FROM chunk_sets WHERE snapshot_id = %s)",
            (SYNTHETIC_SNAPSHOT_ID,),
        )
        conn.execute(
            "DELETE FROM chunk_sets WHERE snapshot_id = %s", (SYNTHETIC_SNAPSHOT_ID,)
        )
        conn.execute(
            "DELETE FROM documents WHERE snapshot_id = %s", (SYNTHETIC_SNAPSHOT_ID,)
        )
        conn.execute("DELETE FROM snapshots WHERE id = %s", (SYNTHETIC_SNAPSHOT_ID,))

        conn.execute(
            "INSERT INTO snapshots (id, source, revision, manifest)"
            " VALUES (%s, %s, %s, %s)",
            (
                SYNTHETIC_SNAPSHOT_ID,
                SYNTHETIC_SOURCE,
                SYNTHETIC_REVISION,
                Jsonb(manifest),
            ),
        )
        for doc, text, _ in prepared:
            conn.execute(
                "INSERT INTO documents (snapshot_id, doc_id, canonical_doc_id, title,"
                " raw_text, raw_sha256, text, text_sha256, is_synthetic, doc_date,"
                " product_version, audience)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, true, %s, %s, %s)",
                (
                    SYNTHETIC_SNAPSHOT_ID,
                    doc.doc_id,
                    doc.doc_id,
                    doc.title,
                    doc.body,
                    _sha(doc.body),
                    text,
                    _sha(text),
                    doc.doc_date,
                    doc.product_version,
                    doc.audience,
                ),
            )
        conn.execute(
            "INSERT INTO chunk_sets (id, snapshot_id, variant, config, config_sha256,"
            " chunk_count, state_sha256) VALUES (%s, %s, %s, %s, %s, NULL, NULL)",
            (
                chunk_set_id,
                SYNTHETIC_SNAPSHOT_ID,
                config.variant,
                Jsonb(asdict(config)),
                config.config_sha256(),
            ),
        )
        chunk_count = 0
        for doc, _, chunks in prepared:
            for chunk in chunks:
                conn.execute(
                    "INSERT INTO chunks (id, chunk_set_id, snapshot_id, doc_id,"
                    " ordinal, headings, start_offset, end_offset, text, text_sha256)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        f"{chunk_set_id}/{doc.doc_id}/{chunk.ordinal}",
                        chunk_set_id,
                        SYNTHETIC_SNAPSHOT_ID,
                        doc.doc_id,
                        chunk.ordinal,
                        list(chunk.headings),
                        chunk.start,
                        chunk.end,
                        chunk.text,
                        _sha(chunk.text),
                    ),
                )
                chunk_count += 1
        state_sha256 = _state_hash(conn, config, chunk_set_id)
        conn.execute(
            "UPDATE chunk_sets SET chunk_count = %s, state_sha256 = %s,"
            " built_at = now() WHERE id = %s",
            (chunk_count, state_sha256, chunk_set_id),
        )

    comparison: Comparison
    if not had_previous or previous is None:
        comparison = "pierwszy import"
    elif previous == state_sha256:
        comparison = "identyczny"
    else:
        comparison = "różny"
    return SyntheticImportReport(
        snapshot_id=SYNTHETIC_SNAPSHOT_ID,
        chunk_set_id=chunk_set_id,
        documents=len(prepared),
        chunks=chunk_count,
        state_sha256=state_sha256,
        comparison=comparison,
    )
