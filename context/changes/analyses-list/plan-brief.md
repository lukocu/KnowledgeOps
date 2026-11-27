# Lista analiz i decyzji (`analyses-list`, S-10) — Plan Brief

> Full plan: `context/changes/analyses-list/plan.md`
> Research: `context/changes/analyses-list/research.md`

## What & Why

Wdrażamy ekran `5` (**„Analizy i decyzje”**, `/analizy`; `US-04`, `FR-010`), który daje redaktorowi wiedzy jedno miejsce do przeglądania i filtrowania wspólnych przykładów demo oraz analiz z własnej sesji — z wyraźnym rozdzieleniem oceny systemu od decyzji człowieka. Zamyka to główną pętlę audytu zapoczątkowaną w S-08 i S-09.

## Starting Point

Tabele `audits`, `audit_claims`, `audit_claim_decisions` i `audit_events` już wspierają `is_demo = true` oraz izolację decyzji per `session_hash`. Brakuje jednak endpointu `GET /api/audits`, seedera przykładów demo, obsługi nowego odwiedzającego bez ciasteczka `kops_session` na przykładach demo oraz widoku `/analizy` i 3. pozycji w `NavRail`.

## Desired End State

Nowy odwiedzający bez logowania i bez ciasteczka otwiera `/analizy`, od razu widzi 4 przykłady z pilotażu (`SIM-P08`, `SIM-P11`, `SIM-P04`, `SIM-P01`) oraz komunikat pustej sesji z CTA do `/audyt`, może otworzyć dowolny przykład z działającym panelem dowodu i zapisać własną decyzję (odizolowaną od innych sesji). Lista pozwala filtrować po wyszukiwarce, decyzji, ocenie systemu i źródle, rozróżnia stan pustej sesji od braku wyników filtra i działa czytelnie w oknie 390 px.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Dane demo (`is_demo = true`) | 4 sprawy z pilotażu (`SIM-P08`, `SIM-P11`, `SIM-P04`, `SIM-P01`) przez CLI `import-demo-audits` | Pokrywa wszystkie 4 werdykty i 3 dokumenty TechQA, rozwiązując `chunk_id` i cytaty z lokalnej bazy bez commitowania surowego tekstu TechQA. | Plan |
| Pochodzenie i stany puste | Filtr źródła (`Wszystkie` / `Przykłady demo` / `Twoje`) + chip `Demo` + pasek pustej sesji | Oba stany puste z `US-04` są zawsze osiągalne i rozróżnialne, mimo że przykłady demo są zawsze obecne. | Plan |
| Sortowanie i „Ostatnia zmiana” | `(pending + in_progress)` → `(queued/running)` → `(saved/failed)`, potem `GREATEST(audits.updated_at, MAX(decyzji sesji))` | Sprawy w trakcie rozstrzygania nie spadają pod zapisane, a decyzja na demo odświeża czas wyłącznie w bieżącej sesji. | Plan |
| Stopka o retencji sesji | Uczciwa kopia bez deklarowania automatycznego usuwania (TTL) | Zgodne z PRD Guardrails — backend nie ma jeszcze mechanizmu TTL. | Plan |
| Trasa i nawigacja | `/analizy` jako 3. pozycja `NavRail`, `end: true` na `/audyt`, powrót z `/audyt/:id` do `/analizy` | Zapewnia spójny przepływ lista → szczegóły → powrót do listy i czyste podświetlenie aktywnej zakładki. | Plan |
| Dostęp bez ciasteczka do demo | `OptionalSessionDep` na `GET /api/audits{,/{id}}`, `SessionDep` na `PUT .../decision` | Eliminuje `404` dla nowych odwiedzających otwierających lub rozstrzygających przykład demo. | Research |

## Scope

**In scope:** migracja częściowego indeksu `is_demo`, `OptionalSessionDep`, `list_audits_for_session`, idempotentny CLI `import-demo-audits`, `GET /api/audits` + poprawki sesji w `api/audits.py`, regeneracja OpenAPI/TS, aktualizacja lokalnego `docs/przeplyw-danych.md`, ekran `/analizy` (desktop + karty 390 px), `NavRail`, breadcrumbs, PL/EN i18n, testy DB/HTTP/Vitest.

**Out of scope:** logowanie/konta, TTL i automatyczne usuwanie sesji, usuwanie/edycja analiz, paginacja serwerowa, eksport danych, commitowanie surowego tekstu TechQA.

## Architecture / Approach

Backend łączy wspólne rekordy `is_demo = true` z rekordami bieżącej sesji w jednym zapytaniu SQL (`list_audits_for_session`), agregując podział tez i decyzje bieżącej sesji oraz licząc `last_activity_at` per sesja. Seeder `import-demo-audits` działa na wzór S-07 (`pg_advisory_xact_lock`, deterministyczne `uuid5`, `ON CONFLICT DO UPDATE`), dzięki czemu ponowny seed nie kasuje zapisanych przez użytkowników decyzji. Frontend reużywa pigułek wydzielonych do `AuditBadges.tsx`, synchronizuje filtry z URL i przełącza tabelę 5-kolumnową na układ kart poniżej `md` (768 px).

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Indeks DB, sesje i `store.py` | Migracja `0006`, `OptionalSessionDep`, `list_audits_for_session` + testy DB | Spójność `decision_status` i `last_activity_at` per sesja na rekordach demo |
| 2. Seeder `import-demo-audits` | Autorski JSON 4 spraw + idempotentny CLI z rozwiązywaniem cytatów z TechQA | Zachowanie zapisanych decyzji użytkowników przy ponownym seedzie (`ON CONFLICT`) |
| 3. API `GET /api/audits` i kontrakt | Endpoint listy, poprawki sesyjne szczegółów/decyzji, testy HTTP, OpenAPI/TS | Brak przecieków między sesjami i obsługa braku ciasteczka na demo |
| 4. Frontend `/analizy` i 390 px | Trasa `/analizy`, `NavRail`, filtry, tabela + karty 390 px, oba stany puste, PL/EN | Czytelność 390 px (brak makiety `S5N`) i wyraźne rozróżnienie obu stanów pustych |

**Prerequisites:** ukończone S-08/S-09, działająca lokalna baza ParadeDB z zaimportowaną migawką TechQA (`import-techqa`).
**Estimated effort:** ~1–2 sesje (4 fazy przyrostowe).

## Open Risks & Assumptions

- Przykłady demo wymagają uruchomienia `import-demo-audits` po `import-techqa`; jeśli baza nie ma migawki TechQA, seeder zgłasza czytelny błąd zamiast generować fałszywe cytaty.
- Retencja danych sesji (PRD Open Question 10) pozostaje otwarta przed publicznym wdrożeniem demo — w MVP komunikujemy uczciwie izolację sesji bez obietnicy automatycznego usuwania.

## Success Criteria (Summary)

- Nowy odwiedzający bez ciasteczka widzi na `/analizy` 4 przykłady demo, otwiera dowolny z działającym panelem dowodu i zapisuje własną decyzję odizolowaną od innych sesji.
- Analiza utworzona w jednej sesji nie pojawia się w drugiej sesji, a oba stany puste (pusta sesja vs brak wyników filtra) są osiągalne i różne.
- Wszystkie kontrole automatyczne backendu i frontendu są zielone, a ekran `/analizy` jest czytelny przy `390 px` w obu językach i rolach.
