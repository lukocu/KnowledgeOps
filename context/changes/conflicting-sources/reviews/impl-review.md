<!-- IMPL-REVIEW-REPORT -->

# Implementation Review: S-07: Sprzeczne źródła i różne zalecenia (`conflicting-sources`)

- **Plan**: context/changes/conflicting-sources/plan.md
- **Scope**: Full plan (Phases 1–4 of 4)
- **Reviewed phases**: 1, 2, 3, 4
- **Date**: 2026-11-26
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 2 warnings, 4 observations

## Verdicts

| Dimension           | Verdict |
| ------------------- | ------- |
| Plan Adherence      | PASS    |
| Scope Discipline    | PASS    |
| Safety & Quality    | WARNING |
| Architecture        | PASS    |
| Pattern Consistency | WARNING |
| Success Criteria    | PASS    |

## Findings

### F1 — Synthetic checked chunks fail with 404 on "Pokaż cały dokument" in abstention view

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: frontend/app/routes/answer.tsx:287-295, frontend/app/components/assistant/EvidencePanel.tsx:155-160
- **Detail**: When `include_synthetic=True` and the graph abstains (`AbstainedResult`), `checked_chunks` can contain chunks from `synthetic@v1`. Because `CheckedChunk` has no `snapshot_id` field, `answer.tsx:289` hardcodes `snapshotId: record.snapshot_id` (the TechQA snapshot). Although `GET /api/evidence` returns the real `snapshot_id` in `EvidenceWindow`, `EvidencePanel.tsx:155-160` does not forward `result.snapshot_id` via `onMeta`. Clicking "Pokaż cały dokument" on a synthetic checked chunk therefore requests `GET /api/documents?snapshot_id=techqa@...&doc_id=SYN-KB-...` and fails with 404, while the metadata line displays the TechQA snapshot hash.
- **Fix A ⭐ Recommended**: Forward `snapshotId: result.snapshot_id` through `onMeta` in `EvidencePanel.tsx` and use `loadedMeta?.snapshotId ?? target.snapshotId` for `DocumentView` and the metadata line.
  - Strength: Fixes both the 404 and the metadata display immediately in the frontend with zero backend schema, DB JSONB, or OpenAPI churn.
  - Tradeoff: `DocumentView` depends on `WindowView` having loaded `GET /api/evidence` first (which is always the initial tab when opening a checked chunk).
  - Confidence: HIGH — `EvidenceWindow.snapshot_id` is already returned by `/api/evidence` and typed in `schema.d.ts`.
  - Blind spot: None significant.
- **Fix B**: Add `snapshot_id: str | None = None` to `CheckedChunk` in `backend/app/answering/schemas.py`, populate it in `nodes.py`, regenerate `openapi.json` and `schema.d.ts`, and pass `chunk.snapshot_id ?? record.snapshot_id` in `answer.tsx:289`.
  - Strength: Makes `CheckedChunk` self-describing at the API contract level, matching `Citation` and `ConflictSide`.
  - Tradeoff: Larger touch surface (backend schema + nodes + OpenAPI export + TS types + frontend) and still needs fallback for legacy DB rows.
  - Confidence: HIGH — follows the exact pattern already used for `Citation.snapshot_id`.
  - Blind spot: Requires checking existing `test_answers.py` fixtures that construct `CheckedChunk`.
- **Decision**: FIXED (Fix A)

