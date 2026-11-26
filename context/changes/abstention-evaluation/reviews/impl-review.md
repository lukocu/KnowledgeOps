<!-- IMPL-REVIEW-REPORT -->

# Implementation Review: Ewaluacja abstencji i odpowiedzi (S-06)

- **Plan**: context/changes/abstention-evaluation/plan.md
- **Scope**: Full plan (Phases 1–5 of 5)
- **Reviewed phases**: 1, 2, 3, 4, 5
- **Date**: 2026-11-26
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 4 warnings, 3 observations

## Verdicts

| Dimension           | Verdict |
| ------------------- | ------- |
| Plan Adherence      | WARNING |
| Scope Discipline    | WARNING |
| Safety & Quality    | WARNING |
| Architecture        | PASS    |
| Pattern Consistency | WARNING |
| Success Criteria    | PASS    |

## Findings

### F1 — Raw TechQA question excerpts committed in `eval-report.md`

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Scope Discipline
- **Location**: backend/app/evals/report.py:68-75, context/changes/abstention-evaluation/eval-report.md:60-69, 73-82
- **Detail**: `_question_preview()` embeds up to 120 characters of raw TechQA question text into each error bullet. As a result, 20 verbatim TechQA question excerpts were committed in `eval-report.md`, conflicting with `plan.md:40` ("Bez kopiowania treści TechQA do repozytorium") and `plan.md:243` ("Przykłady błędów (ID pytań + diagnoza)").
- **Fix**: Remove raw question previews from default `render_markdown_report()` output (keep `question_id`, `split`, and diagnostic stats, or gate behind `include_question_previews: bool = False`) and regenerate `context/changes/abstention-evaluation/eval-report.md`.
- **Decision**: FIXED

### F2 — Silent item drop risk in Langfuse sync and experiment collection

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: backend/app/evals/langfuse_eval.py:155, 251-269
- **Detail**: `ensure_and_sync_dataset()` silently filters out any `selected_ids` absent from `by_id` (line 155), and `run_langfuse_experiment()` silently omits input items absent from `executions_by_question_id` (lines 265–269), which could cause `summary.n_total < len(items)` without flagging `failed` items.
- **Fix**: Raise `RuntimeError` if any `selected_ids` are missing after sync, and synthesize a `failed` `EvalItemExecution` for any input item missing from `executions_by_question_id`.
  - Strength: Guarantees every dataset item is accounted for in metrics and `n_failed` even if Langfuse pagination or task execution skips an item.
  - Tradeoff: Slightly stricter failure behavior on partial Langfuse sync lag.
  - Confidence: HIGH — directly prevents silent denominator shrinkage.
  - Blind spot: None significant.
- **Decision**: FIXED

### F3 — `eval-prepare-abstention` silently overwrites manually edited label template

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: backend/app/evals/prepare.py:287-291
- **Detail**: `prepare_abstention_candidates()` unconditionally overwrites `abstention-labels-template.json`. Re-running `eval-prepare-abstention` on the same `--out-dir` silently destroys in-progress manual labels.
- **Fix**: Refuse to overwrite an existing `abstention-labels-template.json` unless an explicit `overwrite=True` / `--force` flag is provided.
- **Decision**: FIXED

### F4 — Phase 5 human verification gates executed by AI agent on operator instruction

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Plan Adherence
- **Location**: backend/evals/abstention-dataset.json, context/changes/abstention-evaluation/eval-report.md:118
- **Detail**: `plan.md:350, 353, 356` required human verification of the `is_impossible` candidates and the 20-item judge audit sample. At the operator's explicit instruction, both were performed by an AI agent and transparently disclosed via `[AI review]` / `[AI blind review]` notes and `eval-report.md:118`.
- **Fix A ⭐ Recommended**: Accept the current baseline as transparently documented and spot-check a human subsample before tuning prompts or making product decisions.
  - Strength: Preserves the reproducible Langfuse baseline (`43bf66331ca84f95`) while keeping the methodological caveat explicit in `eval-report.md`.
  - Tradeoff: Until a human spot-check is done, human-in-the-loop independence is not fully satisfied.
  - Confidence: HIGH — aligns with operator's explicit instruction and transparency rules.
  - Blind spot: Potential correlation between AI reviewer and LLM judge on subtle edge cases.
- **Fix B**: Perform full human review of `is_impossible` labels and the 20-item blind audit sheet, then re-freeze and regenerate `eval-report.md`.
  - Strength: Strictly satisfies every human-gate clause of the original plan.
  - Tradeoff: Requires significant manual operator effort (~1–2 hours).
  - Confidence: HIGH — straightforward operational rerun using existing CLI commands.
  - Blind spot: None significant.
- **Decision**: ACCEPTED (Fix A — documented baseline accepted; human spot-check before prompt tuning)

### F5 — Minor CLI and Markdown robustness edge cases

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: backend/app/evals/sampling.py:385-386, 397, 404, backend/app/evals/runner.py:214, backend/app/cli.py:257-291
- **Detail**: `sampling.py` wraps `claim.code`/`chunk_text` in triple backticks without escaping inner backticks and prefixes only the first line of multi-line `claim.quote`; `confirm_eval_run()` does not catch `EOFError` on closed stdin; `cli.py` validates `--limit`/`--concurrency` after prompting for cost confirmation.
- **Fix**: Use a dynamic fence longer than any inner backtick run, prefix every line of `claim.quote` with `> `, catch `EOFError` in `confirm_eval_run()`, and validate `--limit`/`--concurrency` before prompting.
- **Decision**: SKIPPED

### F6 — Duplicated citation-support aggregation logic

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: backend/app/evals/agreement.py:77-101, backend/app/evals/metrics.py:198-224
- **Detail**: `_judge_citation_answer_label()` in `agreement.py` duplicates claim-index deduplication and answer-level support logic from `_evaluate_citation_support()` in `metrics.py`.
- **Fix**: Extract and reuse a shared helper from `metrics.py` so the two definitions cannot drift.
- **Decision**: FIXED

### F7 — Token usage/cost not captured in local `EvalItemExecution` artifact

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: backend/app/evals/runner.py:241-352
- **Detail**: `plan.md:47` (`Implementation Approach`) mentioned capturing tokens/cost if returned by the provider, whereas per-phase contracts (`plan.md:173-180, 226-233`) omitted those fields. Tokens/cost are currently captured passively in Langfuse Cloud traces only.
- **Fix**: Leave as-is (captured in Langfuse Cloud) or optionally add an `usage` field to `EvalItemExecution` in a follow-up.
- **Decision**: FIXED
