<!-- IMPL-REVIEW-REPORT -->

# Implementation Review: S-08: Analiza rozwiązanej sprawy (`resolved-case-audit`)

- **Plan**: context/changes/resolved-case-audit/plan.md
- **Scope**: Full plan (Phase 1–4 of 4)
- **Reviewed phases**: 1, 2, 3, 4
- **Date**: 2026-11-27
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical 5 warnings 4 observations

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

### F1 — Raw exception strings exposed in API responses and UI

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: backend/app/auditing/runner.py:197-206
- **Detail**: Uncaught exceptions in `AuditTaskManager._run_audit` (`runner.py:203`) and per-claim LLM errors (`graph.py:371`) are persisted as `f"{type(exc).__name__}: {exc}"`, returned verbatim by `GET /api/audits/{audit_id}` (`audits.py:140, 160`), and `audit.error` is rendered directly in `frontend/app/routes/audit-detail.tsx:166-170`. Exceptions from `psycopg`, `openai`, or `httpx` can leak internal hostnames, SQL fragments, or upstream payloads in a public demo. Sibling `backend/app/api/answers.py:56-61, 124-128` keeps raw exception text in logs/internal state and returns safe classified messages to clients.
- **Fix**: Classify uncaught audit and per-claim exceptions into safe user-facing messages/codes for `audits.error` and `audit_claims.error` (keeping full stack traces in server logs via `logger.warning(..., exc_info=True)`).
  - Strength: Matches `backend/app/api/answers.py` and prevents leaking internal infrastructure details in a public demo without schema changes.
  - Tradeoff: Debugging a failed audit from the UI alone relies on server logs / Langfuse trace instead of raw exception text in the browser.
  - Confidence: HIGH — identical error-handling boundary is already used in `answers.py`.
  - Blind spot: None significant.
- **Decision**: FIXED

### F2 — `EvidencePanel` labels contradicted and insufficient audit evidence as "Supports claim"

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: frontend/app/components/audit/AuditResultView.tsx:262-284
- **Detail**: `AuditResultView` passes `target.claims` without `sideLabel` into `EvidencePanel`. `frontend/app/components/assistant/EvidencePanel.tsx:349-351` unconditionally renders `t("evidence.supports", { n: claim.index })` ("Wspiera tezę N" / "Supports claim N") whenever `sideLabel` is absent — even when the audit claim verdict is `contradicted` or `insufficient` (`supports_claim === false`, closest passage). This contradicts the verdict shown in the main column.
- **Fix**: Add an optional `claimLabel?: string` field to `EvidenceTarget` (or per-claim entry) and pass the truthful audit relation from `AuditResultView` ("Wspiera tezę T1" / "Sprzeczny z tezą T1" / "Najbliższy fragment · T1").
- **Decision**: FIXED

### F3 — Deterministic scope guard allows `contradicted` when `scope_relation == "unclear"`

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: backend/app/auditing/rules.py:209
- **Detail**: `resolve_claim_verdict` only degrades `raw.verdict == "contradicted"` when `raw.scope_relation == "different_scope"`. If the model emits `verdict="contradicted"` with `scope_relation="unclear"`, it passes through as `"contradicted"`. Both `backend/app/auditing/prompts/verify_claim.md:9-14` and the sibling scope guard in `backend/app/answering/nodes.py:258` (`if scope_relation != "same_scope":`) require `same_scope` to allow a contradiction.
- **Fix**: Change `backend/app/auditing/rules.py:209` to `if raw.verdict == "contradicted" and raw.scope_relation != "same_scope":` and add a unit test in `test_audit_rules.py`.
- **Decision**: FIXED

### F4 — Concurrent `update_audit_progress` calls can regress `claims_done`

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: backend/app/auditing/graph.py:249-272
- **Detail**: Inside `retrieve` (`graph.py:249-272`) and `verify` (`graph.py:302-403`), up to `audit_claim_concurrency` coroutines increment `done_count` and call `await self._report(...)` concurrently. Each `_on_progress` call acquires its own DB connection (`runner.py:124-135`) and runs `SET claims_done = COALESCE(%s, claims_done)`, so an earlier increment (`claims_done=1`) can commit after a later one (`claims_done=2`), regressing the progress counter.
- **Fix**: Serialize `done_count += 1` and `await self._report(...)` with an `asyncio.Lock` per stage (or wrap `_on_progress` in `runner.py` with an `asyncio.Lock`).
- **Decision**: FIXED

