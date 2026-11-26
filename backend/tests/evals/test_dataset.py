"""Testy ładowania, deduplikacji, podziału dev/test i walidacji etykiet TechQA."""

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

from app.evals.dataset import (
    DatasetError,
    TechQAContext,
    TechQARecord,
    assign_splits,
    deduplicate_and_filter,
    find_duplicate_groups,
    load_techqa_records,
    load_verified_dataset,
    load_verified_dataset_with_metadata,
)
from app.settings import Settings
from app.techqa.importer import Manifest


def _make_record(
    record_id: str,
    question: str,
    *,
    is_impossible: bool = False,
    doc_id: str | None = None,
    answer: str = "ans",
) -> TechQARecord:
    contexts = [TechQAContext(filename=f"{doc_id}.txt", text="ctx")] if doc_id else []
    return TechQARecord(
        id=record_id,
        question=question,
        answer="" if is_impossible else answer,
        is_impossible=is_impossible,
        contexts=contexts,
    )


def _write_train_and_manifest(
    root: Path, records: list[dict[str, Any]], revision: str = "abc123"
) -> tuple[Path, Manifest]:
    techqa_dir = root / "techqa"
    techqa_dir.mkdir(parents=True, exist_ok=True)
    train_bytes = json.dumps(records).encode("utf-8")
    (techqa_dir / "train.json").write_bytes(train_bytes)
    manifest = Manifest(
        source="test/synth",
        revision=revision,
        files={"train.json": hashlib.sha256(train_bytes).hexdigest()},
        expected_documents=1,
    )
    return techqa_dir, manifest


def _real_techqa_dir() -> Path | None:
    candidates: list[Path] = []
    env_dir = os.environ.get("TECHQA_DIR")
    if env_dir:
        candidates.append(Path(env_dir))
    default = Settings.model_fields["techqa_dir"].default
    candidates.append(default if isinstance(default, Path) else Path(str(default)))
    candidates.append(Path(__file__).resolve().parents[3] / "data" / "raw" / "techqa")
    for candidate in candidates:
        if (candidate / "train.json").is_file():
            return candidate
    return None


def test_load_techqa_records_verifies_sha256(tmp_path: Path) -> None:
    raw_records = [
        {
            "id": "TRAIN_Q001",
            "question": "How to restart?",
            "answer": "Run restart",
            "is_impossible": False,
            "contexts": [{"filename": "doc1.txt", "text": "body"}],
        },
        {
            "id": "TRAIN_Q002",
            "question": "Unknown error?",
            "answer": "-",
            "is_impossible": True,
            "contexts": None,
        },
    ]
    techqa_dir, manifest = _write_train_and_manifest(tmp_path, raw_records)

    loaded = load_techqa_records(techqa_dir, manifest=manifest)
    assert len(loaded) == 2
    assert loaded[0].primary_doc_id == "doc1"
    assert loaded[1].contexts == []

    bad_manifest = Manifest(
        source=manifest.source,
        revision=manifest.revision,
        files={"train.json": "0" * 64},
        expected_documents=1,
    )
    with pytest.raises(DatasetError, match="SHA-256"):
        load_techqa_records(techqa_dir, manifest=bad_manifest)


def test_deduplicate_and_filter_keeps_smallest_id_and_excludes_conflicts() -> None:
    records = [
        _make_record("TRAIN_Q010", "  Same question? \n", doc_id="d1"),
        _make_record("DEV_Q001", "Same question?", doc_id="d1"),
        _make_record("TRAIN_Q020", "Conflicting?", is_impossible=False, doc_id="d2"),
        _make_record("DEV_Q002", "Conflicting?", is_impossible=True),
        _make_record("TRAIN_Q030", "Unique unanswerable?", is_impossible=True),
    ]

    duplicate_groups = find_duplicate_groups(records)
    assert len(duplicate_groups) == 2

    deduped, conflicts = deduplicate_and_filter(records)
    assert [r.id for r in deduped] == ["DEV_Q001", "TRAIN_Q030"]
    assert len(conflicts) == 1
    assert conflicts[0].record_ids == ["DEV_Q002", "TRAIN_Q020"]
    assert conflicts[0].answerable_ids == ["TRAIN_Q020"]
    assert conflicts[0].unanswerable_ids == ["DEV_Q002"]


