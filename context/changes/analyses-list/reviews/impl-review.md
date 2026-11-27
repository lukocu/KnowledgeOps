<!-- IMPL-REVIEW-REPORT -->

# Implementation Review: Lista analiz i decyzji (`analyses-list`, S-10)

- **Plan**: `context/changes/analyses-list/plan.md`
- **Scope**: Full plan (Phases 1–4 of 4; commits `0aeed0f`..`6cc5cdd`)
- **Reviewed phases**: 1, 2, 3, 4
- **Date**: 2026-11-27
- **Verdict**: APPROVED
- **Findings**: 0 critical, 1 warning, 3 observations

## Verdicts

| Dimension           | Verdict |
| ------------------- | ------- |
| Plan Adherence      | PASS    |
| Scope Discipline    | PASS    |
| Safety & Quality    | WARNING |
| Architecture        | PASS    |
| Pattern Consistency | PASS    |
| Success Criteria    | PASS    |

## Findings

### F1 — `pending_count` includes `queued`/`running` audits not yet ready for editor decision

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `backend/app/auditing/store.py:744-746`
- **Detail**: `compute_decision_status` maps `queued`/`running` audits to `"pending"`, and `list_audits_for_session` sums all rows with `decision_status == "pending"` into `pending_count` regardless of `item.status`. Meanwhile `next_pending_audit_id` (`store.py:754-757`) only considers `_priority_group(item) == 0` (`status == "completed"` and `decision_status in ("pending", "in_progress")`), and `PUT .../decision` rejects non-completed audits with `409 Conflict`. With 1 completed pending audit and 1 running audit, the banner says „2 analizy czekają na Twoją decyzję”, even though only 1 can accept a decision; similarly, with 0 completed pending audits and 1 running audit, the summary line still shows „1 czeka” while the banner is hidden.
- **Fix**: Count only completed audits in `pending_count` (`item.status == "completed" and item.decision_status == "pending"`) in `backend/app/auditing/store.py:744-746` and add a regression assertion in `backend/tests/test_audits_list_store.py`.
- **Decision**: FIXED

### F2 — Debounced search-to-URL sync drops trailing spaces mid-query

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `frontend/app/components/audit/AnalysesListView.tsx:101-104`
- **Detail**: When a user types `"WebSphere "` right before the 250 ms debounce fires, `setSearchParams` writes the trimmed value `"WebSphere"` to `urlQ`. On the next render, `if (urlQ !== prevUrlQ)` unconditionally runs `setSearchInput(urlQ)`, overwriting `"WebSphere "` with `"WebSphere"` and dropping the trailing space while the user is typing a multi-word query.
- **Fix**: Guard `setSearchInput(urlQ)` inside `if (urlQ !== prevUrlQ)` with `if (searchInput.trim() !== urlQ)` so URL-to-input sync only runs when the trimmed values actually diverge (e.g., Clear filters or browser Back/Forward).
- **Decision**: FIXED

### F3 — Query parameter `q` on `GET /api/audits` has no `max_length` bound

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `backend/app/api/audits.py:448`
- **Detail**: `q: str | None = None` has no upper length bound, unlike body inputs in `CreateAuditRequest` and `SaveClaimDecisionRequest`. Filtering is done safely in Python via substring match (no SQL injection risk), but bounding `q` keeps input validation consistent across the router.
- **Fix**: Change parameter annotation to `q: Annotated[str | None, Query(max_length=200)] = None` and regenerate `backend/openapi.json` and `frontend/app/api/schema.d.ts`.
- **Decision**: FIXED

### F4 — Unused `AuditSessionDep` alias remains in `backend/app/session.py`

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Architecture
- **Location**: `backend/app/session.py:78-80`
- **Detail**: After `GET /api/audits/{audit_id}` switched to `OptionalSessionDep` and `PUT .../decision` switched to `SessionDep`, `AuditSessionDep` has no remaining references in the codebase.
- **Fix**: Remove the unused `AuditSessionDep` alias from `backend/app/session.py`.
- **Decision**: FIXED
