<!-- PLAN-REVIEW-REPORT -->

# Plan Review: Kopiowanie odpowiedzi z cytatami i wąskie okno

- **Plan**: context/changes/answer-copy-and-narrow-window/plan.md
- **Mode**: Deep
- **Date**: 2026-11-25
- **Verdict**: SOUND
- **Findings**: 0 critical, 1 warning, 2 observations

## Verdicts

| Dimension             | Verdict |
| --------------------- | ------- |
| End-State Alignment   | PASS    |
| Lean Execution        | PASS    |
| Architectural Fitness | WARNING |
| Blind Spots           | WARNING |
| Plan Completeness     | WARNING |

## Grounding

9/9 paths ✓, 5/5 symbols ✓ (vitest 5.1.2 peer vite ^8 ✓, AnswerClaim.citation required ✓, en.ts typed by pl keys ✓), brief↔plan ✓

## Findings

### F1 — Arkusz zamyka się i otwiera przy przejściu lista ↔ fragment

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Architectural Fitness
- **Location**: Faza 3 — Obudowa panelu / Panele w obudowie
- **Detail**: Plan umieszcza PanelFrame wewnątrz EvidencePanel i CheckedChunksPanel. W `answer.tsx` przy abstencji `panel` przełącza się między CheckedChunksPanel a EvidencePanel, czyli między różnymi komponentami. Każde przejście odmontowuje jeden `<dialog>` (close) i montuje drugi (showModal). Skutki: mignięcie tła, chwilowy powrót fokusu za arkusz i skok arkusza przy 390 px. Między cytatami problemu nie ma.
- **Fix A ⭐ Recommended**: Jedna obudowa w AssistantFrame. AssistantFrame owija `panel` w PanelFrame (`panelVariant`, `onDismissPanel` przekazuje trasa), a panele zwracają samą treść.
  - Strength: Dialog żyje przez całe otwarcie, także przy przejściu lista ↔ fragment; jedno miejsce decyzji aside/arkusz.
  - Tradeoff: Trasa przekazuje wariant i onDismiss zależny od stanu.
  - Confidence: HIGH — answer.tsx już wybiera panel i ma funkcje zamykania.
  - Blind spot: Aria-label obudowy musi zmieniać się z treścią.
- **Fix B**: Zostaw obudowę w panelach i zaakceptuj mignięcie.
  - Strength: Mniej zmian w trasie i AssistantFrame.
  - Tradeoff: Widoczne przeładowanie arkusza i skok fokusu przy otwarciu fragmentu.
  - Confidence: MED — skala mignięcia zależy od przeglądarki.
  - Blind spot: Nie sprawdzone na urządzeniu dotykowym.
- **Decision**: FIXED (Fix A)

### F2 — Przewijanie tła pod arkuszem

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Faza 3 — Obudowa panelu; kryterium 3.5
- **Detail**: Kryterium 3.5 wymaga, by tło nie przewijało się pod arkuszem, ale Contract nie mówi jak. Dotykowe przewinięcie do końca treści arkusza może przejść na stronę.
- **Fix**: Dodać do Contract `overscroll-behavior: contain` na przewijanej treści arkusza i szuflady.
- **Decision**: FIXED

### F3 — Niejednoznaczne ogłaszanie wyniku kopiowania

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Faza 1 — Przycisk „Kopiuj odpowiedź z cytatami”
- **Detail**: Contract mówi „aria-live albo w etykiecie przycisku”. Zmiana tekstu przycisku zwykle nie jest ogłaszana przez czytniki ekranu.
- **Fix**: Tekst przycisku się zmienia (jak CodeBlock), a wynik dodatkowo trafia do ukrytego elementu `role="status"`.
- **Decision**: FIXED
