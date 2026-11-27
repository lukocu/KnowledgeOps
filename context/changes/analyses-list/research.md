---
date: 2026-11-27T16:07:27+01:00
researcher: Antigravity
git_commit: 76b3c32d1c0dbfac45a30c3eae091f36809fb651
branch: main
repository: KnowledgeOps
topic: "S-10 (analyses-list): Lista analiz i decyzji — backend, dane demo, frontend i makieta ekranu 5"
tags: [research, codebase, analyses-list, s-10, audits, demo-seed, mockup-s5]
status: complete
last_updated: 2026-11-27
last_updated_by: Antigravity
---

# Research: S-10 (`analyses-list`) — Lista analiz i decyzji

**Date**: 2026-11-27T16:07:27+01:00
**Researcher**: Antigravity
**Git Commit**: 76b3c32d1c0dbfac45a30c3eae091f36809fb651
**Branch**: main
**Repository**: KnowledgeOps

## Research Question

Jak wdrożyć etap **S-10 (`analyses-list`, ekran `5` — „Analizy i decyzje”; `US-04`, `FR-010`)** na istniejących fundamentach S-07/S-08/S-09:
1. Jakie tabele, indeksy, endpointy i mechanizmy sesji istnieją dziś w backendzie i co trzeba dodać dla `GET /api/audits` oraz przykładów `is_demo = true`?
2. Jak dokładnie wygląda makieta ekranu `5` (`design/mockups/canvas/S5.dc.html`) i jakie trasy, komponenty oraz tokeny CSS można ponownie użyć we frontendzie (w tym przy 390 px)?
3. Jakie decyzje z archiwów S-07/S-08/S-09 oraz jakie przypadki z pilotażu (`docs/pilotaz-audytu-techqa.md`) kształtują seedowanie wspólnych przykładów syntetycznych?

## Summary

- **Schemat bazy jest prawie gotowy pod S-10:** tabele `audits` (`is_demo`, `session_hash`, `case_ref`, `note_verdict`, `status`, `claims_total`, `case_context`, `updated_at`), `audit_claims`, `audit_claim_decisions` (`UNIQUE (claim_id, session_hash)` + indeks `(audit_id, session_hash)`) oraz `audit_events` (`actor_type = 'system'` vs `'human'`) już izolują decyzje i historię per sesja na rekordach `is_demo = true` (`backend/migrations/0004_audits.sql:5-63`, `backend/migrations/0005_audit_decisions_and_history.sql:4-55`). Brakuje jedynie częściowego indeksu na `audits` dla `is_demo = true` oraz samego zapytania listującego w `store.py` i endpointu `GET /api/audits`.
- **Krytyczna luka sesyjna dla odwiedzających bez ciasteczka `kops_session`:** `store.get_audit_for_session` już przyjmuje `session_hash: str | None` i zwraca rekordy `is_demo = true` bez ciasteczka (`backend/app/auditing/store.py:472-541`), ale oba istniejące endpointy (`GET /api/audits/{audit_id}` i `PUT /api/audits/{audit_id}/claims/{claim_id}/decision`) używają dziś `AuditSessionDep`, który odrzuca brak ciasteczka kodem `404` przed wejściem do `store` (`backend/app/api/audits.py:378-404`, `backend/app/session.py:51-71`). Dla S-10 potrzebna jest opcjonalna zależność sesji (`OptionalSessionDep -> str | None`) dla `GET /api/audits` i `GET /api/audits/{audit_id}` oraz przełączenie `PUT .../decision` na `SessionDep` (nadanie ciasteczka przy pierwszym zapisie decyzji na przykładzie demo). Ponadto `AuditDetailResponse` nie zwraca jeszcze pola `is_demo` (`backend/app/api/audits.py:146-171`).
- **Brak seedera przykładów demo:** w `backend/app/cli.py` nie ma jeszcze komendy seedującej rekordy `is_demo = true`. Wzorcem idempotentnego ładowania danych syntetycznych w repo jest `import-synthetic-conflicts` z S-07 (`backend/app/synthetic/importer.py:117-233`, `backend/app/synthetic/documents.json`): JSON w git bez surowego tekstu TechQA, transakcja z `pg_advisory_xact_lock` i raportem `state_sha256`. Pilotaż (`docs/pilotaz-audytu-techqa.md:13-80`) i makieta `S5.dc.html:26` wskazują 4 kategorie werdyktów reprezentowane np. przez `P01` (`full`), `P04` (`partial`), `P08` (`contradiction`), `P11` (`insufficient`).
- **Frontend i makieta `S5.dc.html`:** brakuje jeszcze trasy listy analiz (np. `/analizy`), trzeciej pozycji w `NavRail.tsx:28-45` oraz podpięcia breadcrumbs w `AuditResultView.tsx:462-467` (obecnie prowadzi do `/audyt`). Paleta i ikony z `S5.dc.html` są w większości gotowe w `app.css` i `Icon.tsx`; brakuje eksportu `NoteVerdictPill` (dziś prywatny w `AuditResultView.tsx:61-88`), ikony lupy i listy w `Icon.tsx` oraz responsywnego widoku kartowego dla 390 px (makieta `S5N` nie istnieje — `design/mockups/README.md:56`).

