# Lista analiz i decyzji (`analyses-list`, S-10) — Plan implementacji

## Overview

Wdrażamy etap **S-10 (`analyses-list`, ekran `5` — „Analizy i decyzje”; `US-04`, `FR-010`)**:
- backend listujący wspólne przykłady demo (`is_demo = true`) i analizy bieżącej sesji (`session_hash`) w `GET /api/audits` wraz z filtrami, licznikami zbiorczymi i priorytetowym sortowaniem;
- naprawę dostępu bez ciasteczka `kops_session` dla przykładów demo (`OptionalSessionDep` na odczytach oraz `SessionDep` na zapisie decyzji);
- idempotentny seeder CLI `import-demo-audits` ładujący 4 reprezentatywne sprawy z pilotażu (`SIM-P08`, `SIM-P11`, `SIM-P04`, `SIM-P01`) z rozwiązywaniem `chunk_id` i dosłownych cytatów z lokalnej bazy TechQA (zero surowego tekstu TechQA w repozytorium);
- nowy widok SPA `/analizy` z 3. pozycją w `NavRail`, oddzielnymi kolumnami oceny systemu i decyzji redaktora, filtrami (wyszukiwarka, Decyzja, Ocena systemu, Źródło), oboma stanami pustymi, uczciwą stopką bez deklarowania nieistniejącego TTL oraz układem responsywnym 390 px.

## Current State Analysis

- **Schemat bazy danych (`0004_audits.sql`, `0005_audit_decisions_and_history.sql`)** jest w większości gotowy:
  - `audits` zawiera `is_demo boolean NOT NULL DEFAULT false`, `session_hash`, `case_ref`, `case_description`, `resolution_note`, `status`, `stage`, `claims_total`, `claims_done`, `note_verdict`, `case_context jsonb`, `created_at`, `updated_at`, `completed_at` i nie ma FK do tabel TechQA.
  - `audit_claim_decisions` (`UNIQUE (claim_id, session_hash)`, indeks `(audit_id, session_hash)`) i `audit_events` (`actor_type = 'system'` vs `'human'`) już izolują decyzje i historię per sesja na rekordach `is_demo = true`.
  - Brakuje jedynie częściowego indeksu na `audits` dla `is_demo = true` oraz funkcji listującej w `backend/app/auditing/store.py`.
- **Krytyczna luka sesyjna (`backend/app/session.py:51-71`, `backend/app/api/audits.py:373-428`):**
  - `store.get_audit_for_session` już przyjmuje `session_hash: str | None` i zwraca rekordy `is_demo = true` bez sesji, ale `GET /api/audits/{audit_id}` i `PUT /api/audits/{audit_id}/claims/{claim_id}/decision` używają dziś `AuditSessionDep`, który odrzuca brak ciasteczka kodem `404`.
  - `AuditDetailResponse` nie zwraca jeszcze pola `is_demo`.
- **Brak seedera przykładów demo:** `backend/app/cli.py` ma `import-synthetic-conflicts` (wzorzec z S-07: autorski JSON w git, `pg_advisory_xact_lock`, raport `state_sha256`), ale nie ma komendy seedującej `audits` z `is_demo = true`.
- **Frontend (`frontend/app/`):**
  - `routes.ts` ma 4 trasy (`/`, `/odpowiedz/:id`, `/audyt`, `/audyt/:id`) — brak `/analizy`.
  - `NavRail.tsx:28-45` ma 2 pozycje (z komentarzem dla S-10), a `/audyt` nie ma `end: true`.
  - `AuditResultView.tsx:462-467` kieruje link powrotny do `/audyt`, a pigułki `NoteVerdictPill`/`ClaimVerdictPill`/`DecisionStatusPill` są prywatne.
  - `Icon.tsx` ma ikony werdyktów, statusów i spinnera; brakuje ikony lupy i listy. Brakuje też tokenu hover wiersza `#f6f5f1` w `app.css` oraz układu kartowego poniżej `md` (768 px) dla 390 px.

## Desired End State

- Nowy odwiedzający bez ciasteczka `kops_session` wchodzi na `/analizy`, widzi 4 wspólne przykłady demo (`SIM-P08`, `SIM-P11`, `SIM-P04`, `SIM-P01`) oraz komunikat pustej sesji z CTA do `/audyt`, może otworzyć dowolny przykład demo (`/audyt/:id`), zobaczyć klikalne cytaty w panelu dowodu i zapisać własną decyzję (co nadaje ciasteczko `kops_session` i odświeża „Ostatnią zmianę” wyłącznie dla jego sesji).
- Analizy utworzone w jednej sesji (`POST /api/audits`) pojawiają się na liście tej sesji, ale nigdy nie są widoczne w innej sesji; decyzje zapisane na przykładach demo są całkowicie odizolowane między sesjami.
- Lista oddziela ocenę systemu (`Ocena systemu`) od decyzji człowieka (`Decyzja redaktora`), pozwala filtrować po wyszukiwarce, decyzji, ocenie systemu i źródle (`Wszystkie` / `Przykłady demo` / `Twoje (ta sesja)`), rozróżnia stan pustej sesji/listy od braku wyników filtra i pozostaje czytelna bez przewijania w poziomie przy 390 px.

### Key Discoveries:

- `backend/app/auditing/store.py:409-414,472-541` — warstwa SQL już obsługuje `is_demo = true` w `upsert_claim_decision` i `get_audit_for_session(..., session_hash: str | None)`.
- `backend/app/api/audits.py:173-187` — `compute_decision_status` jest źródłem prawdy dla 4 stanów `DecisionStatus` (`pending`, `in_progress`, `saved`, `not_applicable`); lista musi zachować 1:1 parzystość.
- `backend/app/synthetic/importer.py:117-233` — wzorzec idempotentnego importera CLI (`pg_advisory_xact_lock`, brak surowego tekstu TechQA w git, raport `state_sha256`).
- `design/mockups/canvas/S5.dc.html:26` — referencja układu ekranu 5 (5 kolumn, baner „Zacznij od …”, pasek filtrów, oba stany puste); makieta nie ma wersji `S5N` dla 390 px ani nie uwzględnia braku TTL w backendzie.

