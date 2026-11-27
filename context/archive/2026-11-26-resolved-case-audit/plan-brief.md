# S-08: Analiza rozwiązanej sprawy (`resolved-case-audit`) — Plan Brief

> Full plan: `context/changes/resolved-case-audit/plan.md`
> Research: `context/changes/resolved-case-audit/research.md`

## What & Why

Wdrażamy drugi główny przepływ KnowledgeOps Assistant: ręczne przekazanie rozwiązanej sprawy do audytu, wieloetapową analizę w tle porównującą każdą tezę z notatki z całą migawką bazy wiedzy oraz prezentację oceny systemu z dosłownymi dowodami. Dzięki temu konsultant i redaktor dostają konkretne, zweryfikowane sygnały (poparta / sprzeczna / niewystarczające dowody) bez traktowania notatki jako prawdy i bez mylenia braku dowodu z luką lub sprzecznością.

## Starting Point

Repozytorium ma działający przepływ pytań z cytatami, abstencją i sprzecznościami (`S-02`, `S-07`), anonimową sesję `kops_session`, wielozestawowy BM25 w ParadeDB (`techqa@v1` + `synthetic@v1`), endpointy `/api/evidence` i `/api/documents` oraz reużywalny `EvidencePanel`/`PanelFrame`. Brakuje tabel audytu, mechanizmu zadań w tle w `lifespan`, grafu audytu oraz ekranów `2`, `2P`, `3` i `3N`.

## Desired End State