---

## Detailed Findings

### 1. Backend — baza danych, `store.py`, API i sesje

- **Tabela `audits`** (`backend/migrations/0004_audits.sql:5-39`):
  - Kluczowe kolumny dla listy: `id uuid PRIMARY KEY`, `session_hash text NOT NULL`, `is_demo boolean NOT NULL DEFAULT false`, `case_ref text`, `case_description text NOT NULL`, `resolution_note text NOT NULL`, `status text NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed'))`, `stage text NOT NULL`, `claims_total integer NOT NULL DEFAULT 0`, `claims_done integer NOT NULL DEFAULT 0`, `note_verdict text CHECK (note_verdict IN ('full', 'partial', 'contradiction', 'insufficient'))`, `case_context jsonb`, `created_at timestamptz`, `updated_at timestamptz`, `completed_at timestamptz`.
  - **Brak kolumny `title`:** w `0004_audits.sql:5-39` nie ma dedykowanego pola tytułu/skrótu problemu; opis w kolumnie „Problem” na liście można wyprowadzić z `case_context->>'problem'` (gdy dostępne po ekstrakcji) z fallbackiem do `case_description` (lub wprowadzić osobną funkcję pomocniczą w backendzie).
  - **Indeksy na `audits`:** w zbadanych migracjach (`0001`–`0005`) jedynym indeksem na `audits` jest `audits_session_created_idx ON audits (session_hash, created_at DESC)` (`backend/migrations/0004_audits.sql:62`). Nie istnieje jeszcze indeks dla `is_demo = true` (np. częściowy indeks `WHERE is_demo = true`).
  - **Brak FK do `snapshots`/`documents`/`chunks`** (`backend/migrations/0004_audits.sql:1-4`): ponowny import TechQA nie usuwa rekordów audytu ani przykładów demo.
- **Tabele `audit_claims`, `audit_claim_decisions` i `audit_events`:**
  - `audit_claims` przechowuje dowody w kolumnach `jsonb` (`evidence`, `checked_docs`) oraz `verdict IN ('supported', 'contradicted', 'insufficient')` (`backend/migrations/0004_audits.sql:41-60`); nie istnieje osobna tabela `audit_claim_evidence`.
  - `audit_claim_decisions` ma ograniczenie `UNIQUE (claim_id, session_hash)` oraz indeks `audit_claim_decisions_audit_session_idx (audit_id, session_hash)` (`backend/migrations/0005_audit_decisions_and_history.sql:21,24-25`). Pozwala to w jednym zapytaniu SQL policzyć `decisions_count` (oraz podział werdyktów tez `supported`/`contradicted`/`insufficient` z `audit_claims`) per sesja z pełną izolacją między sesjami na wierszach `is_demo = true`.
  - `audit_events` wymusza przez `CHECK`, że zdarzenia `actor_type = 'system'` mają `session_hash IS NULL`, a `actor_type = 'human'` mają `session_hash IS NOT NULL` (`backend/migrations/0005_audit_decisions_and_history.sql:48-51`).