## What We're NOT Doing

- Nie wdrażamy logowania, kont użytkowników ani kontroli dostępu opartej na przełączniku ról (`FR-011`).
- Nie wdrażamy automatycznego TTL / retencji danych sesji (osobny otwarty temat PRD Open Question 10) i nie deklarujemy usuwania danych w kopii UI.
- Nie dodajemy usuwania ani edycji analiz, paginacji serwerowej ani eksportu CSV/JSON.
- Nie commitujemy surowego tekstu korpusu TechQA do repozytorium git — definicje demo w git zawierają wyłącznie autorskie opisy/notatki/uzasadnienia i referencje do dokumentów TechQA.
- Nie zmieniamy dokumentacji po zapisie decyzji (człowiek decyduje, system nie publikuje).

## Implementation Approach

Budujemy zmianę warstwowo w 4 niezależnych fazach:
1. **Warstwa danych i sesji (Faza 1):** dodajemy częściowy indeks na `audits` (`WHERE is_demo = true`), `OptionalSessionDep` w `session.py` oraz pojedyncze zapytanie SQL `list_audits_for_session` w `store.py`, które wylicza podział werdyktów tez, `decisions_count`, `decision_status` (1:1 z `compute_decision_status`), `last_activity_at = GREATEST(a.updated_at, COALESCE(MAX(d.updated_at), a.updated_at))` dla bieżącej sesji i sortuje priorytetowo (`pending`/`in_progress` → `queued`/`running` → `saved`/`failed`/`not_applicable`, dalej po `last_activity_at DESC, created_at DESC, id DESC`).
2. **Seeder przykładów demo (Faza 2):** w `backend/app/auditing/demo_seed.py` i `backend/app/auditing/demo_audits.json` definiujemy 4 sprawy z pilotażu (`SIM-P08`, `SIM-P11`, `SIM-P04`, `SIM-P01`). Komenda `python -m app.cli import-demo-audits` działa w jednej transakcji z `pg_advisory_xact_lock`, używa deterministycznych `uuid5` (dla `audit_id` i `claim_id`) i wyszukuje `chunk_id`, `doc_title` oraz dosłowne cytaty bezpośrednio w lokalnej bazie TechQA (`documents`/`chunks`), aktualizując wyłącznie rekordy demo bez naruszania zapisanych przez użytkowników decyzji (`ON CONFLICT DO UPDATE` lub zachowanie stałych `claim_id`).
3. **API i kontrakt (Faza 3):** dodajemy `GET /api/audits` z parametrami filtrów (`q`, `decision_status`, `note_verdict`, `source`), licznikami zbiorczymi (niezależnymi od aktualnych filtrów, tak aby pasek podsumowania i baner „Zacznij od …” zawsze pokazywały realny stan listy) oraz wskazaniem pierwszej oczekującej analizy; przełączamy `GET /api/audits/{id}` na `OptionalSessionDep` i `PUT .../decision` na `SessionDep`; eksportujemy `openapi.json` i `schema.d.ts` oraz uzupełniamy lokalny `docs/przeplyw-danych.md`.
4. **Frontend `/analizy` i nawigacja (Faza 4):** dodajemy trasę `/analizy`, 3. pozycję w `NavRail` + `end: true` na `/audyt`, aktualizujemy link powrotny z `/audyt/:id` na `/analizy`, wydzielamy wspólne pigułki do `AuditBadges.tsx`, budujemy responsywny ekran 5 (tabela `md+`, karty `<md` dla 390 px), chip pochodzenia `Demo`, filtr źródła, oba stany puste i uczciwą stopkę.

## Critical Implementation Details

- **Zachowanie decyzji sesji przy ponownym uruchomieniu `import-demo-audits`:** `audit_claim_decisions` ma `ON DELETE CASCADE` do `audits` i `audit_claims` (`0005_audit_decisions_and_history.sql:10-12`). Jeśli seeder usuwałby wiersze `audits WHERE is_demo = true` przed `INSERT`, skasowałby zapisane w sesjach decyzje na przykładach demo. Dlatego seeder musi używać deterministycznych `uuid5` dla `audit_id` i `claim_id` oraz wykonywać `INSERT ... ON CONFLICT (id) DO UPDATE`, usuwając wyłącznie przestarzałe rekordy/tezy demo spoza bieżącego zestawu ID.
- **Środowisko Windows / Docker:** na hoście Windows App Control blokuje `psycopg_binary` i `mypy`. Kontrole backendu (`mypy`, `pytest`, `scripts/export_openapi.py`) uruchamiamy w kontenerze `ghcr.io/astral-sh/uv:python3.14-bookworm-slim` w sieci `knowledgeops_default` z `DATABASE_URL` na `db:5432`, a migracje i CLI w działającym kontenerze `backend` (`docker compose exec backend .venv/bin/python -m app.cli ...`).

---

## Phase 1: Indeks bazy danych, sesje i zapytanie listujące (`store.py`)

### Overview
Dodajemy indeks wspierający odczyt wspólnych przykładów demo, opcjonalną zależność sesji `OptionalSessionDep` oraz pełne zapytanie listujące analizy z agregacją tez, decyzji, `last_activity_at` i priorytetowym sortowaniem.

### Changes Required:

#### 1. Migracja częściowego indeksu dla rekordów demo
**File**: `backend/migrations/0006_audits_demo_index.sql`
**Intent**: Przyspiesza pobieranie wspólnych przykładów demo (`is_demo = true`) łączonych z analizami sesji na liście `/analizy`.
**Contract**: Tworzy indeks `CREATE INDEX IF NOT EXISTS audits_demo_updated_idx ON audits (updated_at DESC) WHERE is_demo = true;`.

