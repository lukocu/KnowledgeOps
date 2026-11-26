"""Testy eksportu kandydatów abstynencji (Markdown + JSON) i zamrażania etykiet."""

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import psycopg
import pytest

from app.evals.dataset import DatasetError, load_verified_dataset
from app.evals.prepare import (
    prepare_abstention_candidates,
    validate_and_freeze_labels,
)
from app.techqa.importer import Manifest
from app.techqa.search import SearchHit


class _FakeCursor:
    def __init__(self, rows: list[tuple[str, str, str]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[tuple[str, str, str]]:
        return self._rows


class _FakeConn:
    def __init__(self, rows: list[tuple[str, str, str]]) -> None:
        self._rows = rows

    def execute(self, query: str, params: tuple[Any, ...] | None = None) -> _FakeCursor:
        assert "FROM documents" in query
        assert params is not None
        return _FakeCursor(self._rows)


def _build_synthetic_techqa(tmp_path: Path) -> tuple[Path, Manifest]:
    records: list[dict[str, Any]] = []
    for idx in range(1, 11):
        records.append(
            {
                "id": f"TRAIN_U{idx:02d}",
                "question": f"Unanswerable question {idx}?",
                "answer": "-",
                "is_impossible": True,
                "contexts": [],
            }
        )
    for idx in range(1, 11):
        doc_name = "doc_dup_b" if idx == 2 else f"doc_{idx:02d}"
        records.append(
            {
                "id": f"TRAIN_A{idx:02d}",
                "question": f"Answerable question {idx}?",
                "answer": f"Answer {idx}",
                "is_impossible": False,
                "contexts": [{"filename": f"{doc_name}.txt", "text": "body"}],
            }
        )
    # Grupa konfliktu (powinna zostać wykluczona)
    records.append(
        {
            "id": "TRAIN_C01",
            "question": "Conflicting question?",
            "answer": "Yes",
            "is_impossible": False,
            "contexts": [{"filename": "doc_01.txt", "text": "body"}],
        }
    )
    records.append(
        {
            "id": "TRAIN_C02",
            "question": "Conflicting question?",
            "answer": "-",
            "is_impossible": True,
            "contexts": [],
        }
    )

    techqa_dir = tmp_path / "techqa"
    techqa_dir.mkdir(parents=True, exist_ok=True)
    raw_bytes = json.dumps(records).encode("utf-8")
    (techqa_dir / "train.json").write_bytes(raw_bytes)
    manifest = Manifest(
        source="test/synth",
        revision="deadbeef",
        files={"train.json": hashlib.sha256(raw_bytes).hexdigest()},
        expected_documents=10,
    )
    return techqa_dir, manifest


def test_prepare_abstention_candidates_writes_markdown_and_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    techqa_dir, manifest = _build_synthetic_techqa(tmp_path)
    doc_rows = [
        ("doc_dup_b", "doc_01", "Duplicated | Title"),
        *[(f"doc_{idx:02d}", f"doc_{idx:02d}", f"Title {idx}") for idx in range(1, 11)],
    ]
    fake_conn = cast(psycopg.Connection, _FakeConn(doc_rows))

    def _fake_search(
        conn: psycopg.Connection,
        query: str,
        *,
        method: str,
        chunk_set_id: str,
        k: int = 10,
    ) -> list[SearchHit]:
        assert method == "bm25"
        assert k == 3
        return [
            SearchHit(
                rank=1,
                score=4.25,
                chunk_id=f"{chunk_set_id}/doc_dup_b/0",
                doc_id="doc_dup_b",
                headings=["SYMPTOM"],
                snippet="Line 1\nLine 2 | pipe",
            )
        ]

    monkeypatch.setattr("app.evals.prepare.search_chunks", _fake_search)

    out_dir = tmp_path / "out"
    report = prepare_abstention_candidates(
        fake_conn,
        techqa_dir=techqa_dir,
        chunk_set_id=f"{manifest.snapshot_id}/sections-v1",
        out_dir=out_dir,
        unanswerable_candidates=6,
        answerable_candidates=6,
        top_k=3,
        seed=20261125,
        manifest=manifest,
    )

    assert report.total_records == 22
    assert report.deduplicated_records == 20
    assert report.conflict_groups == 1
    assert report.excluded_conflict_ids == 2
    assert report.selected_unanswerable_dev + report.selected_unanswerable_test == 6
    assert report.selected_answerable_dev + report.selected_answerable_test == 6
    assert report.review_markdown_path.is_file()
    assert report.template_json_path.is_file()

    markdown = report.review_markdown_path.read_text(encoding="utf-8")
    assert "Duplicated \\| Title" in markdown
    assert "Line 1 Line 2 \\| pipe" in markdown
    assert "TRAIN_C01" not in markdown

    template = json.loads(report.template_json_path.read_text(encoding="utf-8"))
    assert template["schema_version"] == 1
    assert template["excluded_conflict_ids"] == ["TRAIN_C01", "TRAIN_C02"]
    assert len(template["items"]) == 12
    for item in template["items"]:
        assert "question" not in item
        assert "answer" not in item
        if item["original_is_impossible"]:
            assert item["verified_label"] is None
            assert item["canonical_doc_id"] is None
        else:
            assert item["verified_label"] == "answerable_in_corpus"
            assert item["canonical_doc_id"] is not None
            if item["question_id"] == "TRAIN_A02":
                assert item["canonical_doc_id"] == "doc_01"


def test_validate_and_freeze_labels_rejects_null_and_freezes_clean_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    techqa_dir, manifest = _build_synthetic_techqa(tmp_path)
    doc_rows = [
        ("doc_dup_b", "doc_01", "Duplicated Title"),
        *[(f"doc_{idx:02d}", f"doc_{idx:02d}", f"Title {idx}") for idx in range(1, 11)],
    ]
    fake_conn = cast(psycopg.Connection, _FakeConn(doc_rows))
    monkeypatch.setattr("app.evals.prepare.search_chunks", lambda *args, **kwargs: [])

    out_dir = tmp_path / "out"
    report = prepare_abstention_candidates(
        fake_conn,
        techqa_dir=techqa_dir,
        chunk_set_id=f"{manifest.snapshot_id}/sections-v1",
        out_dir=out_dir,
        unanswerable_candidates=4,
        answerable_candidates=4,
        top_k=2,
        manifest=manifest,
    )

    frozen_path = tmp_path / "frozen" / "abstention-dataset.json"

    # Niekompletny szablon (verified_label=null) musi zostać odrzucony
    with pytest.raises(DatasetError, match="verified_label"):
        validate_and_freeze_labels(
            report.template_json_path,
            frozen_path,
            techqa_dir,
            manifest=manifest,
        )

    # Uzupełniamy etykiety i dorzucamy przypadkowe pole tekstu do odfiltrowania
    template = json.loads(report.template_json_path.read_text(encoding="utf-8"))
    unans_idx = 0
    for item in template["items"]:
        item["extra_question_text"] = "should not leak into frozen file"
        if item["original_is_impossible"]:
            item["verified_label"] = (
                "ambiguous" if unans_idx == 0 else "verified_unanswerable"
            )
            item["reviewer_note"] = "checked"
            item["reviewed_at"] = "2026-11-25"
            unans_idx += 1
    report.template_json_path.write_text(json.dumps(template), encoding="utf-8")

    summary = validate_and_freeze_labels(
        report.template_json_path,
        frozen_path,
        techqa_dir,
        manifest=manifest,
    )
    assert summary.total_items == 8
    assert summary.dev_ambiguous + summary.test_ambiguous == 1
    assert summary.dev_verified_unanswerable + summary.test_verified_unanswerable == 3
    assert summary.dev_answerable_in_corpus + summary.test_answerable_in_corpus == 4

    frozen_raw = json.loads(frozen_path.read_text(encoding="utf-8"))
    for item in frozen_raw["items"]:
        assert "extra_question_text" not in item
        assert "question" not in item

    active = load_verified_dataset(frozen_path, techqa_dir, manifest=manifest)
    assert len(active) == 7


def test_prepare_refuses_to_overwrite_existing_template_without_force(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    techqa_dir, manifest = _build_synthetic_techqa(tmp_path)
    doc_rows = [
        (f"doc_{idx:02d}", f"doc_{idx:02d}", f"Title {idx}") for idx in range(1, 11)
    ]
    fake_conn = cast(psycopg.Connection, _FakeConn(doc_rows))
    monkeypatch.setattr("app.evals.prepare.search_chunks", lambda *args, **kwargs: [])

    out_dir = tmp_path / "out"
    first = prepare_abstention_candidates(
        fake_conn,
        techqa_dir=techqa_dir,
        chunk_set_id=f"{manifest.snapshot_id}/sections-v1",
        out_dir=out_dir,
        unanswerable_candidates=2,
        answerable_candidates=2,
        top_k=2,
        manifest=manifest,
    )
    sentinel = '{"manual": "work-in-progress"}\n'
    first.template_json_path.write_text(sentinel, encoding="utf-8")

    with pytest.raises(FileExistsError, match="--force"):
        prepare_abstention_candidates(
            fake_conn,
            techqa_dir=techqa_dir,
            chunk_set_id=f"{manifest.snapshot_id}/sections-v1",
            out_dir=out_dir,
            unanswerable_candidates=2,
            answerable_candidates=2,
            top_k=2,
            manifest=manifest,
        )
    assert first.template_json_path.read_text(encoding="utf-8") == sentinel

    second = prepare_abstention_candidates(
        fake_conn,
        techqa_dir=techqa_dir,
        chunk_set_id=f"{manifest.snapshot_id}/sections-v1",
        out_dir=out_dir,
        unanswerable_candidates=2,
        answerable_candidates=2,
        top_k=2,
        manifest=manifest,
        overwrite=True,
    )
    assert second.template_json_path.read_text(encoding="utf-8") != sentinel