- **Wyliczanie `decision_status` i „ostatniej zmiany”:**
  - `DecisionStatus` w `backend/app/auditing/store.py:40` przyjmuje dokładnie 4 wartości: `"pending"`, `"in_progress"`, `"saved"`, `"not_applicable"`.
  - Funkcja `compute_decision_status(status, claims_total, decisions_count)` (`backend/app/api/audits.py:173-187`) zwraca: `"pending"` dla `status IN ('queued', 'running')`, `"not_applicable"` dla `status == 'failed'` lub `claims_total <= 0`, `"pending"` dla `decisions_count <= 0`, `"in_progress"` dla `0 < decisions_count < claims_total`, `"saved"` dla `decisions_count >= claims_total`.
  - Dla wiersza demo (`is_demo = true`) kolumna `audits.updated_at` jest wspólna dla wszystkich sesji, więc „ostatnia zmiana” widoczna dla bieżącej sesji może uwzględniać `GREATEST(a.updated_at, COALESCE(MAX(d.updated_at), a.updated_at))` dla decyzji bieżącej sesji, aby zapis decyzji na przykładzie demo odświeżał znacznik czasu tylko dla tej sesji.
- **Istniejące endpointy audytu i obsługa sesji:**
  - Router `backend/app/api/audits.py:49` (prefiks `/api`, podpięty w `backend/app/main.py:60`) udostępnia obecnie dokładnie 3 endpointy: `POST /api/audits` (`:289-370`, `SessionDep`), `GET /api/audits/{audit_id}` (`:373-387`, `AuditSessionDep`) oraz `PUT /api/audits/{audit_id}/claims/{claim_id}/decision` (`:390-428`, `AuditSessionDep`).
  - `backend/app/session.py:15-71` definiuje ciasteczko `kops_session` (`path="/api"`, `httponly=True`, `samesite="lax"`, brak `max_age`/`expires`) oraz dwie zależności: `SessionDep` (tworzy nowe ciasteczko, gdy brak) i `AuditSessionDep` (`make_require_session`, zwraca `404`, gdy brak ciasteczka). Brak zależności opcjonalnej (`OptionalSessionDep -> str | None`).
  - **Konsekwencja dla S-10:** w aktualnym kodzie nowy odwiedzający (bez ciasteczka `kops_session`) nie może ani odczytać szczegółów przykładu demo przez `GET /api/audits/{audit_id}` (`404` z `AuditSessionDep`), ani zapisać na nim decyzji przez `PUT .../decision` (`404` z `AuditSessionDep`), mimo że warstwa `store.py` (`get_audit_for_session` `:472-541`, `upsert_claim_decision` `:409-414`) już obsługuje `is_demo = true`.
  - `AuditDetailResponse` (`backend/app/api/audits.py:146-171`) nie zawiera obecnie pola `is_demo`, mimo że `StoredAudit.is_demo` istnieje (`backend/app/auditing/store.py:123`).
- **Retencja sesji:** w zbadanych plikach `backend/app/` i `backend/migrations/` nie istnieje żaden mechanizm TTL ani automatycznego usuwania danych sesji; jedynym mechanizmem czyszczenia jest `fail_orphaned_audits` przy starcie FastAPI (`backend/app/main.py:36-49`, `backend/app/auditing/store.py:359-385`).

### 2. Makieta ekranu 5 (`S5.dc.html`) i obecny frontend