#### 2. Opcjonalna zależność sesji w `session.py`
**File**: `backend/app/session.py`
**Intent**: Umożliwia endpointom odczytu (`GET /api/audits`, `GET /api/audits/{audit_id}`) działanie dla nowych odwiedzających bez ciasteczka `kops_session`, przy jednoczesnym rozpoznaniu istniejącej sesji, gdy ciasteczko jest obecne.
**Contract**: Dodaje `get_optional_session(request: Request) -> str | None` (zwraca `hash_token(token)` lub `None`, nie ustawia ciasteczka i nie rzuca `404`) oraz alias `OptionalSessionDep = Annotated[str | None, Depends(get_optional_session)]`.

#### 3. Zapytanie listujące, liczniki i sortowanie w `store.py`
**File**: `backend/app/auditing/store.py`
**Intent**: Dostarcza jedno spójne źródło prawdy w warstwie DB dla listy analiz, podziału werdyktów tez, licznika decyzji bieżącej sesji, `last_activity_at` oraz sortowania priorytetowego.
**Contract**:
- Dodaje typ `AuditSourceFilter = Literal["all", "demo", "session"]`, pomocniczą funkcję `compute_decision_status(status, claims_total, decisions_count) -> DecisionStatus` (przeniesioną z `api/audits.py` do `store.py`, aby obie warstwy współdzieliły jedną definicję) oraz funkcję `_derive_problem_summary(case_context, case_description) -> str` (używa `case_context["problem"]`, gdy niepuste, inaczej `case_description`).
- Dodaje modele `StoredAuditListItem` (pola: `id`, `is_demo`, `case_ref`, `problem_summary`, `status`, `stage`, `note_verdict`, `claims_total`, `claims_done`, `claims_supported`, `claims_contradicted`, `claims_insufficient`, `decisions_count`, `decision_status`, `created_at`, `updated_at`, `last_activity_at`) oraz `StoredAuditListResult` (`items`, `demo_count`, `session_count`, `pending_count`, `in_progress_count`, `saved_count`, `next_pending_audit_id`, `next_pending_case_ref`).
- Dodaje `list_audits_for_session(conn, session_hash: str | None, *, q: str | None = None, decision_status: DecisionStatus | None = None, note_verdict: NoteVerdict | None = None, source: AuditSourceFilter = "all") -> StoredAuditListResult`:
  - Pobiera wyłącznie wiersze spełniające `a.is_demo = true OR ($session_hash IS NOT NULL AND a.session_hash = $session_hash)`.
  - Agreguje po `audit_claims` liczbę tez `supported` / `contradicted` / `insufficient` oraz po `audit_claim_decisions` (filtrowanych po `d.session_hash = $session_hash`) `decisions_count` i `MAX(d.updated_at)`.
  - Wylicza `last_activity_at = GREATEST(a.updated_at, COALESCE(MAX(d.updated_at), a.updated_at))`.
  - Sortuje według grup priorytetu:
    - grupa `0`: `status = 'completed'` i `decision_status IN ('pending', 'in_progress')`
    - grupa `1`: `status IN ('queued', 'running')`
    - grupa `2`: pozostałe (`saved`, `failed`, `not_applicable`)
    - wewnątrz grupy: `last_activity_at DESC, created_at DESC, id DESC`.
  - Liczniki podsumowania (`demo_count`, `session_count`, `pending_count`, `in_progress_count`, `saved_count`) i `next_pending_audit_id`/`next_pending_case_ref` (pierwszy rekord grupy `0`) wylicza na całym widocznym zbiorze (przed filtrami `q`/`decision_status`/`note_verdict`/`source`), a zwracane `items` filtruje według podanych kryteriów (`q` dopasowuje case-insensitive po `case_ref`, `problem_summary`, `case_description`).

#### 4. Testy warstwy `store.py` i `session.py`
**File**: `backend/tests/test_audits_list_store.py`
**Intent**: Weryfikuje w bazie (i w testach jednostkowych) izolację sesji, sortowanie priorytetowe, wyliczanie `last_activity_at` per sesja na rekordzie demo, filtry oraz parzystość `compute_decision_status`.
**Contract**: Testy jednostkowe + `@pytest.mark.db` pokrywające: (a) brak `session_hash` zwraca wyłącznie `is_demo = true`, (b) analiza sesji A nie pojawia się w sesji B, (c) zapis decyzji przez sesję A na rekordzie demo zmienia `decision_status`, `decisions_count` i `last_activity_at` tylko dla sesji A, (d) kolejność sortowania `pending`/`in_progress` → `queued`/`running` → `saved`/`failed`, (e) filtrowanie po `q`, `decision_status`, `note_verdict` i `source`, (f) liczniki podsumowania niezależne od aktywnych filtrów.

### Success Criteria:

#### Automated Verification:
- Migracja `0006_audits_demo_index.sql` nakłada się czysto i idempotentnie (`python -m app.cli migrate`).
- Testy `backend/tests/test_audits_list_store.py` oraz istniejące testy audytu przechodzą w Dockerze (`pytest`).
- Kontrole jakości backendu przechodzą bez błędów (`ruff check .`, `ruff format --check .`, `mypy .`).

#### Manual Verification:
- Brak — faza czysto backendowa (weryfikowana testami integracyjnymi DB).

**Implementation Note**: Po przejściu wszystkich testów i kontroli automatycznych fazy 1 zrób commit Conventional Commits (`feat(backend): add demo index, optional session dep, and audit list store`) i przejdź do fazy 2.

---

## Phase 2: Idempotentny seeder przykładów demo (`import-demo-audits`)

### Overview
Tworzymy idempotentny mechanizm seedowania 4 syntetycznych przykładów demo z pilotażu (`SIM-P08`, `SIM-P11`, `SIM-P04`, `SIM-P01`), pokrywających wszystkie 4 werdykty notatki i 3 dokumenty TechQA, bez umieszczania surowego tekstu TechQA w repozytorium git.

### Changes Required:

#### 1. Definicje 4 spraw demo (autorski JSON w git)
**File**: `backend/app/auditing/demo_audits.json`
**Intent**: Przechowuje autorskie definicje 4 spraw pilotażowych (`SIM-P08` sprzeczność, `SIM-P11` niewystarczające dowody, `SIM-P04` częściowe pokrycie, `SIM-P01` pełne pokrycie) bez cytowania surowego tekstu TechQA.
**Contract**: JSON w wersji `demo-audits@v1` zawierający dla każdej sprawy: `slug`, `case_ref` (`SIM-P08`, `SIM-P11`, `SIM-P04`, `SIM-P01`), `case_description`, `resolution_note`, `note_verdict`, `case_context` (`problem`, `product`, `version`, `environment`, `os`), `created_offset_minutes` (deterministyczna kolejność startowa zgodna z S5), oraz listę `claims` (`claim_index`, `claim_label`, `claim_text`, `source_excerpt`, `search_query`, `verdict`, `rationale`, `scope_note`, `evidence_specs`: wskazujące `doc_id` i wzorzec/frazę kotwiczną do wyszukania chunku w lokalnej bazie TechQA, `checked_doc_ids`: listę `doc_id` sprawdzonych dokumentów).

#### 2. Idempotentny importer przykładów demo
**File**: `backend/app/auditing/demo_seed.py`
**Intent**: Ładuje `demo_audits.json`, rozwiązuje `chunk_id`, `doc_title`, `headings`, `start_offset`, `end_offset` i dosłowne cytaty z lokalnej migawki TechQA w bazie danych, i zapisuje 4 rekordy `is_demo = true` atomowo i idempotentnie bez kasowania zapisanych decyzji użytkowników.
**Contract**:
- Stała blokada doradcza `DEMO_AUDITS_LOCK_KEY = 7_204_003` (osobna od TechQA i `synthetic@v1`) oraz stała przestrzeń nazw `DEMO_UUID_NAMESPACE` do wyliczania deterministycznych `uuid5` dla `audit_id` (`slug`) i `claim_id` (`slug:claim_index`).
- Stały `DEMO_SESSION_HASH = "demo"` (nigdy nie koliduje z 64-znakowym SHA-256 rzeczywistej sesji).
- Rozwiązywanie dowodów: dla każdego `evidence_spec` pobiera aktywny `chunk_set_id` z `settings.effective_chunk_set_id()` (lub podany jawnie), szuka dokumentu `doc_id` w `documents` i dopasowuje chunk zawierający frazę kotwiczną (wycinając dosłowny cytat o ograniczonej długości ze spanem w `chunk.text`), a jeśli brak migawki TechQA lub wymaganego dokumentu, podnosi czytelny `DemoSeedError` z instrukcją uruchomienia `import-techqa`.
- Transakcja z `pg_advisory_xact_lock`: wykonuje `INSERT ... ON CONFLICT (id) DO UPDATE` dla `audits` i `audit_claims`, dopisuje początkowe zdarzenia systemowe (`audit_created`, `evaluation_completed`) tylko gdy nie istnieją dla danego `audit_id` (unikając duplikatów przy ponownym uruchomieniu), usuwa jedynie nieaktualne rekordy demo spoza bieżącego zestawu `audit_id` i zwraca `DemoSeedReport` (`snapshot_id`, `chunk_set_id`, `audits_count`, `claims_count`, `state_sha256`, `comparison`).

#### 3. Podkomenda CLI `import-demo-audits`
**File**: `backend/app/cli.py`
**Intent**: Udostępnia operatorowi jednolitą komendę seedowania przykładów demo obok `import-techqa` i `import-synthetic-conflicts`.
**Contract**: Rejestruje podkomendę `import-demo-audits` z opcjonalnymi flagami `--file` (domyślnie `app/auditing/demo_audits.json`) i `--chunk-set` (domyślnie `settings.effective_chunk_set_id()`), wypisującą raport z liczbą audytów, tez, `state_sha256` i statusem porównania (`pierwszy import` / `identyczny` / `różny`).

#### 4. Testy seedera demo
**File**: `backend/tests/test_demo_seed.py`
**Intent**: Gwarantuje idempotentność seedera, poprawność generowanych cytatów przeciw panelowi dowodu, brak surowego tekstu TechQA w `demo_audits.json` oraz zachowanie decyzji sesji przy ponownym seedzie.
**Contract**: Testy jednostkowe + `@pytest.mark.db` sprawdzające: (a) poprawność i kompletność `demo_audits.json` (4 przypadki, wszystkie 4 `note_verdict`, wszystkie 3 `doc_id` pilotażu), (b) dwukrotne uruchomienie `import_demo_audits` na minimalnym korpusie testowym daje `comparison == "identyczny"` i nie duplikuje `audit_events`, (c) decyzja zapisana przez sesję na rekordzie demo przetrwa ponowne uruchomienie `import_demo_audits`, (d) brak migawki TechQA zgłasza czytelny `DemoSeedError`.

### Success Criteria:

#### Automated Verification:
- Testy `backend/tests/test_demo_seed.py` przechodzą w Dockerze (`pytest`).
- Komenda `docker compose exec backend .venv/bin/python -m app.cli import-demo-audits` uruchamia się czysto na lokalnej bazie TechQA; drugie uruchomienie raportuje `identyczny` i 4 przykłady demo.
- Kontrole jakości backendu przechodzą (`ruff check .`, `ruff format --check .`, `mypy .`).

#### Manual Verification:
- Brak — weryfikacja wizualna przykładów demo następuje w Fazie 4.

**Implementation Note**: Po przejściu testów i dwukrotnym czystym uruchomieniu `import-demo-audits` na lokalnej bazie zrób commit (`feat(backend): add idempotent import-demo-audits CLI seeder`) i przejdź do fazy 3.

---

## Phase 3: API `GET /api/audits`, poprawki sesyjne i kontrakt OpenAPI/TS