def test_assign_splits_no_canonical_doc_leakage_and_deterministic() -> None:
    records = [
        _make_record("Q01", "q1", doc_id="doc_a"),
        _make_record("Q02", "q2", doc_id="doc_a_copy"),
        _make_record("Q03", "q3", doc_id="doc_b"),
        _make_record("Q04", "q4", doc_id="doc_b"),
        _make_record("Q05", "q5", doc_id="doc_c"),
        _make_record("Q06", "q6", doc_id="doc_d"),
        _make_record("Q07", "q7", doc_id="doc_e"),
        _make_record("Q08", "q8", is_impossible=True),
        _make_record("Q09", "q9", is_impossible=True),
        _make_record("Q10", "q10", is_impossible=True),
        _make_record("Q11", "q11", is_impossible=True),
    ]
    canonical_map = {"doc_a": "doc_a", "doc_a_copy": "doc_a"}

    splits_first = assign_splits(
        records, canonical_doc_map=canonical_map, dev_ratio=0.3, seed=42
    )
    splits_second = assign_splits(
        list(reversed(records)), canonical_doc_map=canonical_map, dev_ratio=0.3, seed=42
    )
    assert splits_first == splits_second
    assert splits_first["Q01"] == splits_first["Q02"]
    assert splits_first["Q03"] == splits_first["Q04"]

    dev_docs = {
        canonical_map.get(r.primary_doc_id, r.primary_doc_id)
        for r in records
        if not r.is_impossible and r.primary_doc_id and splits_first[r.id] == "dev"
    }
    test_docs = {
        canonical_map.get(r.primary_doc_id, r.primary_doc_id)
        for r in records
        if not r.is_impossible and r.primary_doc_id and splits_first[r.id] == "test"
    }
    assert dev_docs.isdisjoint(test_docs)

    unans_dev = sum(
        1 for r in records if r.is_impossible and splits_first[r.id] == "dev"
    )
    assert unans_dev == 1


def test_assign_splits_rejects_invalid_dev_ratio() -> None:
    with pytest.raises(ValueError, match="dev_ratio"):
        assign_splits([], dev_ratio=0.0)
    with pytest.raises(ValueError, match="dev_ratio"):
        assign_splits([], dev_ratio=1.0)


def test_load_verified_dataset_excludes_ambiguous_and_validates(tmp_path: Path) -> None:
    raw_records = [
        {
            "id": "Q1",
            "question": "Question 1",
            "answer": "-",
            "is_impossible": True,
            "contexts": [],
        },
        {
            "id": "Q2",
            "question": "Question 2",
            "answer": "Answer 2",
            "is_impossible": False,
            "contexts": [{"filename": "doc_2.txt", "text": "x"}],
        },
        {
            "id": "Q3",
            "question": "Question 3",
            "answer": "-",
            "is_impossible": True,
            "contexts": [],
        },
    ]
    techqa_dir, manifest = _write_train_and_manifest(tmp_path, raw_records)
    labels_path = tmp_path / "abstention-dataset.json"

    payload: dict[str, Any] = {
        "schema_version": 1,
        "snapshot_id": manifest.snapshot_id,
        "train_json_sha256": manifest.files["train.json"],
        "split_seed": 20261125,
        "dev_ratio": 0.3,
        "excluded_conflict_ids": [],
        "items": [
            {
                "question_id": "Q1",
                "split": "dev",
                "original_is_impossible": True,
                "canonical_doc_id": None,
                "verified_label": "verified_unanswerable",
                "reviewer_note": "No match in top-10",
                "reviewed_at": "2026-11-25",
            },
            {
                "question_id": "Q2",
                "split": "test",
                "original_is_impossible": False,
                "canonical_doc_id": "doc_2",
                "verified_label": "answerable_in_corpus",
                "reviewer_note": "",
                "reviewed_at": "2026-11-25",
            },
            {
                "question_id": "Q3",
                "split": "test",
                "original_is_impossible": True,
                "canonical_doc_id": None,
                "verified_label": "ambiguous",
                "reviewer_note": "Unclear",
                "reviewed_at": "2026-11-25",
            },
        ],
    }
    labels_path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = load_verified_dataset_with_metadata(
        labels_path, techqa_dir, split="all", manifest=manifest
    )
    assert loaded.metadata.total_labeled == 3
    assert loaded.metadata.ambiguous_count == 1
    assert loaded.metadata.active_count == 2
    assert [item.question_id for item in loaded.items] == ["Q1", "Q2"]
    assert loaded.items[0].question == "Question 1"
    assert loaded.items[1].doc_ids == ["doc_2"]

    dev_only = load_verified_dataset(
        labels_path, techqa_dir, split="dev", manifest=manifest
    )
    assert [item.question_id for item in dev_only] == ["Q1"]