- **Układ i nagłówek `design/mockups/canvas/S5.dc.html:26`:**
  - Tytuł strony: `<h1>` „Analizy i decyzje” + chip `DEMO · dane z pilotażu` (z ikoną info i tooltipem o publicznym demo i braku kontroli dostępu) + podtytuł „Analizy rozwiązanych spraw i decyzje redaktora, osobno dla każdej tezy.”.
  - Baner akcji (gdy są analizy oczekujące): niebieska kropka `#2f5fc4`, tekst „N analizy czekają na Twoją decyzję.” oraz przycisk primary „Zacznij od <ref>” przechodzący do pierwszej oczekującej analizy.
  - Pasek filtrów (`h:34px`, tło `#f2f0ea`): pole wyszukiwania („Szukaj po identyfikatorze lub problemie”), filtr „Decyzja” (`Wszystkie`), filtr „Ocena systemu” (`Wszystkie`), a po prawej licznik zbiorczy: „4 przykłady · 2 Twoje (ta sesja) · 2 czekają · 1 w toku · 3 zapisane”.
- **Tabela (`S5.dc.html:26`):**
  - Pojedyncza tabela z 5 kolumnami: `Sprawa` (`100px`, monospace), `Problem` (`auto`, 2-line clamp), `Ocena systemu` (`280px`: pigułka werdyktu notatki + linia podziału tez, np. „1 poparta · 1 bez wystarczających dowodów”; dla `running` znak „—”), `Decyzja redaktora` (`210px`: status z ikoną/kropką/spinnerem + podlinia „X z Y tez rozstrzygnięte”), `Ostatnia zmiana` (`130px`, zwarty znacznik czasu + strzałka w prawo).
  - Stopka tabeli: po lewej reguła sortowania („Najpierw analizy czekające na decyzję, potem ostatnia zmiana”), po prawej nota o oddzieleniu oceny systemu od decyzji człowieka i izolacji sesji. **Uwaga do treści stopki:** makieta mówi „a po ograniczonym czasie są usuwane”, natomiast w kodzie backendu nie ma jeszcze automatycznego TTL (PRD Open Question 10, `docs/przeplyw-danych.md:45-47`) — tekst w UI nie powinien deklarować nieistniejącego jeszcze automatycznego usuwania, albo należy to jawnie uzgodnić w planie.
  - W makiecie nie ma zakładkowego podziału na „Przykłady” i „Twoje” ani odznaki pochodzenia w wierszu; podział jest w liczniku paska filtrów i stopce (`design/mockups/README.md:69` oznacza ten podział jako przykładowy).
  - Makieta nie pokazuje wiersza w stanie `in_progress` (częściowe decyzje, np. `1 z 2`) ani `failed` / `queued` / `not_applicable` — te stany istnieją w modelu backendu i wymagają jawnej reprezentacji słowem i ikoną.
- **Oba stany puste (`S5.dc.html:26`):**
  - **Stan pusty (brak własnych analiz w sesji / pusta lista):** „Nie masz jeszcze analiz w tej sesji. Przykłady demo są dostępne zawsze.” + CTA „Przekaż rozwiązaną sprawę do audytu” → `/audyt`.
  - **Brak wyników filtra:** „Żadna analiza nie pasuje do filtrów.” + CTA „Wyczyść filtry”.