### Overview
Udostępniamy endpoint listy analiz `GET /api/audits`, naprawiamy dostęp do przykładów demo bez ciasteczka w `GET /api/audits/{audit_id}` i `PUT .../decision`, dodajemy `is_demo` do `AuditDetailResponse`, regenerujemy kontrakt OpenAPI/TypeScript i aktualizujemy lokalny opis przepływu danych.

### Changes Required:

#### 1. Endpoint `GET /api/audits` i naprawa zależności sesyjnych w `api/audits.py`
**File**: `backend/app/api/audits.py`
**Intent**: Wystawia listę analiz z filtrami i metadanymi podsumowania oraz pozwala odwiedzającym bez ciasteczka przeglądać i rozstrzygać wspólne przykłady demo.
**Contract**:
- Dodaje modele Pydantic: `AuditListItemResponse` (pola 1:1 ze `StoredAuditListItem`: `audit_id`, `is_demo`, `case_ref`, `problem_summary`, `status`, `stage`, `note_verdict`, `claims_total`, `claims_done`, `claims_supported`, `claims_contradicted`, `claims_insufficient`, `decisions_count`, `decision_status`, `created_at`, `updated_at`, `last_activity_at`), `AuditListSummaryResponse` (`demo_count`, `session_count`, `pending_count`, `in_progress_count`, `saved_count`, `next_pending_audit_id`, `next_pending_case_ref`) oraz `AuditListResponse` (`items`, `summary`).
- Dodaje `is_demo: bool` do `AuditDetailResponse` i przekazuje `stored.is_demo` w `_to_detail_response`.
- Usuwa duplikat `compute_decision_status` i importuje go z `app.auditing.store`.
- Dodaje `@router.get("/audits", response_model=AuditListResponse)` z parametrami query: `q: str | None = None`, `decision_status: DecisionStatus | None = None`, `note_verdict: NoteVerdict | None = None`, `source: AuditSourceFilter = "all"`, używający `OptionalSessionDep`.
- Zmienia zależność w `GET /api/audits/{audit_id}` z `AuditSessionDep` na `OptionalSessionDep` (dla nieistniejącego ID lub cudzej sesji nadal zwraca `404`).
- Zmienia zależność w `PUT /api/audits/{audit_id}/claims/{claim_id}/decision` z `AuditSessionDep` na `SessionDep` (pierwszy zapis decyzji na przykładzie demo bez ciasteczka nadaje `kops_session` i zapisuje decyzję w nowej sesji; zapis na cudzej analizie sesyjnej nadal zwraca `404` ze `store.upsert_claim_decision`).

#### 2. Testy HTTP dla `GET /api/audits` i sesji demo
**File**: `backend/tests/test_audits_api.py`
**Intent**: Pokrywa kontrakty HTTP, izolację sesji oraz ścieżkę nowego odwiedzającego bez ciasteczka.
**Contract**: Dodaje testy HTTP (zarówno z mockiem/stubem, jak i `@pytest.mark.db`): (a) `GET /api/audits` bez ciasteczka zwraca `200`, wyłącznie rekordy demo i nie ustawia `Set-Cookie`, (b) `GET /api/audits/{demo_id}` bez ciasteczka zwraca `200` z `is_demo=true`, a dla cudzej analizy sesyjnej zwraca `404`, (c) `PUT /api/audits/{demo_id}/claims/{claim_id}/decision` bez ciasteczka zwraca `200`, ustawia `kops_session`, a kolejna sesja bez tego ciasteczka nadal widzi `decisions_count=0`, (d) analiza utworzona przez sesję A pojawia się w `GET /api/audits` sesji A i nigdy w `GET /api/audits` sesji B, (e) filtry query `q`, `decision_status`, `note_verdict`, `source` poprawnie zawężają `items`, pozostawiając pełne `summary`.

#### 3. Kontrakt OpenAPI i typy TypeScript
**Files**: `backend/openapi.json`, `frontend/app/api/schema.d.ts`, `frontend/app/api/audits.ts`
**Intent**: Synchronizuje schemat API między backendem a frontendem (wymagane przez CI) oraz dodaje funkcję klienta `fetchAudits`.
**Contract**:
- Regeneracja `backend/openapi.json` (`scripts/export_openapi.py` w Dockerze) i `frontend/app/api/schema.d.ts` (`npm run api:types`).
- W `frontend/app/api/audits.ts`: eksport typów `AuditListResponse`, `AuditListItemResponse`, `AuditListSummaryResponse`, `AuditSourceFilter` oraz funkcji `fetchAudits(filters, signal)` wywołującej `GET /api/audits` z `credentials: "same-origin"`.

#### 4. Aktualizacja lokalnej dokumentacji przepływu danych
**File**: `docs/przeplyw-danych.md` (plik lokalny w `.gitignore` — nie commitować)
**Intent**: Utrzymuje dokumentację przepływu danych w zgodzie z aktualnym zachowaniem wspólnych przykładów `is_demo = true` i `GET /api/audits`.
**Contract**: Dopisuje w sekcji sesji i audytów opis widoczności `is_demo = true` bez ciasteczka, nadawania ciasteczka przy pierwszym zapisie decyzji oraz jawne zastrzeżenie o braku automatycznego TTL w bieżącej wersji.

### Success Criteria:

#### Automated Verification:
- Wszystkie testy backendu przechodzą w Dockerze (`pytest`), w tym nowe testy HTTP izolacji sesji i odczytu/zapisu demo bez ciasteczka.
- Kontrole backendu przechodzą (`ruff check .`, `ruff format --check .`, `mypy .`).
- Kontrakt jest aktualny (`backend/openapi.json` i `frontend/app/api/schema.d.ts` zregenerowane), a `cd frontend; npm run typecheck` przechodzi bez błędów.

#### Manual Verification:
- Brak — pełny przepływ sprawdzany ręcznie w przeglądarce w Fazie 4.

