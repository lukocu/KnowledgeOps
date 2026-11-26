"""Ładowanie, deduplikacja, podział dev/test i walidacja etykiet TechQA."""

import hashlib
import json
import random
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.techqa.importer import Manifest, load_manifest

DEFAULT_DEV_RATIO = 0.3
DEFAULT_SPLIT_SEED = 20261125

VerifiedLabel = Literal["verified_unanswerable", "answerable_in_corpus", "ambiguous"]
Split = Literal["dev", "test"]


class DatasetError(ValueError):
    """Błąd walidacji danych źródłowych TechQA lub zamrożonego zbioru etykiet."""


class TechQAContext(BaseModel):
    """Pojedynczy kontekst dokumentu powiązany z rekordem `train.json`."""

    model_config = ConfigDict(frozen=True)

    filename: str
    text: str = ""

    @property
    def doc_id(self) -> str:
        return self.filename.removesuffix(".txt")


class TechQARecord(BaseModel):
    """Pojedynczy rekord pytania z pliku `train.json`."""

    model_config = ConfigDict(frozen=True)

    id: str
    question: str
    answer: str = ""
    is_impossible: bool
    contexts: list[TechQAContext] = Field(default_factory=list)

    @field_validator("contexts", mode="before")
    @classmethod
    def _coerce_null_contexts(cls, value: Any) -> Any:
        if value is None:
            return []
        return value

    @property
    def normalized_question(self) -> str:
        return self.question.strip()

    @property
    def doc_ids(self) -> list[str]:
        return [context.doc_id for context in self.contexts]

    @property
    def primary_doc_id(self) -> str | None:
        return self.contexts[0].doc_id if self.contexts else None


class ConflictGroup(BaseModel):
    """Grupa identycznych pytań ze sprzeczną etykietą `is_impossible`."""

    model_config = ConfigDict(frozen=True)

    question: str
    record_ids: list[str]
    answerable_ids: list[str]
    unanswerable_ids: list[str]


class LabelEntry(BaseModel):
    """Wpis etykiety w zamrożonym pliku `abstention-dataset.json` (bez tekstu)."""

    model_config = ConfigDict(frozen=True)

    question_id: str
    split: Split
    original_is_impossible: bool
    canonical_doc_id: str | None = None
    verified_label: VerifiedLabel
    reviewer_note: str = ""
    reviewed_at: str = ""


class AbstentionDatasetFile(BaseModel):
    """Kontrakt zamrożonego pliku `backend/evals/abstention-dataset.json`."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = 1
    snapshot_id: str
    train_json_sha256: str
    split_seed: int = DEFAULT_SPLIT_SEED
    dev_ratio: float = DEFAULT_DEV_RATIO
    excluded_conflict_ids: list[str] = Field(default_factory=list)
    items: list[LabelEntry]


class EvalItem(BaseModel):
    """Aktywny element zbioru ewaluacyjnego po złączeniu etykiety z `train.json`."""

    model_config = ConfigDict(frozen=True)

    question_id: str
    split: Split
    original_is_impossible: bool
    canonical_doc_id: str | None = None
    verified_label: VerifiedLabel
    reviewer_note: str = ""
    reviewed_at: str = ""
    question: str
    answer: str
    doc_ids: list[str] = Field(default_factory=list)


class DatasetMetadata(BaseModel):
    """Metadane wczytanego zbioru etykiet do raportów ewaluacyjnych."""

    model_config = ConfigDict(frozen=True)

    schema_version: int
    snapshot_id: str
    train_json_sha256: str
    split_seed: int
    dev_ratio: float
    excluded_conflict_ids: list[str]
    total_labeled: int
    ambiguous_count: int
    active_count: int


class LoadedDataset(BaseModel):
    """Aktywne pytania ewaluacyjne wraz z metadanymi (w tym liczbą `ambiguous`)."""

    model_config = ConfigDict(frozen=True)

    metadata: DatasetMetadata
    items: list[EvalItem]


def sha256_file(path: Path) -> str:
    """Oblicza SHA-256 pliku strumieniowo."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1 << 20):
            digest.update(block)
    return digest.hexdigest()