- **Obecny kod frontendu:**
  - `frontend/app/routes.ts:8-15` definiuje 4 trasy (`/`, `/odpowiedz/:id`, `/audyt`, `/audyt/:id`) — brak trasy dla listy analiz (konwencja polskich ścieżek wskazuje na `/analizy`, zgodne z planami S-08/S-09).
  - `frontend/app/components/shell/NavRail.tsx:28-45` celowo ma dziś tylko 2 pozycje (komentarz w linii 28: „Dwie pozycje do S-10: nie pokazujemy linku do listy analiz przed jej implementacją”). Pozycja `"/audyt"` nie ma `end: true`, więc `/audyt/:id` podświetla dziś „Przekaż sprawę do audytu” — w S-10 warto rozważyć `end: true` na `/audyt` (lub mapowanie aktywności), żeby nawigacja między `/audyt`, `/analizy` i `/audyt/:id` była spójna.
  - `frontend/app/components/audit/AuditResultView.tsx:462-467` ma breadcrumb prowadzący obecnie do `/audyt` (`audit.detail.newAudit`), który w S-10 można przełączyć lub uzupełnić o powrót do `/analizy`.
  - `NoteVerdictPill` (`AuditResultView.tsx:61-88`), `ClaimVerdictPill` (`:91-131`) i `DecisionStatusPill` (`:159-200`) są nieeksportowane — do reużycia na liście wystarczy wydzielić je (np. do `AuditBadges.tsx`).
  - `frontend/app/components/assistant/Icon.tsx` ma już wszystkie 4 ikony werdyktów (`SupportedIcon`, `PartialIcon`, `ContradictionIcon`, `InsufficientIcon`), `CheckIcon`, `ChevronIcon`, `StepStatusIcon` (ze spinnerem z S5) i `InfoIcon`; brakuje ikony lupy (`SearchIcon`) i ikony listy dla `NavRail`.
  - Role (`frontend/app/session/role.tsx:12-44`): brak blokowania tras dla roli `consultant`; ekran 5 powinien być dostępny w obu rolach bez udawania kontroli dostępu (`FR-011`).
  - Responsywność 390 px: `frontend/app/app.css:4-47` zawiera już niemal wszystkie tokeny kolorów S5 (brak tylko koloru hover wiersza `#f6f5f1`). Brak makiety `S5N` (`design/mockups/README.md:56`) oznacza, że poniżej `md` (768 px) 5-kolumnową tabelę trzeba zastąpić responsywną listą kart bez przewijania w poziomie (`NFR Szerokość okna`).

### 3. Wzorce z archiwów (S-07, S-08, S-09) i dane pilotażowe dla przykładów demo

- **Wzorzec danych syntetycznych z S-07:** `backend/app/synthetic/importer.py:21-233` i `backend/app/synthetic/documents.json` pokazują przyjęty w repo standard:
  - źródłowy JSON w git zawiera wyłącznie treść autorstwa projektu (bez kopiowania surowego tekstu TechQA do repozytorium — `context/archive/2026-11-26-conflicting-sources/plan.md:37`);
  - komenda CLI (`python -m app.cli import-synthetic-conflicts`, `backend/app/cli.py:523-532`) działa w pojedynczej transakcji z `pg_advisory_xact_lock`, usuwa wyłącznie własny zakres danych, wstawia deterministyczne rekordy i raportuje `state_sha256` (`pierwszy import` / `identyczny` / `różny`).
- **Dane pilotażowe dla przykładów demo (`docs/pilotaz-audytu-techqa.md:13-80`):**
  - Pilotaż definiuje 12 syntetycznych spraw (`P01`–`P12`) opartych na 3 dokumentach TechQA (`swg21996508`, `swg21675316`, `swg21648497`).
  - W makiecie `S5.dc.html:26` widnieją przykłady `SIM-P08` (`contradiction`, `swg21648497`), `SIM-P11` (`insufficient`, `swg21675316`), `SIM-P04` (`partial`, `swg21996508`), `SIM-P01` (`full`, `swg21996508`) — ten zestaw 4 spraw pokrywa wszystkie 4 kategorie `note_verdict` oraz wszystkie 3 dokumenty źródłowe pilotażu.
  - Aby zachować zasadę niecommitowania surowych tekstów TechQA do git, a jednocześnie mieć prawdziwe, klikalne cytaty działające z panelem dowodu (`GET /api/evidence/...`), seeder CLI (np. `import-demo-audits`) może rozwiązywać `chunk_id`, `doc_id`, `doc_title` i dosłowne cytaty bezpośrednio z zaimportowanej lokalnie migawki TechQA w bazie (z deterministycznymi UUID-ami `uuid5`, dzięki czemu ponowny seed jest idempotentny i nie zrywa zapisanych w sesji decyzji, jeśli użyje `ON CONFLICT DO UPDATE` lub stałych UUID-ów — choć decyzje na demo można też czyścić tylko przy zmianie lub zachować przy upsert).

---

## Code References