### F2 — Mismatch between `resolve_conflict_type` behavior for `None` vs `None` metadata and report limitation note

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: backend/app/answering/nodes.py:247-266, backend/app/evals/conflicts.py:1386-1391
- **Detail**: `resolve_conflict_type()` checks `_norm_scope_attr(side_a_doc.product_version) != _norm_scope_attr(side_b_doc.product_version)` (and similarly for `audience`). When both sides are TechQA docs (`product_version=None` and `audience=None` on both), `None != None` is `False`, so the guard allows `"contradiction"` whenever the LLM outputs `scope_relation="same_scope"`. However, the report limitation note in `backend/app/evals/conflicts.py:1388-1391` (and `eval-report.md`) states that `resolve_conflict_type()` degrades pairs with unknown (`nieustaloną`) version to `"different_recommendations"`.
- **Fix A ⭐ Recommended**: Update the limitation note in `backend/app/evals/conflicts.py:1386-1391` and `context/changes/conflicting-sources/eval-report.md` to accurately state that `resolve_conflict_type()` degrades pairs when metadata is mismatched or specified on only one side (while TechQA-vs-TechQA pairs rely on the LLM's `scope_relation` check from body text).
  - Strength: Aligns documentation with the plan contract (`plan.md:213`) and preserves the ability to detect genuine same-scope contradictions between two TechQA documents in the future.
  - Tradeoff: Two TechQA docs with `NULL` metadata rely on `detect_conflict.md` prompt discipline rather than a Python-level block.
  - Confidence: HIGH — matches `plan.md:213` and existing unit tests in `test_conflict_nodes.py`.
  - Blind spot: None significant.
- **Fix B**: Tighten `resolve_conflict_type()` in `backend/app/answering/nodes.py:258-266` to require non-null `product_version` on both sides before allowing `"contradiction"`.
  - Strength: Guarantees deterministically that unknown version metadata can never produce `"contradiction"`.
  - Tradeoff: Prevents any TechQA-vs-TechQA pair from ever being classified as `"contradiction"` even when both bodies explicitly state the same product version; requires updating `test_conflict_nodes.py`.
  - Confidence: MEDIUM — depends on whether TechQA-vs-TechQA contradictions should be allowed at runtime.
  - Blind spot: Haven't verified whether any `test_conflict_nodes.py` case explicitly asserts `None` vs `None` -> `"contradiction"`.
- **Decision**: FIXED (Fix A)

### F3 — Unchecked `signal.aborted` before `onMeta` callback in `EvidencePanel`

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: frontend/app/components/assistant/EvidencePanel.tsx:154-160
- **Detail**: Inside `WindowView`'s `load` callback, `onMeta(...)` (`setLoadedMeta`) runs immediately after `await getEvidence(...)` without checking `if (!signal.aborted)`. Rapid `before`/`after` changes could briefly apply stale metadata from an aborted request.
- **Fix**: Wrap `onMeta(...)` in `if (!signal.aborted) { onMeta(...); }`.
- **Decision**: FIXED

### F4 — Unstripped comparison strings in `compose_conflict_result`

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: backend/app/answering/nodes.py:417-425
- **Detail**: `summary` and `refine_hint` are `.strip()`ped before fallback checks, but `conflict_check.comparison` fields (`value_label`, `side_a_value`, `side_b_value`) are passed raw. Whitespace-only LLM output would render `"Zalecana wartość (   )"` or blank table cells in `ConflictView.tsx`.
- **Fix**: Strip `value_label`, `side_a_value`, and `side_b_value` in `compose_conflict_result`, treating empty `value_label` as `None` and falling back empty side values to `claim.text`.
- **Decision**: FIXED

### F5 — Private helper imports across eval modules

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: backend/app/evals/conflicts.py:38,41
- **Detail**: `conflicts.py` imports underscore-prefixed private functions `_percentile` (from `app.evals.metrics`) and `_extract_token_usage` (from `app.evals.runner`), coupling to internal symbols of sibling modules.
- **Fix**: Expose `percentile` in `app.evals.metrics` and `extract_token_usage` in `app.evals.runner` as public functions and import those in `conflicts.py`.
- **Decision**: FIXED

### F6 — `RunSummary` in S-06 eval metrics does not track `n_conflicting` separately

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: backend/app/evals/metrics.py:86-110,337-342, backend/app/evals/runner.py:136-140
- **Detail**: `runner.py` now records `outcome="conflicting"` without crashing, and `metrics.py:337` counts it in `n_evaluated`, but `RunSummary` only exposes `n_answered` and `n_abstained` (so `n_answered + n_abstained < n_evaluated` if a TechQA-only run ever hits a conflict), and `estimate_llm_calls` still uses `3 * n_total` instead of `4 * n_total` as the upper bound.
- **Fix**: Add `n_conflicting: int = 0` to `RunSummary` (backward-compatible default) and update `estimate_llm_calls` upper bound for the optional `detect_conflict` call.
- **Decision**: FIXED