### F5 — Unbounded concurrent background audits against `max_size=5` DB pool

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: backend/app/auditing/runner.py:56-93
- **Detail**: `AuditTaskManager.schedule` spawns an `asyncio.Task` per `POST /api/audits` with no global concurrency cap. During `retrieve`, each active audit can hold up to `audit_claim_concurrency=3` DB connections plus progress writes, while `backend/app/db.py:25` configures `max_size=5`. Two or more concurrent audits competing with 1.5 s polling requests can exhaust the pool and trigger `PoolTimeout` (`503` on GET/POST and failed audits).
- **Fix**: Guard `_run_audit` execution in `AuditTaskManager` with a global `asyncio.Semaphore(2)` (or `1` configurable via settings) so extra submissions stay cleanly in `queued` state until a worker slot opens.
  - Strength: Protects the 5-connection DB pool and polling responsiveness under concurrent submissions while preserving the existing `queued` status semantics on screen `2P`.
  - Tradeoff: Concurrent users wait sequentially in `queued` state; `audit_deadline_s` should start after acquiring the semaphore so queued time does not eat into execution budget.
  - Confidence: HIGH — small self-contained change in `AuditTaskManager`.
  - Blind spot: None significant.
- **Decision**: FIXED

### F6 — `is_demo` records unreachable without a session cookie

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: backend/app/api/audits.py:256-265
- **Detail**: `store.get_audit_for_session` accepts `session_hash: str | None` so `is_demo = true` audits can be read without a cookie, but `GET /api/audits/{audit_id}` uses `AuditSessionDep` (`make_require_session`), which returns `404` before reaching the store when no cookie is present. Safe (fail-closed) for S-08 since no demo audits exist yet, but will need an optional-session dependency in S-10.
- **Fix**: Keep fail-closed for S-08 and switch `GET /api/audits/{audit_id}` to an optional-session dependency in S-10 when demo audits are added.
- **Decision**: ACCEPTED — fail-closed for S-08; deferred to S-10 when demo audits are introduced

### F7 — `createAudit` request is not aborted on unmount

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: frontend/app/routes/audit-new.tsx:89-94
- **Detail**: Unlike sibling `frontend/app/components/assistant/useAsk.ts:24-26`, `AuditNewRoute` calls `createAudit(...)` without an `AbortController` signal. Navigating away while `POST /api/audits` is in flight can still trigger `navigate("/audyt/...")` when the request resolves.
- **Fix**: Track an `AbortController` ref in `AuditNewRoute`, pass `signal` to `createAudit`, and abort it in a `useEffect` unmount cleanup.
- **Decision**: FIXED

### F8 — Clickable claim `<span>` in resolution note lacks keyboard semantics

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: frontend/app/components/audit/AuditResultView.tsx:381-395
- **Detail**: Highlighted claim spans in the resolution note attach `onClick` to a `<span>` without `role="button"`, `tabIndex={0}`, or `onKeyDown` (Enter/Space). The claim list below provides keyboard-accessible `<button>` controls, so functionality is reachable, but interactive spans should also be keyboard-operable.
- **Fix**: Add `role="button"`, `tabIndex={0}`, and `onKeyDown` (handling `Enter` and ` `) to the highlighted claim spans in `AuditResultView.tsx:381-395`.
- **Decision**: FIXED

### F9 — `resolve_active_chunk_set_ids` queried per claim in `retrieve`

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: backend/app/auditing/graph.py:103-108
- **Detail**: `make_pool_retriever` calls `resolve_active_chunk_set_ids` on every claim (up to 12 times per audit) even though the active chunk sets are constant for the audit run and already resolved in `POST /api/audits`.
- **Fix**: Resolve `chunk_set_ids` once per audit run in `retrieve` (or pass the resolved `chunk_set_ids` from `AuditState` into the retriever).
- **Decision**: FIXED