- `backend/migrations/0004_audits.sql:5-63` — tabele `audits`, `audit_claims`, indeks `audits_session_created_idx`.
- `backend/migrations/0005_audit_decisions_and_history.sql:4-55` — tabele `audit_claim_decisions` (`UNIQUE (claim_id, session_hash)`) i `audit_events` (izolacja zdarzeń `system` vs `human`).
- `backend/app/auditing/store.py:40,123,409-414,472-541` — `DecisionStatus`, `StoredAudit.is_demo`, obsługa `is_demo = true` w `upsert_claim_decision` i `get_audit_for_session`.
- `backend/app/api/audits.py:146-187,289-428` — `AuditDetailResponse`, `compute_decision_status`, obecne 3 endpointy i zależność `AuditSessionDep`.
- `backend/app/session.py:15-71` — ciasteczko `kops_session`, `SessionDep`, `AuditSessionDep`.
- `backend/app/cli.py:505-796` — struktura podkomend CLI `python -m app.cli`.
- `backend/app/synthetic/importer.py:21-233` — wzorzec idempotentnego importera z `pg_advisory_xact_lock` i `state_sha256`.
- `design/mockups/canvas/S5.dc.html:5,12-26` — pełna makieta ekranu 5 („Analizy i decyzje”).
- `frontend/app/routes.ts:8-15` — obecne 4 trasy SPA.
- `frontend/app/components/shell/NavRail.tsx:28-45` — komentarz S-10 i aktualne 2 pozycje nawigacji.
- `frontend/app/components/audit/AuditResultView.tsx:61-200,462-467` — prywatne komponenty pigułek statusów i breadcrumb do `/audyt`.
- `frontend/app/components/assistant/Icon.tsx:33-302` — istniejące ikony werdyktów, statusów i spinnera.
- `frontend/app/api/audits.ts:1-72` & `frontend/app/lib/audit.ts:144-252` — klient API audytów i mapy etykiet.
- `frontend/app/app.css:4-47` — tokeny kolorystyczne z kanwy.

---

## Architecture Insights

1. **Jedno źródło prawdy dla `decision_status` i sortowania:** logika `compute_decision_status` (`backend/app/api/audits.py:173-187`) powinna pozostać spójna między `GET /api/audits` a `GET /api/audits/{audit_id}` (najlepiej wyliczana spójnym wyrażeniem SQL lub wspólną funkcją w Pythonie, gdy lista sesji + demo jest niewielka, lub `CASE` w SQL z testem parzystości przeciw `compute_decision_status`).
2. **Spójność kontraktu sesyjnego na przykładach demo:** skoro `GET /api/audits` musi pokazać wspólne przykłady demo także nowemu odwiedzającemu bez ciasteczka `kops_session`, ta sama zasada musi dotyczyć otwarcia szczegółów (`GET /api/audits/{audit_id}` → `OptionalSessionDep`) oraz pierwszego zapisu decyzji na przykładzie demo (`PUT /api/audits/{audit_id}/claims/{claim_id}/decision` → `SessionDep`, który przy okazji nada ciasteczko sesji). W przeciwnym razie kliknięcie przykładu demo na czystej sesji skończy się `404`.
3. **Niezależność od reimportu TechQA i brak tekstu TechQA w git:** `audits` nie ma FK do `documents`/`chunks`, a seeder demo może dociągać dosłowne fragmenty i `chunk_id` z lokalnie zaimportowanej migawki TechQA w DB (lub działać z jawnym komunikatem, gdy brak migawki TechQA), zachowując higienę repozytorium z S-07.

---

## Historical Context (from prior changes)

