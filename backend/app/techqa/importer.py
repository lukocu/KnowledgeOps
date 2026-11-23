"""Import migawki TechQA: weryfikacja, deduplikacja, transakcja, hash stanu."""

import hashlib
import json
import re
import statistics
import time
import zipfile
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import psycopg
from psycopg.types.json import Jsonb

from app.techqa.chunking import Chunk, ChunkerConfig, chunk_document
from app.techqa.normalize import normalize_body
from app.techqa.parse import parse_document

MANIFEST_PATH = Path(__file__).resolve().parent / "manifest.json"

# Stały klucz blokady doradczej importu TechQA.
IMPORT_LOCK_KEY = 7_204_001
_ENTRY_PATTERN = re.compile(r"^corpus/([^/]+)\.txt$")
_COPY_DOCUMENTS = (
    "COPY documents (snapshot_id, doc_id, canonical_doc_id, title, raw_text,"
    " raw_sha256, text, text_sha256) FROM STDIN"
)
_COPY_CHUNKS = (
    "COPY chunks (id, chunk_set_id, snapshot_id, doc_id, ordinal, headings,"
    " start_offset, end_offset, text, text_sha256) FROM STDIN"
)

Comparison = Literal["pierwszy import", "identyczny", "różny"]


class ImportFailure(Exception):
    """Weryfikacja lub zapis importu nie powiodły się; baza zostaje bez zmian."""


@dataclass(frozen=True)
class Manifest:
    source: str
    revision: str
    files: dict[str, str]
    expected_documents: int

    @property
    def snapshot_id(self) -> str:
        return f"techqa@{self.revision}"

    def chunk_set_id(self, config: ChunkerConfig) -> str:
        return f"{self.snapshot_id}/{config.variant}"


def load_manifest(path: Path = MANIFEST_PATH) -> Manifest:
    data = json.loads(path.read_text(encoding="utf-8"))
    return Manifest(
        source=data["source"],
        revision=data["revision"],
        files=dict(data["files"]),
        expected_documents=int(data["expected_documents"]),
    )


@dataclass(frozen=True)
class TrainCheck:
    records: int
    references: int
    distinct_documents: int
    missing: int


@dataclass
class ImportReport:
    snapshot_id: str
    chunk_set_id: str
    files: int
    documents: int
    canonical_documents: int
    duplicate_groups: list[tuple[str, list[str]]]
    chunks: int
    chunks_median_per_document: float
    chunks_max_per_document: int
    documents_without_chunks: list[str]
    train: TrainCheck
    timings: dict[str, float] = field(default_factory=dict)
    state_sha256: str = ""
    comparison: Comparison = "pierwszy import"


@dataclass(frozen=True)
class _Document:
    doc_id: str
    canonical_doc_id: str
    title: str
    raw_text: str
    raw_sha256: str
    text: str
    text_sha256: str


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1 << 20):
            digest.update(block)
    return digest.hexdigest()


def _verify_files(data_dir: Path, manifest: Manifest) -> None:
    revision_file = data_dir / "revision.txt"
    if not revision_file.is_file():
        raise ImportFailure(f"Brak pliku {revision_file}")
    revision = revision_file.read_text(encoding="utf-8").strip()
    if revision != manifest.revision:
        raise ImportFailure(
            f"Rewizja {revision!r} z revision.txt różni się od manifestu"
            f" {manifest.revision!r}"
        )
    for name, expected in manifest.files.items():
        path = data_dir / name
        if not path.is_file():
            raise ImportFailure(f"Brak pliku {path}")
        actual = _sha256_file(path)
        if actual != expected:
            raise ImportFailure(
                f"SHA-256 pliku {name} ({actual}) różni się od manifestu ({expected})"
            )


def _read_corpus(zip_path: Path) -> list[tuple[str, bytes]]:
    """Zwraca (doc_id, bajty) posortowane po doc_id; katalogi pomijane."""
    entries: dict[str, bytes] = {}
    try:
        archive_file = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:
        raise ImportFailure(f"Uszkodzony plik zip {zip_path.name}: {exc}") from exc
    with archive_file as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            match = _ENTRY_PATTERN.fullmatch(info.filename)
            if match is None:
                raise ImportFailure(
                    f"Nieoczekiwany wpis w corpus.zip: {info.filename!r}"
                )
            doc_id = match.group(1)
            if doc_id in entries:
                raise ImportFailure(f"Powtórzony wpis w corpus.zip: {info.filename!r}")
            entries[doc_id] = archive.read(info)
    return sorted(entries.items())


