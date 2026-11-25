<!-- IMPL-REVIEW-REPORT -->

# Implementation Review: Kopiowanie odpowiedzi z cytatami i wąskie okno

- **Plan**: context/changes/answer-copy-and-narrow-window/plan.md
- **Scope**: Full plan
- **Reviewed phases**: 1, 2, 3
- **Date**: 2026-11-25
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 3 warnings, 2 observations

## Verdicts

| Dimension           | Verdict |
| ------------------- | ------- |
| Plan Adherence      | PASS    |
| Scope Discipline    | PASS    |
| Safety & Quality    | WARNING |
| Architecture        | PASS    |
| Pattern Consistency | PASS    |
| Success Criteria    | PASS    |

Success Criteria: npm test (6/6), lint, format:check, typecheck, build — all PASS. Manual rows 1.4–3.7 checked in the browser during implementation; multi-citation prev/next was not exercised (both test answers had one citation).

## Findings

### F1 — Escape/cancel w arkuszu zależy wyłącznie od słuchacza trasy

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: frontend/app/components/assistant/PanelFrame.tsx:81
- **Detail**: `onCancel` tylko `preventDefault()`. Jeśli `cancel` przyjdzie bez `keydown` (np. systemowy gest Wstecz na Androidzie), nic nie zamknie arkusza, a natywne zamknięcie jest zablokowane. NavDrawer w tej sytuacji wywołuje `onClose`.
- **Fix**: Wywołaj `onDismiss()` w `onCancel` po `preventDefault()`; trasa i tak sprawdza `defaultPrevented`, a funkcje zamykania są idempotentne. Plan (Critical Implementation Details) zakładał obsługę Escape tylko w trasie, więc to świadome odejście od planu.
  - Strength: Pokrywa ścieżkę bez klawiatury, spójne z NavDrawer.
  - Tradeoff: Przy Escape z klawiatury `onDismiss` mógłby zadziałać dwa razy (kolejność fragment → lista); wymaga ręcznego sprawdzenia.
  - Confidence: MED — kolejność zamykania w answer.tsx nie była testowana z tą zmianą.
  - Blind spot: Zachowanie na prawdziwym urządzeniu dotykowym.
- **Decision**: FIXED (onCancel wywołuje onDismiss; Escape chunk → lista → zamknięcie sprawdzone przy 390 px)

### F2 — Echo `close` po sprzątaniu może drugi raz wywołać onDismiss

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: frontend/app/components/assistant/PanelFrame.tsx:73 i :88; NavRail.tsx (onClose)
- **Detail**: Sprzątanie wywołuje `dialog.close()`, co kolejkuje asynchroniczne zdarzenie `close`. Po odmontowaniu `dialog.open` jest `false`, więc strażnik przepuszcza, a React może jeszcze wywołać `onDismiss` na odłączonym węźle. Dla arkusza oznacza to ponowne `closeCitation`/`closeChunk`/`closeChecked` i drugi `focusSoon`. Ręczne testy nie pokazały objawu, więc skutek niepewny.
- **Fix**: Ustaw ref `closingByCleanup` w sprzątaniu i pomiń `onClose`, gdy jest ustawiony.
- **Decision**: FIXED (ref closingByCleanup w PanelFrame i NavDrawer)

### F3 — `aria-controls` wskazuje na nieistniejący element

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: frontend/app/components/shell/AppHeader.tsx (przycisk Menu); NavRail.tsx (`NavDrawer` zwraca null, gdy zamknięty)
- **Detail**: Szuflada jest odmontowana, gdy zamknięta, więc `aria-controls={menuId}` wskazuje na id, którego nie ma.
- **Fix**: `aria-controls={menuOpen ? menuId : undefined}` (plan wymagał `aria-controls`, więc to doprecyzowanie planu).
- **Decision**: FIXED (aria-controls tylko przy otwartej szufladzie)

### F4 — Timer resetu kopiowania nie restartuje się przy ponownym kliknięciu

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: frontend/app/components/assistant/useCopy.ts:12
- **Detail**: Timer zależy od `state`. Drugie kliknięcie przy stanie `copied` nie restartuje 2 s i nie ogłasza wyniku ponownie.
- **Fix**: Trzymaj timer w refie i restartuj przy każdym `copy`.
- **Decision**: FIXED (timer w refie, restart przy każdym copy)

### F5 — Ta sama etykieta na dialogu szuflady i na wewnętrznym `<nav>`

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: frontend/app/components/shell/NavRail.tsx (~190)
- **Detail**: Czytnik ogłasza „Menu, dialog”, a potem „Menu, nawigacja”. Kosmetyka.
- **Fix**: Daj dialogowi etykietę `nav.menu`.
- **Decision**: FIXED (dialog ma etykietę nav.menu)
