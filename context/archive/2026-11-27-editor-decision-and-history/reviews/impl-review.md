<!-- IMPL-REVIEW-REPORT -->

# Implementation Review: Decyzja redaktora i historia analizy (`editor-decision-and-history`)

- **Plan**: context/changes/editor-decision-and-history/plan.md
- **Scope**: Full plan (Phases 1–3 of 3)
- **Reviewed phases**: 1, 2, 3
- **Date**: 2026-11-27
- **Verdict**: APPROVED
- **Findings**: 0 critical, 2 warnings, 3 observations

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

### F1 — Unmounting `ClaimDecisionPanel` drops unsaved draft and aborts in-flight save on desktop

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: frontend/app/components/audit/AuditResultView.tsx:311-442, frontend/app/components/audit/ClaimDecisionPanel.tsx:54-61,71-76
- **Detail**: On desktop (`>= 1280px`), opening `EvidencePanel` or `CaseContextPanel` replaces and unmounts `ClaimDecisionPanel`. Because form state (`selectedCategory`, `justification`) and `abortRef` live inside `ClaimDecisionPanel`, inspecting a document or case context while drafting a justification discards unsaved text and aborts any in-flight `PUT` request on unmount.
- **Fix A ⭐ Recommended**: Keep `ClaimDecisionPanel` mounted (visually hidden with `hidden` and `aria-hidden`) while `EvidencePanel` or `CaseContextPanel` temporarily occupies the desktop right slot.
  - Strength: Preserves both unsaved form state and in-flight save completion with a small localized change in `AuditResultView.tsx`.
  - Tradeoff: Keeps one extra lightweight DOM subtree mounted while inspecting evidence.
  - Confidence: HIGH — `ClaimDecisionPanel` is keyed by `selectedClaim.claim_id` and has no heavy subscriptions.
  - Blind spot: None significant.
- **Fix B**: Lift unsaved drafts (`draftsByClaimId`) into `AuditResultView` and keep the `PUT` request outside the panel's unmount cleanup.
  - Strength: Also preserves unsaved drafts across claim switches and mobile `<dialog>` close/reopen.
  - Tradeoff: Larger refactor of form state ownership and dirty-state synchronization.
  - Confidence: MEDIUM — requires careful sync when `audit` updates from the server.
  - Blind spot: Edge cases when reloading or switching role mid-draft.
- **Decision**: Fixed via Fix A

### F2 — Dead `isEditableTarget` branch in `Escape` key handler

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: frontend/app/components/audit/AuditResultView.tsx:247-263
- **Detail**: Inside `onKeyDown`, `if (event.key !== "Escape") { if (isEditableTarget(event.target)) return; return; }` is a dead guard, and `if (isXl && isEditableTarget(event.target)) return;` never triggers on `xl` when `evidence`/`context` is open (no editable input is mounted there) while leaving `!isXl` `<textarea>` unprotected if the intent was to block `Escape` inside textareas.
- **Fix**: Remove the dead `isEditableTarget` check inside `event.key !== "Escape"` and simplify the `Escape` handler so its desktop vs. mobile behavior is explicit and unambiguous.
- **Decision**: Fixed

### F3 — No HTTP-level API test for cross-session `is_demo = true` isolation

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: backend/tests/test_audits_decisions_api.py
- **Detail**: Cross-session isolation of decisions and human events on `is_demo = true` audits is verified at the store layer (`test_audit_store_decisions.py`), but not end-to-end over HTTP with two distinct session cookies.
- **Fix**: Add a DB HTTP test in `backend/tests/test_audits_decisions_api.py` verifying two sessions on an `is_demo = true` audit only see their own decisions and `decision_saved` events.
- **Decision**: Fixed

### F4 — Stale `activePanel.kind === "decision"` across viewport resize

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: frontend/app/components/audit/AuditResultView.tsx:407-442
- **Detail**: Opening the `3N-D` sheet below `1280px`, resizing to `>= 1280px`, and resizing back below `1280px` automatically re-opens the sheet because `activePanel` is not cleared when `isXl` becomes `true`.
- **Fix**: Clear `activePanel` (or ignore `kind === "decision"`) when transitioning into `isXl === true`.
- **Decision**: Fixed

### F5 — Unused `ASIDE_CLASS.decision` branch in `PanelFrame.tsx`

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: frontend/app/components/assistant/PanelFrame.tsx:13-14
- **Detail**: `PanelFrame.tsx` defines `ASIDE_CLASS.decision`, but `AuditResultView.tsx` only mounts `PanelFrame` with `variant="decision"` when `!isXl`, rendering a separate `<aside>` on `xl`.
- **Fix**: Either render `PanelFrame` on `xl` as well for consistency or document in a comment that desktop renders the persistent `<aside>` directly.
- **Decision**: Fixed