Użytkownik wkleja opis sprawy i notatkę na `/audyt` (ekran `2`), obserwuje rzeczywisty postęp analizy na `/audyt/:id` (ekran `2P`, przetrwa odświeżenie strony), a po zakończeniu przegląda ocenę całej notatki, podświetlone tezy `T1`/`T2`, `Kontekst sprawy` (`FR-007`) w `PanelFrame` oraz dowody w `EvidencePanel` na desktopie (`>= 1280 px`) i w wąskim oknie (`390 px`), w języku PL i EN.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Utrwalanie stanu w tle | Dedykowane tabele `0004_audits.sql` + `asyncio.Task` w `lifespan` | Unika dodawania `langgraph-checkpoint-postgres` (AGENTS.md), używa jednej puli DB i przygotowuje schemat pod S-09/S-10. | Plan |
| Zakres korpusu | Dziedziczy `settings.include_synthetic` (jak S-07) | Zapewnia spójność między Asystentem a Audytem i jawnie oznacza trafienia z `synthetic@v1` w szczegółach analizy. | Plan |
| Restart i błąd pojedynczej tezy | Restart → `failed`; błąd 1 tezy → `insufficient` z notatką | Zapobiega pętlom kosztów po restarcie i nie marnuje poprawnie ocenionych pozostałych tez. | Plan |
| Rozwinięty `Kontekst sprawy` (`FR-007`) | Panel boczny / arkusz `PanelFrame` (wspólny slot z `EvidencePanel`) | Pasuje do wzorca strzałki `›` na `S3`, nie wydłuża listy tez i działa spójnie przy `390 px`. | Plan |
| Prezentacja tezy (decyzja #3) | Oba: dosłowny `source_excerpt` w notatce + zwięzła teza na liście | Odwzorowuje 1:1 makietę `S3.dc.html` przy pełnym zakotwiczeniu w oryginale przez `locate_quote()`. | Plan |
| Wejście z ekranu 1C | Subtelny link `/audyt` w `AbstentionView` obok `NavRail` | Realizuje naturalne przejście z abstencji do audytu (i komentarz w `AbstentionView.tsx:13`). | Plan |
| Ocena całej notatki | Deterministyczna funkcja Pythona (bez LLM) | Gwarantuje 100% zgodności z regułą `Business Logic` z `prd.md:231` dla 4 kategorii notatki. | Research |

## Scope

**In scope:** migracja `0004_audits.sql` (gotowa pod S-09/S-10), graf audytu LangGraph (`extract → retrieve → verify → aggregate`), wykonanie w tle w `lifespan`, API `POST/GET /api/audits`, eksport OpenAPI/TS, ekrany `2`, `2P`, `3`, `3N` (PL/EN), `Kontekst sprawy`, `Jak powstała ta analiza` (`FR-020`), link w `AbstentionView`, aktualizacja `docs/przeplyw-danych.md`, ręczne sprawdzenie 12 przypadków pilotażu.

**Out of scope:** panel decyzji redaktora, „Sugestia systemu”, arkusz `S3N-D` i `Historia` (`S-09`); lista analiz i przykłady demo (`S-10`); metryki/macierz pomyłek audytu (`S-11`); `langgraph-checkpoint-postgres`; logowanie, integracje ticketowe, edycja dokumentacji, wyszukiwanie w internecie.

## Architecture / Approach

`POST /api/audits` zapisuje wiersz `audits` w ramach sesji `kops_session`, uruchamia `asyncio.Task` w rejestrze `app.state.audit_tasks` i zwraca `202`. Graf LangGraph wykonuje `extract` (FR-007 + tezy z `locate_quote()`), równoległe `retrieve` (BM25 po aktywnych `chunk_set_ids` pod `Semaphore`) i `verify` (3-stanowy werdykt + weryfikacja cytatu + strażnik zakresu), a na końcu deterministyczną agregację notatki — aktualizując postęp w Postgresie po każdym etapie bez blokowania połączeń DB podczas wywołań LLM. Frontend na `/audyt/:id` odpytuje `GET /api/audits/:id` (ekran `2P`) aż do wyniku (`3`/`3N`).

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Migracja `0004_audits.sql` i fundamenty backendu | Tabele `audits`/`audit_claims`, `store.py`, uogólnienie `session.py` i `observability.py` | Utrzymanie kompatybilności wstecznej testów `answers` |
| 2. Graf audytu LangGraph i reguły | Schematy, prompty `*.md`, węzły `extract→retrieve→verify→aggregate`, testy jednostkowe | Jakość wyodrębniania dosłownych spanów i rozróżnianie braku dowodu od sprzeczności |
| 3. Wykonanie w tle, API `/api/audits` i OpenAPI/TS | `AuditTaskManager` w `lifespan`, endpointy `POST`/`GET`, testy API, `schema.d.ts` | Wycieki zadań w tle lub blokowanie puli `max_size=5` przy współbieżności |
| 4. Frontend (`2`, `2P`, `3`, `3N`), i18n i pilotaż | Ekrany audytu, `CaseContextPanel`, tokeny/ikony, testy Vitest, 12 przypadków pilotażu | Układ 2-kolumnowy z otwartym `PanelFrame` przy `1280 px` i bez przewijania na `390 px` |

**Prerequisites:** Działający ParadeDB (`docker compose up -d db`), zaimportowany korpus TechQA (i nakładka `synthetic@v1`), skonfigurowany `CHAT_MODEL` w `.env`.
**Estimated effort:** ~2–3 sesje przez 4 fazy.

## Open Risks & Assumptions

- Pilotaż `docs/pilotaz-audytu-techqa.md` powstał w kontrakcie jednego dokumentu, a S-08 przeszukuje całą migawkę — ręczna weryfikacja 12 przypadków może ujawnić dodatkowe trafienia spoza wskazanego dokumentu (to oczekiwane, nie traktujemy wyniku jako pomiaru S-11).
- Przy notatkach z wieloma zdaniami model może zwrócić niedokładny `source_excerpt`; `locate_quote()` obsługuje normalizację białych znaków, a brak dopasowania bezpiecznie pomija inline-highlight bez utraty tezy na liście.

## Success Criteria (Summary)

- Konsultant przekazuje sprawę na `/audyt`, odświeżenie strony w trakcie analizy nie gubi postępu, a wynik pokazuje osobne oceny tez i deterministyczną ocenę całej notatki z cytatami i `Kontekstem sprawy`.
- Wszystkie kontrole backendu (`ruff`, `mypy`, `pytest`), frontendu (`lint`, `format:check`, `typecheck`, `vitest`, `build`) oraz synchronizacja `openapi.json`/`schema.d.ts` przechodzą na zielono.
- 12 przypadków z `docs/pilotaz-audytu-techqa.md` przechodzi przez graf bez błędów, a `docs/przeplyw-danych.md` zawiera wpis dla przepływu audytu.