def test_load_verified_dataset_rejects_duplicates_missing_labels_and_leakage(
    tmp_path: Path,
) -> None:
    raw_records = [
        {
            "id": "Q1",
            "question": "Question 1",
            "answer": "A1",
            "is_impossible": False,
            "contexts": [{"filename": "doc_shared.txt", "text": "x"}],
        },
        {
            "id": "Q2",
            "question": "Question 2",
            "answer": "A2",
            "is_impossible": False,
            "contexts": [{"filename": "doc_shared.txt", "text": "x"}],
        },
    ]
    techqa_dir, manifest = _write_train_and_manifest(tmp_path, raw_records)
    labels_path = tmp_path / "labels.json"

    base: dict[str, Any] = {
        "schema_version": 1,
        "snapshot_id": manifest.snapshot_id,
        "train_json_sha256": manifest.files["train.json"],
        "split_seed": 20261125,
        "dev_ratio": 0.3,
        "excluded_conflict_ids": [],
    }

    # Przeciek canonical_doc_id między dev i test
    leak_payload = {
        **base,
        "items": [
            {
                "question_id": "Q1",
                "split": "dev",
                "original_is_impossible": False,
                "canonical_doc_id": "doc_shared",
                "verified_label": "answerable_in_corpus",
            },
            {
                "question_id": "Q2",
                "split": "test",
                "original_is_impossible": False,
                "canonical_doc_id": "doc_shared",
                "verified_label": "answerable_in_corpus",
            },
        ],
    }
    labels_path.write_text(json.dumps(leak_payload), encoding="utf-8")
    with pytest.raises(DatasetError, match="przeciek"):
        load_verified_dataset(labels_path, techqa_dir, manifest=manifest)

    # Duplikat question_id
    dup_payload = {
        **base,
        "items": [
            {
                "question_id": "Q1",
                "split": "dev",
                "original_is_impossible": False,
                "canonical_doc_id": "doc_shared",
                "verified_label": "answerable_in_corpus",
            },
            {
                "question_id": "Q1",
                "split": "dev",
                "original_is_impossible": False,
                "canonical_doc_id": "doc_shared",
                "verified_label": "answerable_in_corpus",
            },
        ],
    }
    labels_path.write_text(json.dumps(dup_payload), encoding="utf-8")
    with pytest.raises(DatasetError, match="Duplikat"):
        load_verified_dataset(labels_path, techqa_dir, manifest=manifest)

    # Brakująca etykieta verified_label
    missing_label_payload = {
        **base,
        "items": [
            {
                "question_id": "Q1",
                "split": "dev",
                "original_is_impossible": False,
                "canonical_doc_id": "doc_shared",
                "verified_label": None,
            }
        ],
    }
    labels_path.write_text(json.dumps(missing_label_payload), encoding="utf-8")
    with pytest.raises(DatasetError, match="schemat"):
        load_verified_dataset(labels_path, techqa_dir, manifest=manifest)