**Implementation Note**: Po przejściu testów i regeneracji kontraktu zrób commit jawnie wskazując pliki (bez gitignored `docs/przeplyw-danych.md`): `feat(api): add GET /api/audits and optional session access for demo audits`, a następnie przejdź do fazy 4.

---

## Phase 4: Frontend ekranu `/analizy`, nawigacja i responsywność 390 px

### Overview
Wdrażamy ekran `5` („Analizy i decyzje”) pod trasą `/analizy`, dodajemy go jako 3. pozycję w `NavRail`, aktualizujemy powrót z `/audyt/:id`, wydzielamy wspólne pigułki statusów i zapewniamy pełną responsywność do 390 px oraz obsługę obu stanów pustych.

### Changes Required:

#### 1. Trasa `/analizy`, `NavRail` i linki powrotne
**Files**: `frontend/app/routes.ts`, `frontend/app/components/shell/NavRail.tsx`, `frontend/app/components/audit/AuditResultView.tsx`, `frontend/app/routes/audit-detail.tsx`, `frontend/app/components/assistant/Icon.tsx`, `frontend/app/app.css`
**Intent**: Włącza pełną nawigację między Asystentem (`/`), nowym audytem (`/audyt`), listą analiz (`/analizy`) i szczegółami (`/audyt/:id`).
**Contract**:
- `routes.ts`: dodaje `route("analizy", "routes/analyses.tsx")`.
- `NavRail.tsx`: usuwa komentarz tymczasowy, dodaje `end: true` na `/audyt` oraz 3. pozycję `{ to: "/analizy", label: "nav.analyses", icon: <AnalysesListIcon /> }`.
- `AuditResultView.tsx` i `audit-detail.tsx`: zmienia link powrotny z `/audyt` na `/analizy` z etykietą „Wszystkie analizy” / „All analyses” (przycisk „Spróbuj ponownie” w stanie `failed` nadal prowadzi do `/audyt` z `state`).
- `Icon.tsx`: dodaje `SearchIcon` i `AnalysesListIcon` w stylu istniejących ikon (`strokeWidth={1.8}`).
- `app.css`: dodaje token `--color-row-hover: #f6f5f1;`.

#### 2. Wydzielenie wspólnych pigułek statusów i helperów listy
**Files**: `frontend/app/components/audit/AuditBadges.tsx`, `frontend/app/components/audit/AuditResultView.tsx`, `frontend/app/lib/audit.ts`
**Intent**: Eliminuje duplikację pigułek werdyktu notatki i statusu decyzji między ekranem szczegółów (`3`/`3N`) a listą (`5`) oraz zapewnia czyste funkcje formatowania podsumowań i czasu dla testów Vitest.
**Contract**:
- `AuditBadges.tsx`: eksportuje `NoteVerdictPill`, `ClaimVerdictPill` i `DecisionStatusPill` (z zachowaniem zasady słowo + ikona; `insufficient` zawsze neutralny szary, nigdy czerwony; dla `queued`/`running` spinner z `StepStatusIcon` i etykieta „Analiza trwa…”, dla `failed` status „Błąd analizy” z ikoną, dla `in_progress` etykieta „W toku” z kropką/ikoną).
- `lib/audit.ts`: dodaje czyste funkcje formatowania: `formatClaimBreakdown(item, t)` (np. „1 poparta · 1 bez wystarczających dowodów”), `formatCompactTimestamp(iso, locale)` (np. `22.11 10:22`), `hasActiveListFilters(filters)` oraz pomocniki liczników w pasku podsumowania.

#### 3. Widok listy `/analizy` (ekran `5`, desktop + karty 390 px, oba stany puste)
**Files**: `frontend/app/routes/analyses.tsx`, `frontend/app/components/audit/AnalysesListView.tsx`, `frontend/app/i18n/pl.ts`, `frontend/app/i18n/en.ts`
**Intent**: Realizuje ekran `5` zgodnie z makietą `S5.dc.html` oraz wszystkimi decyzjami projektowymi (filtr źródła, chip `Demo`, oba stany puste, uczciwa stopka, responsywność 390 px).
**Contract**:
- Nagłówek: `<h1>` „Analizy i decyzje” + chip `DEMO · dane z pilotażu` (z `InfoIcon` i tooltipem o publicznym demo i braku kontroli dostępu) + podtytuł.
- Baner akcji (gdy `summary.next_pending_audit_id` nie jest `null`): niebieska kropka `#2f5fc4`, licznik analiz czekających na decyzję (wliczając `pending` i `in_progress`) oraz link-przycisk primary „Zacznij od `<case_ref>`” prowadzący do `/audyt/<id>`.
- Pasek filtrów (synchronizowany z parametrami URL `useSearchParams`, debounced wyszukiwanie lub natychmiastowe z `AbortController`):
  - pole wyszukiwania (`q`),
  - natywny `<select>` „Decyzja” (`Wszystkie`, `Czeka na decyzję`, `W toku`, `Zapisane`, `Nie dotyczy`),
  - natywny `<select>` „Ocena systemu” (`Wszystkie`, `Sprzeczność`, `Częściowe pokrycie`, `Pełne pokrycie`, `Niewystarczające dowody`),
  - natywny `<select>` „Źródło” (`Wszystkie`, `Przykłady demo`, `Twoje (ta sesja)`),
  - podsumowanie liczbowe po prawej (`X przykładów · Y Twoje (ta sesja) · Z czekają · W w toku · S zapisane`).
- Pasek/karta stanu pustego sesji:
  - Gdy `summary.session_count === 0` i `source !== "demo"` oraz nie ma aktywnych filtrów wyszukiwania/decyzji/oceny: wyświetla wyraźny blok stanu pustego sesji („Nie masz jeszcze analiz w tej sesji. Przykłady demo są dostępne zawsze.” + link-przycisk „Przekaż rozwiązaną sprawę do audytu” → `/audyt`). Gdy wybrano `source === "session"` (lub gdy baza jest całkowicie pusta bez rekordów demo), blok ten zastępuje tabelę jako pełny stan pusty.
  - Gdy aktywne są filtry (`q`, `decision_status`, `note_verdict`, lub `source === "demo"` przy pustym wyniku) i `items.length === 0`: wyświetla osobny stan **Brak wyników filtra** („Żadna analiza nie pasuje do filtrów.” + przycisk „Wyczyść filtry” resetujący wszystkie filtry).