def load_techqa_records(
    techqa_dir: Path, *, manifest: Manifest | None = None
) -> list[TechQARecord]:
    """Wczytuje `train.json` i weryfikuje jego SHA-256 względem manifestu."""
    active_manifest = manifest if manifest is not None else load_manifest()
    expected_sha = active_manifest.files.get("train.json")
    if expected_sha is None:
        raise DatasetError("Manifest nie zawiera wpisu SHA-256 dla train.json")

    train_path = techqa_dir / "train.json"
    if not train_path.is_file():
        raise DatasetError(f"Brak pliku {train_path}")

    actual_sha = sha256_file(train_path)
    if actual_sha != expected_sha:
        raise DatasetError(
            f"SHA-256 pliku train.json ({actual_sha}) różni się od manifestu"
            f" ({expected_sha})"
        )

    try:
        raw = json.loads(train_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise DatasetError(f"Nieprawidłowy plik {train_path}: {exc}") from exc

    if not isinstance(raw, list):
        raise DatasetError(f"Plik {train_path} musi zawierać tablicę JSON rekordów")

    try:
        return [TechQARecord.model_validate(entry) for entry in raw]
    except ValidationError as exc:
        raise DatasetError(f"Nieprawidłowy rekord w {train_path}: {exc}") from exc


def _group_by_question(
    records: Sequence[TechQARecord],
) -> dict[str, list[TechQARecord]]:
    groups: dict[str, list[TechQARecord]] = defaultdict(list)
    for record in records:
        groups[record.normalized_question].append(record)
    return groups


def find_duplicate_groups(records: Sequence[TechQARecord]) -> list[list[TechQARecord]]:
    """Zwraca grupy identycznych pytań (`question.strip()`) o liczności > 1."""
    groups = _group_by_question(records)
    duplicates = [
        sorted(group, key=lambda record: record.id)
        for group in groups.values()
        if len(group) > 1
    ]
    return sorted(duplicates, key=lambda group: group[0].id)


def deduplicate_and_filter(
    records: list[TechQARecord],
) -> tuple[list[TechQARecord], list[ConflictGroup]]:
    """Deduplikuje pytania po `question.strip()` i wyklucza konflikty `is_impossible`.

    Z niesprzecznych grup duplikatów stabilnie wybiera rekord o najmniejszym `id`.
    """
    groups = _group_by_question(records)
    kept: list[TechQARecord] = []
    conflicts: list[ConflictGroup] = []

    for question, group in groups.items():
        ordered = sorted(group, key=lambda record: record.id)
        flags = {record.is_impossible for record in ordered}
        if len(flags) > 1:
            conflicts.append(
                ConflictGroup(
                    question=question,
                    record_ids=[record.id for record in ordered],
                    answerable_ids=[
                        record.id for record in ordered if not record.is_impossible
                    ],
                    unanswerable_ids=[
                        record.id for record in ordered if record.is_impossible
                    ],
                )
            )
            continue
        kept.append(ordered[0])

    kept.sort(key=lambda record: record.id)
    conflicts.sort(key=lambda group: group.record_ids[0])
    return kept, conflicts


def resolve_canonical_doc_id(
    record: TechQARecord,
    canonical_doc_map: Mapping[str, str] | None = None,
) -> str | None:
    """Wyznacza `canonical_doc_id` dla rekordu z fallbackiem na `doc_id` kontekstu."""
    doc_id = record.primary_doc_id
    if doc_id is None:
        return None
    if canonical_doc_map is None:
        return doc_id
    return canonical_doc_map.get(doc_id, doc_id)


def assign_splits(
    records: list[TechQARecord],
    *,
    canonical_doc_map: Mapping[str, str] | None = None,
    dev_ratio: float = DEFAULT_DEV_RATIO,
    seed: int = DEFAULT_SPLIT_SEED,
) -> dict[str, Split]:
    """Deterministycznie dzieli rekordy na `dev`/`test` bez przecieku dokumentów.

    Rekordy `is_impossible=False` są grupowane po `canonical_doc_id` (cała grupa
    trafia do `dev` albo `test`), a `is_impossible=True` i `False` są stratyfikowane
    osobno.
    """
    if not 0.0 < dev_ratio < 1.0:
        raise ValueError("dev_ratio musi mieścić się w przedziale (0, 1)")

    splits: dict[str, Split] = {}

    unanswerable = sorted(
        (record for record in records if record.is_impossible),
        key=lambda record: record.id,
    )
    rng_unanswerable = random.Random(f"{seed}:unanswerable")
    rng_unanswerable.shuffle(unanswerable)
    unanswerable_dev_target = round(len(unanswerable) * dev_ratio)
    for index, record in enumerate(unanswerable):
        splits[record.id] = "dev" if index < unanswerable_dev_target else "test"

    answerable = sorted(
        (record for record in records if not record.is_impossible),
        key=lambda record: record.id,
    )
    grouped: dict[str, list[TechQARecord]] = defaultdict(list)
    for record in answerable:
        canonical_id = resolve_canonical_doc_id(record, canonical_doc_map)
        group_key = (
            canonical_id if canonical_id is not None else f"__no_doc__:{record.id}"
        )
        grouped[group_key].append(record)

    ordered_groups = [grouped[key] for key in sorted(grouped)]
    rng_answerable = random.Random(f"{seed}:answerable")
    rng_answerable.shuffle(ordered_groups)

    answerable_dev_target = round(len(answerable) * dev_ratio)
    dev_count = 0
    for group in ordered_groups:
        if dev_count + len(group) <= answerable_dev_target:
            target_split: Split = "dev"
            dev_count += len(group)
        else:
            target_split = "test"
        for record in group:
            splits[record.id] = target_split

    return splits


def validate_dataset_entries(
    dataset: AbstentionDatasetFile,
    records: Sequence[TechQARecord],
    manifest: Manifest,
) -> dict[str, TechQARecord]:
    """Waliduje spójność `AbstentionDatasetFile` z `train.json` i manifestem."""
    if dataset.snapshot_id != manifest.snapshot_id:
        raise DatasetError(
            f"snapshot_id w pliku etykiet ({dataset.snapshot_id!r}) różni się od"
            f" manifestu ({manifest.snapshot_id!r})"
        )

    expected_sha = manifest.files.get("train.json")
    if dataset.train_json_sha256 != expected_sha:
        raise DatasetError(
            f"train_json_sha256 w pliku etykiet ({dataset.train_json_sha256}) różni"
            f" się od manifestu ({expected_sha})"
        )

    records_by_id = {record.id: record for record in records}
    _, conflict_groups = deduplicate_and_filter(list(records))
    conflict_ids = {
        record_id for group in conflict_groups for record_id in group.record_ids
    }
    declared_excluded = set(dataset.excluded_conflict_ids)

    seen_ids: set[str] = set()
    seen_questions: set[str] = set()
    dev_docs: set[str] = set()
    test_docs: set[str] = set()

    for entry in dataset.items:
        if entry.question_id in seen_ids:
            raise DatasetError(
                f"Duplikat question_id w etykietach: {entry.question_id}"
            )
        seen_ids.add(entry.question_id)

        if entry.question_id in conflict_ids or entry.question_id in declared_excluded:
            raise DatasetError(
                f"Rekord konfliktowy nie może występować w items: {entry.question_id}"
            )

        record = records_by_id.get(entry.question_id)
        if record is None:
            raise DatasetError(
                f"question_id {entry.question_id!r} nie istnieje w train.json"
            )

        if entry.original_is_impossible != record.is_impossible:
            raise DatasetError(
                f"Niezgodne original_is_impossible dla {entry.question_id}:"
                f" {entry.original_is_impossible} != {record.is_impossible}"
            )

        question_key = record.normalized_question
        if question_key in seen_questions:
            raise DatasetError(
                f"Duplikat treści pytania w etykietach dla {entry.question_id}"
            )
        seen_questions.add(question_key)

        effective_doc_id = (
            entry.canonical_doc_id
            if entry.canonical_doc_id is not None
            else record.primary_doc_id
        )
        if effective_doc_id is not None:
            if entry.split == "dev":
                dev_docs.add(effective_doc_id)
            else:
                test_docs.add(effective_doc_id)

    leaked_docs = sorted(dev_docs & test_docs)
    if leaked_docs:
        raise DatasetError(
            "Wykryto przeciek canonical_doc_id między dev i test:"
            f" {', '.join(leaked_docs[:5])}"
        )

    return records_by_id


def load_verified_dataset_with_metadata(
    labels_path: Path,
    techqa_dir: Path,
    *,
    split: Literal["dev", "test", "all"] = "all",
    manifest: Manifest | None = None,
) -> LoadedDataset:
    """Wczytuje zamrożony plik etykiet, waliduje go i zwraca aktywne `EvalItem`."""
    if not labels_path.is_file():
        raise DatasetError(f"Brak pliku etykiet {labels_path}")

    try:
        raw = json.loads(labels_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise DatasetError(f"Nieprawidłowy JSON etykiet {labels_path}: {exc}") from exc

    try:
        dataset = AbstentionDatasetFile.model_validate(raw)
    except ValidationError as exc:
        raise DatasetError(
            f"Nieprawidłowy schemat pliku etykiet {labels_path}: {exc}"
        ) from exc

    active_manifest = manifest if manifest is not None else load_manifest()
    records = load_techqa_records(techqa_dir, manifest=active_manifest)
    records_by_id = validate_dataset_entries(dataset, records, active_manifest)

    scoped_entries = [
        entry for entry in dataset.items if split == "all" or entry.split == split
    ]

    ambiguous_count = sum(
        1 for entry in scoped_entries if entry.verified_label == "ambiguous"
    )
    active_items = [
        EvalItem(
            question_id=entry.question_id,
            split=entry.split,
            original_is_impossible=entry.original_is_impossible,
            canonical_doc_id=entry.canonical_doc_id,
            verified_label=entry.verified_label,
            reviewer_note=entry.reviewer_note,
            reviewed_at=entry.reviewed_at,
            question=records_by_id[entry.question_id].question,
            answer=(
                ""
                if records_by_id[entry.question_id].answer.strip() in {"", "-"}
                else records_by_id[entry.question_id].answer
            ),
            doc_ids=records_by_id[entry.question_id].doc_ids,
        )
        for entry in scoped_entries
        if entry.verified_label != "ambiguous"
    ]

    metadata = DatasetMetadata(
        schema_version=dataset.schema_version,
        snapshot_id=dataset.snapshot_id,
        train_json_sha256=dataset.train_json_sha256,
        split_seed=dataset.split_seed,
        dev_ratio=dataset.dev_ratio,
        excluded_conflict_ids=list(dataset.excluded_conflict_ids),
        total_labeled=len(scoped_entries),
        ambiguous_count=ambiguous_count,
        active_count=len(active_items),
    )
    return LoadedDataset(metadata=metadata, items=active_items)


def load_verified_dataset(
    labels_path: Path,
    techqa_dir: Path,
    *,
    split: Literal["dev", "test", "all"] = "all",
    manifest: Manifest | None = None,
) -> list[EvalItem]:
    """Wczytuje zamrożony plik etykiet i zwraca aktywne pytania (bez `ambiguous`)."""
    return load_verified_dataset_with_metadata(
        labels_path, techqa_dir, split=split, manifest=manifest
    ).items
