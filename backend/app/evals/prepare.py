"""Eksport kandydatów abstynencji z top-10 BM25 oraz zamrażanie pliku etykiet."""

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import psycopg
from pydantic import BaseModel, ConfigDict, ValidationError

from app.evals.dataset import (
    DEFAULT_DEV_RATIO,
    DEFAULT_SPLIT_SEED,
    AbstentionDatasetFile,
    DatasetError,
    Split,
    TechQARecord,
    assign_splits,
    deduplicate_and_filter,
    load_techqa_records,
    resolve_canonical_doc_id,
    validate_dataset_entries,
)
from app.techqa.importer import Manifest, load_manifest
from app.techqa.search import SearchHit, search_chunks

REVIEW_MARKDOWN_FILENAME = "abstention-candidates-review.md"
TEMPLATE_JSON_FILENAME = "abstention-labels-template.json"


class PrepareReport(BaseModel):
    """Podsumowanie eksportu kandydatów do ręcznej weryfikacji."""

    model_config = ConfigDict(frozen=True)

    snapshot_id: str
    chunk_set_id: str
    total_records: int
    deduplicated_records: int
    conflict_groups: int
    excluded_conflict_ids: int
    selected_unanswerable_dev: int
    selected_unanswerable_test: int
    selected_answerable_dev: int
    selected_answerable_test: int
    review_markdown_path: Path
    template_json_path: Path


class FreezeSummary(BaseModel):
    """Podsumowanie walidacji i zapisu zamrożonego pliku etykiet."""

    model_config = ConfigDict(frozen=True)

    target_path: Path
    total_items: int
    dev_verified_unanswerable: int
    dev_answerable_in_corpus: int
    dev_ambiguous: int
    test_verified_unanswerable: int
    test_answerable_in_corpus: int
    test_ambiguous: int


def _fetch_document_metadata(
    conn: psycopg.Connection, snapshot_id: str
) -> tuple[dict[str, str], dict[str, str]]:
    """Pobiera `doc_id -> canonical_doc_id` oraz `doc_id -> title` jednym zapytaniem."""
    rows = conn.execute(
        "SELECT doc_id, canonical_doc_id, title FROM documents WHERE snapshot_id = %s",
        (snapshot_id,),
    ).fetchall()
    canonical_doc_map: dict[str, str] = {}
    doc_titles: dict[str, str] = {}
    for doc_id, canonical_doc_id, title in rows:
        doc_key = str(doc_id)
        canonical_doc_map[doc_key] = str(canonical_doc_id)
        doc_titles[doc_key] = str(title)
    return canonical_doc_map, doc_titles


def _select_stratified(
    records: Sequence[TechQARecord],
    splits: dict[str, Split],
    *,
    total: int,
    dev_ratio: float,
) -> tuple[list[TechQARecord], list[TechQARecord]]:
    """Dobiera kandydatów proporcjonalnie `dev`/`test` po sortowaniu `question_id`."""
    if total < 0:
        raise ValueError("Liczba kandydatów nie może być ujemna")
    dev_pool = sorted(
        (record for record in records if splits[record.id] == "dev"),
        key=lambda record: record.id,
    )
    test_pool = sorted(
        (record for record in records if splits[record.id] == "test"),
        key=lambda record: record.id,
    )
    dev_target = min(len(dev_pool), round(total * dev_ratio))
    test_target = min(len(test_pool), total - dev_target)

    remaining = total - (dev_target + test_target)
    if remaining > 0 and dev_target < len(dev_pool):
        extra_dev = min(remaining, len(dev_pool) - dev_target)
        dev_target += extra_dev
        remaining -= extra_dev
    if remaining > 0 and test_target < len(test_pool):
        extra_test = min(remaining, len(test_pool) - test_target)
        test_target += extra_test

    return dev_pool[:dev_target], test_pool[:test_target]


def _escape_md_cell(text: str) -> str:
    collapsed = " ".join(text.split())
    return collapsed.replace("|", "\\|")