- Tabela desktop (`hidden md:block`): 5 kolumn z `S5.dc.html` (`Sprawa` z monospace ID + subtelny chip `Demo` dla `is_demo === true`, `Problem` z 2-line clamp, `Ocena systemu` z `NoteVerdictPill` i podziałem tez, `Decyzja redaktora` z ikoną/statusem i podlinią „X z Y tez rozstrzygnięte”, `Ostatnia zmiana` z `formatCompactTimestamp` i strzałką). Wiersze są w pełni dostępne z klawiatury (link w komórce lub semantyczna nawigacja do `/audyt/:id`) i podświetlają się na `#f6f5f1`.
- Widok kartowy mobilny (`md:hidden`, 390 px): każdy wiersz jako klikalna karta `Link` do `/audyt/:id` z `case_ref`, chipem `Demo`, problemem, pigułką oceny systemu + podziałem tez, statusem decyzji + postępem tez oraz czasem zmiany — zero przewijania w poziomie przy 390 px.
- Stopka listy: po lewej reguła sortowania („Najpierw analizy czekające na decyzję, potem ostatnia zmiana”), po prawej uczciwa nota bez obietnicy TTL („Oceny w tabeli to oceny systemu. Decyzję zapisuje człowiek. Przykłady demo są syntetyczne i wspólne; Twoje analizy i decyzje są widoczne tylko w tej sesji przeglądarki.”).
- Automatyczne odświeżanie (polling co 3 s), tylko gdy na liście znajduje się co najmniej jedna analiza ze statusem `queued` lub `running`, z czystym sprzątaniem przy odmontowaniu i unikaniem synchronicznego `setState` w `useEffect`.
- Pełne tłumaczenia w `pl.ts` i `en.ts`.

#### 4. Testy jednostkowe frontendu (Vitest)
**File**: `frontend/app/lib/audit.test.ts`
**Intent**: Weryfikuje czyste funkcje formatowania i logiki filtrów listy analiz.
**Contract**: Rozszerza `audit.test.ts` o testy dla `formatClaimBreakdown`, `formatCompactTimestamp` i `hasActiveListFilters` (wszystkie warianty werdyktów, 0 tez, stan pusty vs aktywny filtr).

### Success Criteria:

#### Automated Verification:
- Kontrole frontendu przechodzą bez błędów i ostrzeżeń: `cd frontend; npm run lint; npm run format:check; npm run typecheck; npm test; npm run build`.
- Kontrole backendu nadal przechodzą (brak regresji).

#### Manual Verification:
- Na czystej sesji przeglądarki (bez ciasteczka `kops_session`) wejście na `/analizy` pokazuje 4 przykłady demo (`SIM-P08`, `SIM-P11`, `SIM-P04`, `SIM-P01`), baner „Zacznij od SIM-P08”, chip `Demo` oraz komunikat pustej sesji z CTA do `/audyt`.
- Kliknięcie `SIM-P08` otwiera `/audyt/:id`, cytat otwiera panel dowodu, zapisanie decyzji zapisuje ją w tej sesji, a powrót przez „Wszystkie analizy” odświeża status i „Ostatnią zmianę” `SIM-P08` na liście.
- W drugiej, osobnej sesji (incognito / wyczyszczone ciasteczka) `SIM-P08` nadal czeka na decyzję, a analiza utworzona w pierwszej sesji nie pojawia się na liście.
- Oba stany puste są osiągalne i wyraźnie różne: stan pustej sesji (np. filtr `Twoje (ta sesja)` bez własnych analiz) z CTA do `/audyt` oraz stan braku wyników filtra (np. wpisanie nieistniejącej frazy w wyszukiwarce) z przyciskiem „Wyczyść filtry”.
- Przy szerokości `390 px` ekran `/analizy` wyświetla czytelne karty bez przewijania w poziomie, a przełączenie roli (`Konsultant` / `Redaktor`) i języka (`PL` / `EN`) działa bez blokowania widoku.

**Implementation Note**: Po przejściu wszystkich testów automatycznych zatrzymaj się na ręcznej weryfikacji UI w przeglądarce (1280/1440 px i 390 px), zanim zatwierdzisz zamknięcie fazy 4.

---

## Testing Strategy

### Unit Tests:
- `compute_decision_status`, `_derive_problem_summary`, walidacja `demo_audits.json` (4 przypadki, 4 werdykty, 3 dokumenty TechQA).
- Vitest (`frontend/app/lib/audit.test.ts`): `formatClaimBreakdown`, `formatCompactTimestamp`, `hasActiveListFilters`.

### Integration Tests (`@pytest.mark.db` w Dockerze):
- `test_audits_list_store.py`: izolacja sesji, sortowanie priorytetowe (`pending`/`in_progress` → `queued`/`running` → `saved`/`failed`), `last_activity_at` per sesja, filtry SQL i liczniki podsumowania.
- `test_demo_seed.py`: idempotentność `import_demo_audits` (`pierwszy import` → `identyczny`), brak duplikatów zdarzeń, zachowanie decyzji użytkownika po ponownym seedzie, obsługa braku migawki TechQA.
- `test_audits_api.py`: `GET /api/audits` bez ciasteczka, `GET /api/audits/{demo_id}` bez ciasteczka, `PUT .../decision` nadające `kops_session`, izolacja między dwiema sesjami HTTP.