def _check_train(train_path: Path, doc_ids: set[str]) -> TrainCheck:
    try:
        records = json.loads(train_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ImportFailure(f"Nieprawidłowy plik {train_path.name}: {exc}") from exc
    references: list[str] = []
    for record in records:
        for context in record.get("contexts") or []:
            if "filename" not in context:
                raise ImportFailure(
                    f"Rekord {record.get('id')!r} w {train_path.name}"
                    " ma kontekst bez pola filename"
                )
            filename = str(context["filename"])
            references.append(filename.removesuffix(".txt"))
    missing = sorted({ref for ref in references if ref not in doc_ids})
    if missing:
        raise ImportFailure(
            f"train.json odwołuje się do {len(missing)} nieistniejących dokumentów,"
            f" np. {', '.join(missing[:5])}"
        )
    return TrainCheck(
        records=len(records),
        references=len(references),
        distinct_documents=len(set(references)),
        missing=0,
    )


def _build_documents(corpus: list[tuple[str, bytes]]) -> list[_Document]:
    decoded: list[tuple[str, str, str]] = []
    groups: dict[str, list[str]] = defaultdict(list)
    for doc_id, raw in corpus:
        try:
            raw_text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ImportFailure(
                f"Plik {doc_id}.txt nie jest poprawnym UTF-8: {exc}"
            ) from exc
        raw_sha = hashlib.sha256(raw).hexdigest()
        decoded.append((doc_id, raw_text, raw_sha))
        groups[raw_sha].append(doc_id)
    # Korpus jest posortowany po doc_id, więc ids[0] to najmniejszy doc_id grupy.
    canonical_of = {doc_id: ids[0] for ids in groups.values() for doc_id in ids}

    documents: list[_Document] = []
    for doc_id, raw_text, raw_sha in decoded:
        try:
            parsed = parse_document(raw_text)
        except ValueError as exc:
            raise ImportFailure(f"Plik {doc_id}.txt: {exc}") from exc
        text = normalize_body(parsed.body)
        documents.append(
            _Document(
                doc_id=doc_id,
                canonical_doc_id=canonical_of[doc_id],
                title=parsed.title,
                raw_text=raw_text,
                raw_sha256=raw_sha,
                text=text,
                text_sha256=_sha(text),
            )
        )
    return documents


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _insert_chunk_set(
    conn: psycopg.Connection, manifest: Manifest, config: ChunkerConfig
) -> None:
    conn.execute(
        "INSERT INTO chunk_sets (id, snapshot_id, variant, config, config_sha256,"
        " chunk_count, state_sha256) VALUES (%s, %s, %s, %s, %s, NULL, NULL)",
        (
            manifest.chunk_set_id(config),
            manifest.snapshot_id,
            config.variant,
            Jsonb(asdict(config)),
            config.config_sha256(),
        ),
    )


def _state_hash(
    conn: psycopg.Connection, manifest: Manifest, config: ChunkerConfig
) -> str:
    """SHA-256 posortowanych wierszy z bazy (bez znaczników czasu)."""
    digest = hashlib.sha256()

    def feed(value: Any) -> None:
        digest.update(_canonical_json(value).encode("utf-8"))
        digest.update(b"\n")

    feed(["manifest", asdict(manifest)])
    feed(["config", asdict(config)])
    with conn.cursor(name="state_hash_documents") as cursor:
        cursor.execute(
            "SELECT doc_id, canonical_doc_id, title, raw_sha256, text_sha256"
            ' FROM documents WHERE snapshot_id = %s ORDER BY doc_id COLLATE "C"',
            (manifest.snapshot_id,),
        )
        for row in cursor:
            feed(["document", *row])
    with conn.cursor(name="state_hash_chunks") as cursor:
        cursor.execute(
            "SELECT id, doc_id, ordinal, headings, start_offset, end_offset,"
            " text_sha256 FROM chunks WHERE chunk_set_id = %s"
            ' ORDER BY id COLLATE "C"',
            (manifest.chunk_set_id(config),),
        )
        for row in cursor:
            feed(["chunk", *row])
    return digest.hexdigest()


def import_snapshot(
    conn: psycopg.Connection,
    data_dir: Path,
    manifest: Manifest,
    config: ChunkerConfig,
) -> ImportReport:
    """Weryfikuje migawkę i zastępuje jej stan w bazie jedną transakcją."""
    timings: dict[str, float] = {}

    started = time.perf_counter()
    _verify_files(data_dir, manifest)
    corpus = _read_corpus(data_dir / "corpus.zip")
    if len(corpus) != manifest.expected_documents:
        raise ImportFailure(
            f"Liczba dokumentów w corpus.zip ({len(corpus)}) różni się od"
            f" oczekiwanej ({manifest.expected_documents})"
        )
    train = _check_train(data_dir / "train.json", {doc_id for doc_id, _ in corpus})
    timings["weryfikacja"] = time.perf_counter() - started

    started = time.perf_counter()
    documents = _build_documents(corpus)
    del corpus
    chunk_set_id = manifest.chunk_set_id(config)
    chunks_by_doc: dict[str, list[Chunk]] = {}
    duplicates: dict[str, list[str]] = defaultdict(list)
    for document in documents:
        if document.doc_id == document.canonical_doc_id:
            chunks_by_doc[document.doc_id] = chunk_document(document.text, config)
        else:
            duplicates[document.canonical_doc_id].append(document.doc_id)
    per_document = [len(chunks) for chunks in chunks_by_doc.values()]
    timings["normalizacja i chunking"] = time.perf_counter() - started

    started = time.perf_counter()
    with conn.transaction():
        # Blokada: dwa równoległe importy nie mogą czytać nieaktualnego stanu.
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (IMPORT_LOCK_KEY,))
        # 1. poprzedni hash stanu (brak wiersza oznacza pierwszy import)
        row = conn.execute(
            "SELECT state_sha256 FROM chunk_sets WHERE id = %s", (chunk_set_id,)
        ).fetchone()
        had_previous = row is not None
        previous = row[0] if row else None
        # 2.
        conn.execute("SET LOCAL work_mem = '64MB'")
        # 3. jawne usunięcie poprzedniego stanu w kolejności zależności.
        # Uwaga: import zastępuje CAŁĄ migawkę (wszystkie jej zestawy fragmentów,
        # dokumenty i wiersz migawki). Przy drugim wariancie chunkera (S-12)
        # trzeba zawęzić usuwanie do jednego zestawu.
        conn.execute(
            "DELETE FROM chunks WHERE chunk_set_id IN"
            " (SELECT id FROM chunk_sets WHERE snapshot_id = %s)",
            (manifest.snapshot_id,),
        )
        conn.execute(
            "DELETE FROM chunk_sets WHERE snapshot_id = %s", (manifest.snapshot_id,)
        )
        conn.execute(
            "DELETE FROM documents WHERE snapshot_id = %s", (manifest.snapshot_id,)
        )
        conn.execute("DELETE FROM snapshots WHERE id = %s", (manifest.snapshot_id,))
        # 4.
        conn.execute(
            "INSERT INTO snapshots (id, source, revision, manifest)"
            " VALUES (%s, %s, %s, %s)",
            (
                manifest.snapshot_id,
                manifest.source,
                manifest.revision,
                Jsonb(manifest.files),
            ),
        )
        # 5.
        with conn.cursor() as cursor, cursor.copy(_COPY_DOCUMENTS) as copy:
            for d in documents:
                copy.write_row(
                    (
                        manifest.snapshot_id,
                        d.doc_id,
                        d.canonical_doc_id,
                        d.title,
                        d.raw_text,
                        d.raw_sha256,
                        d.text,
                        d.text_sha256,
                    )
                )
        # 6.
        _insert_chunk_set(conn, manifest, config)
        # 7.
        with conn.cursor() as cursor, cursor.copy(_COPY_CHUNKS) as copy:
            for doc_id, chunks in chunks_by_doc.items():
                for chunk in chunks:
                    copy.write_row(
                        (
                            f"{chunk_set_id}/{doc_id}/{chunk.ordinal}",
                            chunk_set_id,
                            manifest.snapshot_id,
                            doc_id,
                            chunk.ordinal,
                            list(chunk.headings),
                            chunk.start,
                            chunk.end,
                            chunk.text,
                            _sha(chunk.text),
                        )
                    )
        timings["zapis"] = time.perf_counter() - started
        # 8.
        started = time.perf_counter()
        state_sha256 = _state_hash(conn, manifest, config)
        timings["hash stanu"] = time.perf_counter() - started
        # 9.
        count_row = conn.execute(
            "SELECT count(*) FROM chunks WHERE chunk_set_id = %s", (chunk_set_id,)
        ).fetchone()
        if count_row is None:
            raise ImportFailure("Nie udało się policzyć fragmentów zestawu")
        chunk_count = int(count_row[0])
        conn.execute(
            "UPDATE chunk_sets SET chunk_count = %s, state_sha256 = %s,"
            " built_at = now() WHERE id = %s",
            (chunk_count, state_sha256, chunk_set_id),
        )
    # 10. commit następuje przy wyjściu z bloku transaction()

    comparison: Comparison
    if not had_previous or previous is None:
        comparison = "pierwszy import"
    elif previous == state_sha256:
        comparison = "identyczny"
    else:
        comparison = "różny"

    return ImportReport(
        snapshot_id=manifest.snapshot_id,
        chunk_set_id=chunk_set_id,
        files=len(documents),
        documents=len(documents),
        canonical_documents=len(chunks_by_doc),
        duplicate_groups=sorted(
            (canonical, sorted(copies)) for canonical, copies in duplicates.items()
        ),
        chunks=chunk_count,
        chunks_median_per_document=float(statistics.median(per_document))
        if per_document
        else 0.0,
        chunks_max_per_document=max(per_document, default=0),
        documents_without_chunks=sorted(
            doc_id for doc_id, chunks in chunks_by_doc.items() if not chunks
        ),
        train=train,
        timings=timings,
        state_sha256=state_sha256,
        comparison=comparison,
    )