def _render_review_markdown(
    *,
    snapshot_id: str,
    chunk_set_id: str,
    candidates: Sequence[tuple[TechQARecord, Split, list[SearchHit]]],
    doc_titles: dict[str, str],
) -> str:
    lines: list[str] = [
        "# Przegląd kandydatów abstynencji (is_impossible=true)",
        "",
        f"- Migawka: `{snapshot_id}`",
        f"- Zestaw fragmentów: `{chunk_set_id}`",
        f"- Liczba kandydatów `is_impossible=true`: {len(candidates)}",
        "",
        "Dla każdego kandydata uzupełnij w szablonie JSON pole `verified_label`:",
        "- `verified_unanswerable` — żaden dokument w korpusie"
        " nie odpowiada na pytanie",
        "- `answerable_in_corpus` — w top-10 BM25 znaleziono dokument z odpowiedzią",
        "- `ambiguous` — przypadek niejednoznaczny (wykluczany z aktywnej ewaluacji)",
        "",
    ]

    for record, split, hits in candidates:
        lines.append(f"## {record.id} (`{split}`)")
        lines.append("")
        lines.append("**Pytanie:**")
        lines.append("")
        lines.append(record.question.strip())
        lines.append("")
        if not hits:
            lines.append("_Brak wyników BM25._")
            lines.append("")
            continue
        lines.append("| # | doc_id | score | tytuł | fragment |")
        lines.append("|---:|---|---:|---|---|")
        for hit in hits:
            title = _escape_md_cell(doc_titles.get(hit.doc_id, ""))
            snippet = _escape_md_cell(hit.snippet)
            lines.append(
                f"| {hit.rank} | `{hit.doc_id}` | {hit.score:.3f}"
                f" | {title} | {snippet} |"
            )
        lines.append("")

    return "\n".join(lines)