### Manual Testing Steps:
1. Uruchomić `docker compose exec backend .venv/bin/python -m app.cli migrate` oraz `import-demo-audits` (dwukrotnie, potwierdzając `identyczny`).
2. Otworzyć `http://127.0.0.1:5173/analizy` w czystej sesji, sprawdzić 4 przykłady demo, baner „Zacznij od …”, chip `Demo`, komunikat pustej sesji i uczciwą stopkę.
3. Przetestować filtrowanie (wyszukiwarka, Decyzja, Ocena systemu, Źródło) oraz oba stany puste („Twoje (ta sesja)” vs nieistniejąca fraza + „Wyczyść filtry”).
4. Otworzyć `SIM-P08`, zweryfikować panel dowodu, zapisać decyzję, wrócić na `/analizy` i potwierdzić zmianę statusu; zweryfikować brak przecieku w drugiej sesji.
5. Zweryfikować układ responsywny przy `390 px` (karty, filtry, szuflada nawigacji) oraz przełączanie `PL` / `EN` i roli.

## Performance Considerations

- Lista łączy wyłącznie wspólne rekordy `is_demo = true` (4 wiersze) z rekordami bieżącej sesji (typowo kilka–kilkadziesiąt wierszy). Częściowy indeks `audits_demo_updated_idx` + istniejące indeksy `audits_session_created_idx` i `audit_claim_decisions_audit_session_idx` zapewniają pojedyncze, szybkie zapytanie SQL bez pełnego skanu tabeli.
- Polling listy na frontendzie włącza się wyłącznie wtedy, gdy na liście istnieje analiza w stanie `queued` lub `running`.

## Migration Notes

- Migracja `0006_audits_demo_index.sql` jest w pełni addytywna (`CREATE INDEX IF NOT EXISTS`) i bezinwazyjna dla istniejących danych.
- Istniejące analizy w bazie mają `is_demo = false` i pozostają widoczne wyłącznie w swoich sesjach.
- Przed ręcznym testem UI należy uruchomić `import-demo-audits` po zaimportowaniu migawki TechQA.

## References

- Related research: `context/changes/analyses-list/research.md`
- Product & roadmap: `context/foundation/prd.md`, `context/foundation/roadmap.md` (S-10), `docs/pilotaz-audytu-techqa.md`
- Mockup: `design/mockups/canvas/S5.dc.html`, `design/mockups/README.md`
- Similar implementation: `backend/app/synthetic/importer.py:117-233`, `backend/app/auditing/store.py:472-541`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Indeks bazy danych, sesje i zapytanie listujące (`store.py`)

#### Automated

- [x] 1.1 Migracja `0006_audits_demo_index.sql` nakłada się czysto i idempotentnie (`python -m app.cli migrate`).
- [x] 1.2 Testy `backend/tests/test_audits_list_store.py` oraz istniejące testy audytu przechodzą w Dockerze (`pytest`).
- [x] 1.3 Kontrole jakości backendu przechodzą bez błędów (`ruff check .`, `ruff format --check .`, `mypy .`).

### Phase 2: Idempotentny seeder przykładów demo (`import-demo-audits`)

#### Automated

- [ ] 2.1 Testy `backend/tests/test_demo_seed.py` przechodzą w Dockerze (`pytest`).
- [ ] 2.2 Komenda `docker compose exec backend .venv/bin/python -m app.cli import-demo-audits` uruchamia się czysto na lokalnej bazie TechQA; drugie uruchomienie raportuje `identyczny` i 4 przykłady demo.
- [ ] 2.3 Kontrole jakości backendu przechodzą (`ruff check .`, `ruff format --check .`, `mypy .`).

### Phase 3: API `GET /api/audits`, poprawki sesyjne i kontrakt OpenAPI/TS

#### Automated

- [ ] 3.1 Wszystkie testy backendu przechodzą w Dockerze (`pytest`), w tym nowe testy HTTP izolacji sesji i odczytu/zapisu demo bez ciasteczka.
- [ ] 3.2 Kontrole backendu przechodzą (`ruff check .`, `ruff format --check .`, `mypy .`).
- [ ] 3.3 Kontrakt jest aktualny (`backend/openapi.json` i `frontend/app/api/schema.d.ts` zregenerowane), a `cd frontend; npm run typecheck` przechodzi bez błędów.

### Phase 4: Frontend ekranu `/analizy`, nawigacja i responsywność 390 px

#### Automated

- [ ] 4.1 Kontrole frontendu przechodzą bez błędów i ostrzeżeń: `cd frontend; npm run lint; npm run format:check; npm run typecheck; npm test; npm run build`.
- [ ] 4.2 Kontrole backendu nadal przechodzą (brak regresji).

#### Manual

- [ ] 4.3 Na czystej sesji przeglądarki (bez ciasteczka `kops_session`) wejście na `/analizy` pokazuje 4 przykłady demo (`SIM-P08`, `SIM-P11`, `SIM-P04`, `SIM-P01`), baner „Zacznij od SIM-P08”, chip `Demo` oraz komunikat pustej sesji z CTA do `/audyt`.
- [ ] 4.4 Kliknięcie `SIM-P08` otwiera `/audyt/:id`, cytat otwiera panel dowodu, zapisanie decyzji zapisuje ją w tej sesji, a powrót przez „Wszystkie analizy” odświeża status i „Ostatnią zmianę” `SIM-P08` na liście.
- [ ] 4.5 W drugiej, osobnej sesji (incognito / wyczyszczone ciasteczka) `SIM-P08` nadal czeka na decyzję, a analiza utworzona w pierwszej sesji nie pojawia się na liście.
- [ ] 4.6 Oba stany puste są osiągalne i wyraźnie różne: stan pustej sesji (np. filtr `Twoje (ta sesja)` bez własnych analiz) z CTA do `/audyt` oraz stan braku wyników filtra (np. wpisanie nieistniejącej frazy w wyszukiwarce) z przyciskiem „Wyczyść filtry”.
- [ ] 4.7 Przy szerokości `390 px` ekran `/analizy` wyświetla czytelne karty bez przewijania w poziomie, a przełączenie roli (`Konsultant` / `Redaktor`) i języka (`PL` / `EN`) działa bez blokowania widoku.
