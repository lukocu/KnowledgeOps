# Decyzja redaktora i historia analizy (`editor-decision-and-history`) — Plan Brief

> Full plan: `context/changes/editor-decision-and-history/plan.md`
> Research: `context/changes/editor-decision-and-history/research.md`

## What & Why

W ramach etapu **S-09** (`US-02`, `FR-009`, `FR-021`, `FR-011`) dodajemy możliwość zapisu i edycji decyzji redaktora dla każdej tezy z analizy rozwiązanego zgłoszenia (z wymaganym uzasadnieniem i 4 kategoriami bez wyboru domyślnego) oraz rzeczywistą historię zdarzeń analizy. Dzięki temu przepływ audytu zamyka się pełną pętlą human-in-the-loop, zachowując twardą granicę MVP: ocena systemu jest oddzielona od decyzji człowieka, a zapis decyzji nigdy nie zmienia ani nie publikuje dokumentacji.

## Starting Point

Po wdrożeniu S-08 (`resolved-case-audit`, commit `4d47785`) działają tabele `audits` i `audit_claims` (`0004_audits.sql`), endpointy `POST /api/audits` i `GET /api/audits/{audit_id}` oraz ekran wyniku `AuditResultView` z ocenami tez, panelem dowodu i kontekstem sprawy. Brakuje zapisu decyzji per teza, wyliczanego statusu decyzji, tabeli zdarzeń historii oraz prawego panelu decyzji (`3`), dolnego paska z arkuszem (`3N`/`3N-D`) i sekcji `Historia`.

## Desired End State

W roli Redaktora użytkownik zapisuje i może edytować decyzję z uzasadnieniem dla każdej tezy (także popartej) — w stałym prawym panelu `340 px` na desktopie (`>= 1280 px`) lub w arkuszu `3N-D` otwieranym z dolnego paska CTA na węższych oknach (`390 px`, zero przewijania w poziomie). Po rozstrzygnięciu wszystkich tez analiza dostaje status „Zapisana”, a zwinięta sekcja `Historia` pokazuje wyłącznie rzeczywiste zdarzenia (utworzenie, ocena systemu, zapis/aktualizacja decyzji człowieka).

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Zachowanie roli `consultant` | Tylko do odczytu + przycisk „Przełącz na rolę Redaktor” | Zgodne z tabelą ról w PRD przy jawnym komunikacie, że przełącznik nie jest kontrolą dostępu. | Plan |
| „Sugestia systemu” z makiety `S3` | Pominięta | Unika podpowiadania wyboru redaktorowi (nudging) i pozostaje wierne PRD. | Plan |
| Edycja zapisanej decyzji | Dozwolona (`UPSERT` + `decision_updated`) | Pozwala skorygować decyzję po sprawdzeniu kolejnych dowodów przy pełnej historii zmian. | Plan |
| Klucz unikalności pod S-10 (`is_demo`) | `UNIQUE (claim_id, session_hash)` już w `0005` | Zapewnia izolację decyzji odwiedzających na przyszłych przykładach demo bez destrukcyjnej migracji w S-10. | Plan |
| Układ paneli i breakpoint `3N-D` | Zamiana prawego panelu od `1280 px`, pasek + `3N-D` poniżej `1280 px` | Zapewnia brak ścisku przy `1280 px` i `1440 px` oraz spójny arkusz modalny przy `390 px`. | Plan |
| `0` tez i backfill historii | `decision_status = not_applicable` dla 0 tez + SQL backfill w `0005` | Zapobiega błędnemu statusowi „zapisana” bez tez i daje spójną historię audytom z S-08. | Plan |
| Źródło historii `FR-021` | Dedykowana tabela SQL `audit_events` (nie checkpointy LangGraph) | S-08 nie używa checkpointów LangGraph, a zapisy w `store.py` gwarantują atomowość z cyklem życia audytu. | Research |

## Scope