- `context/archive/2026-11-26-resolved-case-audit/plan.md:5,41,51,73-75` — **supported:** S-08 celowo przygotował `is_demo`, `case_ref` i brak FK do tabel TechQA w `0004_audits.sql`, odkładając trasę `/analizy` i seedowanie demo do S-10.
- `context/archive/2026-11-26-resolved-case-audit/reviews/impl-review.md:83-91` — **supported:** znalezisko F6 jawnie zaakceptowało `AuditSessionDep` na `GET /api/audits/{audit_id}` w S-08 i odłożyło przełączenie na opcjonalną sesję do S-10.
- `context/archive/2026-11-27-editor-decision-and-history/plan.md:28,39,46,76,83` — **supported:** S-09 przygotował `UNIQUE (claim_id, session_hash)` i izolację `audit_events` pod współdzielone rekordy `is_demo = true`, odkładając `/analizy`, link powrotny z ekranu `3`/`3N` oraz seedowanie demo do S-10.
- `context/archive/2026-11-27-editor-decision-and-history/reviews/impl-review.md:54-62` — **supported:** test HTTP `test_demo_audit_http_isolates_decisions_and_history_between_sessions` już weryfikuje izolację decyzji między dwiema sesjami posiadającymi ciasteczko `kops_session` na rekordzie `is_demo = true`.
- `context/archive/2026-11-26-conflicting-sources/plan.md:18,37,43` — **supported:** ustalił zasadę niecommitowania surowego tekstu TechQA do git oraz wzorzec idempotentnego CLI z `pg_advisory_xact_lock`.
- `docs/przeplyw-danych.md:28,32,36-37,45-47` (lokalny plik w `.gitignore`) — **partial:** poprawnie opisuje izolację `session_hash` i brak automatycznej retencji, ale nie opisuje jeszcze wspólnych rekordów `is_demo = true` ani `GET /api/audits` — do uzupełnienia w S-10.

---

## Related Research

- `context/archive/2026-11-26-resolved-case-audit/research.md` — badanie S-08 (schemat audytów, nawigacja `NavRail`, trasy `/audyt` i odroczone `/analizy`).
- `context/archive/2026-11-27-editor-decision-and-history/research.md` — badanie S-09 (decyzje per teza, `audit_events`, izolacja `session_hash`).

---

## Open Questions

Pytania do rozstrzygnięcia w `/10x-plan analyses-list`:
1. **Zestaw i sposób seedowania przykładów demo (`is_demo = true`):** ile przykładów seedować domyślnie (np. 4 z pilotażu: `SIM-P08` sprzeczność, `SIM-P11` niewystarczające dowody, `SIM-P04` częściowe pokrycie, `SIM-P01` pełne pokrycie — pokrywające wszystkie 4 kategorie `note_verdict` i 3 dokumenty TechQA) oraz czy seed ma działać jako osobna komenda CLI `import-demo-audits` z rozwiązywaniem cytatów z lokalnej bazy TechQA?
2. **Oznaczenie pochodzenia wiersza i filtr źródła:** czy oprócz licznika w pasku filtrów (`X przykładów · Y Twoje (ta sesja)`) wyświetlać subtelną etykietę w wierszu (np. `Przykład demo` vs `Ta sesja`) lub filtr źródła (w tym ułatwiający osiągnięcie stanu pustego dla „Twoje (ta sesja)”, gdy lista ma zawsze widoczne przykłady demo)?
3. **Osiągalność obu stanów pustych (`US-04`, `roadmap.md:386`):** gdy w bazie są wspólne przykłady demo (`is_demo = true`), cała lista nie jest pusta dla nowego odwiedzającego. Jak prezentować stan „Nie masz jeszcze analiz w tej sesji. Przykłady demo są dostępne zawsze.” (np. baner/karta stanu pustego sekcji sesji nad lub pod przykładami, przełącznik „Wszystkie / Tylko Twoje (ta sesja)”, oraz osobny stan pusty przy braku jakichkolwiek rekordów w bazie)?
4. **Kopia w stopce dotycząca retencji:** makieta `S5.dc.html:26` zawiera zwrot „a po ograniczonym czasie są usuwane”, mimo że TTL sesji (PRD Open Question 10) nie jest jeszcze zaimplementowany — doprecyzować uczciwy komunikat zgodny z zasadą z PRD Guardrails (nie deklarować nieistniejących mechanizmów).
5. **Ścieżka trasy i nawigacja z ekranów `2P`/`3`/`3N`:** potwierdzić `/analizy` jako ścieżkę dla ekranu 5 oraz zaktualizowanie linków powrotnych (`AuditResultView.tsx:462-467`, `AuditProgressView`, `NavRail.tsx:28-45`).