def test_load_verified_dataset_normalizes_dash_reference_answer(
    tmp_path: Path,
) -> None:
    raw_records = [
        {
            "id": "Q1",
            "question": "Question 1",
            "answer": "-",
            "is_impossible": True,
            "contexts": [],
        },
        {
            "id": "Q2",
            "question": "Question 2",
            "answer": "Real answer",
            "is_impossible": False,
            "contexts": [{"filename": "doc_2.txt", "text": "x"}],
        },
    ]
    techqa_dir, manifest = _write_train_and_manifest(tmp_path, raw_records)
    labels_path = tmp_path / "labels.json"
    payload = {
        "schema_version": 1,
        "snapshot_id": manifest.snapshot_id,
        "train_json_sha256": manifest.files["train.json"],
        "split_seed": 20261125,
        "dev_ratio": 0.3,
        "excluded_conflict_ids": [],
        "items": [
            {
                "question_id": "Q1",
                "split": "test",
                "original_is_impossible": True,
                "canonical_doc_id": None,
                "verified_label": "answerable_in_corpus",
                "reviewer_note": "Found in corpus",
                "reviewed_at": "2026-11-26",
            },
            {
                "question_id": "Q2",
                "split": "test",
                "original_is_impossible": False,
                "canonical_doc_id": "doc_2",
                "verified_label": "answerable_in_corpus",
                "reviewer_note": "",
                "reviewed_at": "2026-11-26",
            },
        ],
    }
    labels_path.write_text(json.dumps(payload), encoding="utf-8")
    items = load_verified_dataset(labels_path, techqa_dir, manifest=manifest)
    by_id = {item.question_id: item for item in items}
    assert by_id["Q1"].answer == ""
    assert by_id["Q2"].answer == "Real answer"


def test_frozen_abstention_dataset_meets_phase5_invariants() -> None:
    dataset_path = Path(__file__).resolve().parents[2] / "evals/abstention-dataset.json"
    assert dataset_path.is_file(), "Brak zamrożonego evals/abstention-dataset.json"
    raw = json.loads(dataset_path.read_text(encoding="utf-8"))
    items = raw["items"]
    unanswerable = [i for i in items if i["verified_label"] == "verified_unanswerable"]
    answerable = [i for i in items if i["verified_label"] == "answerable_in_corpus"]
    assert len(unanswerable) >= 50
    assert len(answerable) >= 50

    qids = [i["question_id"] for i in items]
    assert len(qids) == len(set(qids))
    conflicts = set(raw.get("excluded_conflict_ids", []))
    assert conflicts.isdisjoint(qids)

    dev_docs = {
        i["canonical_doc_id"]
        for i in items
        if i["split"] == "dev" and i.get("canonical_doc_id")
    }
    test_docs = {
        i["canonical_doc_id"]
        for i in items
        if i["split"] == "test" and i.get("canonical_doc_id")
    }
    assert dev_docs.isdisjoint(test_docs)


@pytest.mark.corpus
@pytest.mark.skipif(_real_techqa_dir() is None, reason="brak train.json (TECHQA_DIR)")
def test_real_train_json_counts_and_no_split_leakage() -> None:
    techqa_dir = _real_techqa_dir()
    assert techqa_dir is not None

    records = load_techqa_records(techqa_dir)
    assert len(records) == 910

    duplicate_groups = find_duplicate_groups(records)
    assert len(duplicate_groups) == 20

    deduped, conflicts = deduplicate_and_filter(records)
    assert len(conflicts) == 6

    splits = assign_splits(deduped)
    dev_docs = {
        r.primary_doc_id
        for r in deduped
        if not r.is_impossible and r.primary_doc_id and splits[r.id] == "dev"
    }
    test_docs = {
        r.primary_doc_id
        for r in deduped
        if not r.is_impossible and r.primary_doc_id and splits[r.id] == "test"
    }
    assert dev_docs.isdisjoint(test_docs)

    dev_questions = {r.normalized_question for r in deduped if splits[r.id] == "dev"}
    test_questions = {r.normalized_question for r in deduped if splits[r.id] == "test"}
    assert dev_questions.isdisjoint(test_questions)