**In scope:** Migracja `0005` (`audit_claim_decisions`, `audit_events`, backfill), atomowe zdarzenia i `upsert_claim_decision` w `store.py`, `PUT /api/audits/{audit_id}/claims/{claim_id}/decision`, rozszerzenie `GET /api/audits/{audit_id}`, synchronizacja `openapi.json` i `schema.d.ts`, panel decyzji (`3`), pasek CTA + arkusz `3N-D`, sekcja `Historia`, wskaźniki na tezach, PL/EN i testy, aktualizacja lokalnego `docs/przeplyw-danych.md`.

**Out of scope:** Edycja/publikacja dokumentacji, wywołania LLM lub Langfuse przy zapisie decyzji, linia „Sugestia systemu”, etykieta „szkic”, lista analiz `/analizy` i odczyt `is_demo` bez ciasteczka (S-10), ewaluacja audytu (S-11), ciemny motyw (`FR-022`).

## Architecture / Approach

Zapis decyzji omija całkowicie LangGraph, LLM i Langfuse: `PUT` wykonuje krótką transakcję SQL w ParadeDB (`UPSERT` w `audit_claim_decisions` + `INSERT` w `audit_events`) i zwraca pełny, autorytatywny `AuditDetailResponse` z wyliczonym `decision_status`. Na froncie `ClaimDecisionPanel` jest współdzielony między desktopowym `<aside>` (`>= 1280 px`, tymczasowo zastępowanym przez dowód/kontekst) a natywnym arkuszem `<dialog>.showModal()` z `PanelFrame` (`< 1280 px`).

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Migracja `0005` i `store.py` | Tabele `audit_claim_decisions` i `audit_events` z backfill, atomowe zdarzenia i `upsert_claim_decision` + testy DB | Naruszenie niezmienności `0001`–`0004` lub błędne filtrowanie `session_hash` |
| 2. API i kontrakt OpenAPI/TS | Endpoint `PUT decision`, rozszerzony `GET` (`decision_status`, `history`), testy API, `openapi.json` + `schema.d.ts` | Rozjazd kontraktu OpenAPI/TS lub niespójny `decision_status` dla 0 tez |
| 3. Frontend (`3`, `3N`, `3N-D`, `Historia`) | Panel decyzji, tryb roli `consultant`, pasek + arkusz `3N-D`, `Historia`, i18n PL/EN, testy Vitest i ręczna weryfikacja UI | Konflikt `Escape`/fokusu z `<textarea>` lub poziome przewijanie na `390 px` |

**Prerequisites:** Ukończony S-08 (`4d47785`), działający ParadeDB (`docker compose up -d db`), wyeksportowane `.env` dla testów DB i Docker do uruchomienia `mypy` na Windows.
**Estimated effort:** ~1–2 sesje robocze w 3 fazach.

## Open Risks & Assumptions

- Przełącznik ról działa wyłącznie po stronie przeglądarki (`localStorage`) jako etykieta UX, nie mechanizm bezpieczeństwa; backend przyjmuje `role_label` z żądania i waliduje domenę wartości (`editor` | `consultant`).
- W S-09 odczyt `GET /api/audits/{id}` pozostaje fail-closed na `AuditSessionDep`; udostępnienie publicznych przykładów `is_demo = true` bez ciasteczka wejdzie w S-10 bez zmian w kluczach `0005`.

## Success Criteria (Summary)

- Zapis bez wybranej kategorii lub z pustym uzasadnieniem jest blokowany w UI i odrzucany (`422`) przez API; żadna z 4 kategorii nie jest wybrana domyślnie.
- Po zapisaniu decyzji dla wszystkich tez analiza ma status „Zapisana”, historia pokazuje wyłącznie rzeczywiste zdarzenia z rozróżnieniem systemu i człowieka, a dokumentacja pozostaje nienaruszona.
- Cały przepływ działa w `1440 px`, `1280 px` oraz `390 px` (arkusz `3N-D`, zero przewijania w poziomie) w językach PL i EN.