def prepare_abstention_candidates(
    conn: psycopg.Connection,
    *,
    techqa_dir: Path,
    chunk_set_id: str,
    out_dir: Path,
    unanswerable_candidates: int = 80,
    answerable_candidates: int = 60,
    top_k: int = 10,
    seed: int = DEFAULT_SPLIT_SEED,
    dev_ratio: float = DEFAULT_DEV_RATIO,
    manifest: Manifest | None = None,
    overwrite: bool = False,
) -> PrepareReport:
    """Eksportuje kandydatów z top-10 BM25 do Markdown oraz szablonu JSON."""
    if top_k < 1:
        raise ValueError("top_k musi być dodatnie")

    template_json_path = out_dir / TEMPLATE_JSON_FILENAME
    if not overwrite and template_json_path.exists():
        raise FileExistsError(
            f"Plik szablonu etykiet już istnieje: {template_json_path}. "
            "Użyj flagi --force (overwrite=True), aby go nadpisać."
        )

    active_manifest = manifest if manifest is not None else load_manifest()
    records = load_techqa_records(techqa_dir, manifest=active_manifest)
    deduped, conflict_groups = deduplicate_and_filter(records)
    excluded_conflict_ids = sorted(
        record_id for group in conflict_groups for record_id in group.record_ids
    )

    canonical_doc_map, doc_titles = _fetch_document_metadata(
        conn, active_manifest.snapshot_id
    )
    splits = assign_splits(
        deduped,
        canonical_doc_map=canonical_doc_map,
        dev_ratio=dev_ratio,
        seed=seed,
    )

    unanswerable_records = [record for record in deduped if record.is_impossible]
    answerable_records = [record for record in deduped if not record.is_impossible]

    unans_dev, unans_test = _select_stratified(
        unanswerable_records,
        splits,
        total=unanswerable_candidates,
        dev_ratio=dev_ratio,
    )
    ans_dev, ans_test = _select_stratified(
        answerable_records,
        splits,
        total=answerable_candidates,
        dev_ratio=dev_ratio,
    )

    selected_unanswerable = sorted(
        [*unans_dev, *unans_test], key=lambda record: record.id
    )
    selected_answerable = sorted([*ans_dev, *ans_test], key=lambda record: record.id)

    review_entries: list[tuple[TechQARecord, Split, list[SearchHit]]] = []
    for record in selected_unanswerable:
        hits = search_chunks(
            conn,
            record.question,
            method="bm25",
            chunk_set_id=chunk_set_id,
            k=top_k,
        )
        review_entries.append((record, splits[record.id], hits))

    template_items: list[dict[str, Any]] = []
    for record in selected_unanswerable:
        template_items.append(
            {
                "question_id": record.id,
                "split": splits[record.id],
                "original_is_impossible": True,
                "canonical_doc_id": None,
                "verified_label": None,
                "reviewer_note": "",
                "reviewed_at": "",
            }
        )

    for record in selected_answerable:
        doc_id = record.primary_doc_id
        canonical_doc_id = resolve_canonical_doc_id(record, canonical_doc_map)
        has_confirmed_doc = doc_id is not None and (
            not canonical_doc_map or doc_id in canonical_doc_map
        )
        template_items.append(
            {
                "question_id": record.id,
                "split": splits[record.id],
                "original_is_impossible": False,
                "canonical_doc_id": canonical_doc_id,
                "verified_label": "answerable_in_corpus" if has_confirmed_doc else None,
                "reviewer_note": "",
                "reviewed_at": "",
            }
        )

    template_items.sort(key=lambda item: str(item["question_id"]))

    template_payload: dict[str, Any] = {
        "schema_version": 1,
        "snapshot_id": active_manifest.snapshot_id,
        "train_json_sha256": active_manifest.files["train.json"],
        "split_seed": seed,
        "dev_ratio": dev_ratio,
        "excluded_conflict_ids": excluded_conflict_ids,
        "items": template_items,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    review_markdown_path = out_dir / REVIEW_MARKDOWN_FILENAME
    template_json_path = out_dir / TEMPLATE_JSON_FILENAME

    review_markdown = _render_review_markdown(
        snapshot_id=active_manifest.snapshot_id,
        chunk_set_id=chunk_set_id,
        candidates=review_entries,
        doc_titles=doc_titles,
    )
    review_markdown_path.write_text(review_markdown, encoding="utf-8")
    template_json_path.write_text(
        json.dumps(template_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return PrepareReport(
        snapshot_id=active_manifest.snapshot_id,
        chunk_set_id=chunk_set_id,
        total_records=len(records),
        deduplicated_records=len(deduped),
        conflict_groups=len(conflict_groups),
        excluded_conflict_ids=len(excluded_conflict_ids),
        selected_unanswerable_dev=len(unans_dev),
        selected_unanswerable_test=len(unans_test),
        selected_answerable_dev=len(ans_dev),
        selected_answerable_test=len(ans_test),
        review_markdown_path=review_markdown_path,
        template_json_path=template_json_path,
    )


def validate_and_freeze_labels(
    template_path: Path,
    target_path: Path,
    techqa_dir: Path,
    *,
    manifest: Manifest | None = None,
) -> FreezeSummary:
    """Waliduje uzupełniony szablon etykiet i zapisuje czysty plik zamrożony."""
    if not template_path.is_file():
        raise DatasetError(f"Brak pliku szablonu {template_path}")

    try:
        raw = json.loads(template_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise DatasetError(
            f"Nieprawidłowy JSON szablonu {template_path}: {exc}"
        ) from exc

    if not isinstance(raw, dict) or not isinstance(raw.get("items"), list):
        raise DatasetError(
            f"Plik szablonu {template_path} musi być obiektem JSON z listą items"
        )

    missing_labels = [
        str(item.get("question_id", f"index:{idx}"))
        for idx, item in enumerate(raw["items"])
        if isinstance(item, dict) and item.get("verified_label") is None
    ]
    if missing_labels:
        raise DatasetError(
            f"Brak wypełnionej etykiety verified_label dla {len(missing_labels)}"
            f" rekordów, np. {', '.join(missing_labels[:5])}"
        )

    try:
        dataset = AbstentionDatasetFile.model_validate(raw)
    except ValidationError as exc:
        raise DatasetError(
            f"Nieprawidłowy schemat szablonu {template_path}: {exc}"
        ) from exc

    active_manifest = manifest if manifest is not None else load_manifest()
    records = load_techqa_records(techqa_dir, manifest=active_manifest)
    validate_dataset_entries(dataset, records, active_manifest)

    cleaned = AbstentionDatasetFile(
        schema_version=dataset.schema_version,
        snapshot_id=dataset.snapshot_id,
        train_json_sha256=dataset.train_json_sha256,
        split_seed=dataset.split_seed,
        dev_ratio=dataset.dev_ratio,
        excluded_conflict_ids=sorted(set(dataset.excluded_conflict_ids)),
        items=sorted(dataset.items, key=lambda entry: entry.question_id),
    )

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(
        json.dumps(cleaned.model_dump(mode="json"), indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )

    def _count(split: Split, label: str) -> int:
        return sum(
            1
            for entry in cleaned.items
            if entry.split == split and entry.verified_label == label
        )

    return FreezeSummary(
        target_path=target_path,
        total_items=len(cleaned.items),
        dev_verified_unanswerable=_count("dev", "verified_unanswerable"),
        dev_answerable_in_corpus=_count("dev", "answerable_in_corpus"),
        dev_ambiguous=_count("dev", "ambiguous"),
        test_verified_unanswerable=_count("test", "verified_unanswerable"),
        test_answerable_in_corpus=_count("test", "answerable_in_corpus"),
        test_ambiguous=_count("test", "ambiguous"),
    )
