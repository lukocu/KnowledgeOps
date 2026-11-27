# Decyzja redaktora i historia analizy (`editor-decision-and-history`) — Implementation Plan

## Overview

W ramach etapu **S-09** (`US-02`, `FR-009`, `FR-021`, `FR-011`) dodajemy zapis i edycję decyzji redaktora dla każdej tezy z analizy rozwiązanego zgłoszenia (z wymaganym uzasadnieniem i czterema kategoriami startowymi bez wyboru domyślnego) oraz rzeczywistą, niemutowalną historię zdarzeń analizy. Decyzja człowieka jest trwale oddzielona od oceny systemu i nigdy nie zmienia ani nie publikuje dokumentacji.

## Current State Analysis

Po ukończeniu S-08 (`resolved-case-audit`, commit `4d47785`):
- **Baza danych (`backend/migrations/`):** Istnieją 4 niezmienne migracje (`0001`–`0004`, weryfikowane SHA-256 w `backend/app/migrations.py:39-61`). Migracja `0004_audits.sql` tworzy tabele `audits` (`status` w `{queued, running, completed, failed}`, `claims_total`, `note_verdict`) i `audit_claims` (`id uuid PK`, `audit_id FK CASCADE`, `claim_index`). Brak tabel dla decyzji redaktora i zdarzeń historii.
- **Store i API (`backend/app/auditing/store.py`, `backend/app/api/audits.py`):** `store.py` zapisuje cykl życia audytu w krótkich transakcjach (`create_audit`, `complete_audit`, `fail_audit`, `fail_orphaned_audits`) i udostępnia `get_audit_for_session`. `api/audits.py` wystawia `POST /api/audits` (`202`, `SessionDep`) oraz `GET /api/audits/{audit_id}` (`AuditSessionDep`, fail-closed `404` bez sesji).
- **Frontend (`frontend/app/routes/audit-detail.tsx`, `frontend/app/components/audit/AuditResultView.tsx`):** Działa lewa i środkowa kolumna ekranu `3` oraz wspólny prawy slot `PanelFrame` (`EvidencePanel` i `CaseContextPanel`). Tokeny kolorystyczne (`frontend/app/app.css:4-47`), przełącznik ról (`frontend/app/session/role.tsx`) oraz arkusz `<dialog>.showModal()` (`frontend/app/components/assistant/PanelFrame.tsx`) już istnieją. Brakuje panelu decyzji (`3`), dolnego paska CTA + arkusza (`3N`/`3N-D`), ikony osoby (`PersonIcon`), wskaźników decyzji na tezach oraz zwiniętej sekcji `Historia`.
- **Dokument przepływu danych (`docs/przeplyw-danych.md`, lokalny w `.gitignore`):** Wymaga dopisania tabel decyzji i zdarzeń historii oraz aktualizacji nagłówka i sekcji retencji.

## Desired End State

1. W bazie ParadeDB działają addytywne tabele `audit_claim_decisions` (z `UNIQUE (claim_id, session_hash)` i `CHECK (btrim(justification) <> '')`) oraz append-only `audit_events` (z backfill zdarzeń dla istniejących audytów).
2. `PUT /api/audits/{audit_id}/claims/{claim_id}/decision` waliduje sesję (`404`), stan audytu (`409` gdy nie `completed`), kategorię, rolę i niepuste uzasadnienie (`422`), wykonuje `UPSERT` decyzji i dopisuje `decision_saved` albo `decision_updated` w `audit_events` bez wywoływania LLM ani Langfuse.
3. `GET /api/audits/{audit_id}` zwraca decyzję przy każdej tezie, wyliczony `decision_status` (`pending` / `in_progress` / `saved` / `not_applicable`), `decisions_count` oraz uporządkowaną historię `history` (zdarzenia systemowe + zdarzenia człowieka z bieżącej sesji).
4. Na desktopie (`>= 1280 px`) obok oceny tezy widoczny jest stały prawy panel decyzji (`340 px`, tło `#f4f2ec`), tymczasowo zastępowany przez `EvidencePanel`/`CaseContextPanel` i przywracany po ich zamknięciu. Poniżej `1280 px` (w tym przy `390 px`, zero poziomego przewijania) działa przyklejony dolny pasek CTA otwierający arkusz `3N-D` (`<dialog>.showModal()`).
5. Formularz ma 4 kategorie startowe bez wyboru domyślnego, bez linii „Sugestia systemu”, z wymaganym uzasadnieniem i zastrzeżeniem MVP. W roli `consultant` formularz jest tylko do odczytu z przyciskiem „Przełącz na rolę Redaktor” i informacją o braku kontroli dostępu.
6. Zwinięty `<details>` `Historia` nad `Jak powstała ta analiza` pokazuje wyłącznie rzeczywiste zdarzenia (z rozróżnieniem ikony systemu i człowieka), a tezy i nagłówek pokazują postęp rozstrzygnięć (słowo + ikona).
7. Wszystkie kontrole backendu (`ruff`, `mypy` w Dockerze, `pytest` z testami DB) i frontendu (`lint`, `format:check`, `typecheck`, `test`, `build`) przechodzą na zielono, a `backend/openapi.json` i `frontend/app/api/schema.d.ts` są zsynchronizowane.

### Key Discoveries:

- `backend/app/migrations.py:39-61` weryfikuje SHA-256 zastosowanych migracji — `0001`–`0004` są niezmienne; wszystkie zmiany SQL muszą trafić do `0005_audit_decisions_and_history.sql`.
- `backend/migrations/0004_audits.sql:12` ogranicza `audits.status` do cyklu wykonania (`queued`/`running`/`completed`/`failed`), a `frontend/app/routes/audit-detail.tsx:41-74` steruje nim pollingiem — status decyzji musi być osobnym, wyliczanym polem `decision_status`.
- `backend/app/auditing/store.py:93-271` realizuje wszystkie przejścia cyklu życia audytu w `conn.transaction()`, więc zdarzenia `audit_created`, `evaluation_completed` i `evaluation_failed` mogą być wstawiane atomowo w tych samych transakcjach bez zmian w `runner.py` i `observability.py`.
- `frontend/app/components/assistant/PanelFrame.tsx:25-115` ma gotowy natywny `<dialog>.showModal()` z trapem fokusu, przysłoną i obsługą `Escape` — rozszerzenie go o wariant `"decision"` i opcjonalny `wideQuery` realizuje `3N-D` bez duplikacji kodu.
- `frontend/app/i18n/en.ts` jest typowany jako `Record<TranslationKey, string>`, więc TypeScript wymusza 100% pokrycia PL/EN.

## What We're NOT Doing

- **Żadnej edycji ani publikacji dokumentacji** — zapis decyzji niczego nie modyfikuje w tabeli `documents`/`chunks` ani w plikach źródłowych (`AGENTS.md`, `prd.md:107,253`).
- **Brak wywołań LLM i brak zapisu decyzji/uzasadnień do Langfuse** — dane decyzji zostają wyłącznie w ParadeDB.
- **Brak linii „Sugestia systemu” z makiety `S3`/`S3N`** — nie podpowiadamy wyboru redaktorowi (decyzja z wywiadu, zgodna z `prd.md:109-110,221`).
- **Brak etykiety „szkic” w historii** — `Historia` pokazuje wyłącznie rzeczywiste zdarzenia z `audit_events`.
- **Brak listy analiz `/analizy`, filtrów, przykładów demo i odczytu `is_demo` bez ciasteczka** — to zakres S-10 (`analyses-list`). Link w nagłówku pozostaje `/audyt`.
- **Brak ewaluacji audytu / macierzy pomyłek (`FR-015`)** — to zakres S-11.
- **Brak ciemnego motywu (`FR-022`)** — zaparkowane poza MVP.

## Implementation Approach

Realizujemy zmianę od warstwy danych do interfejsu w 3 przyrostowych fazach:
1. **ParadeDB + `store.py`:** Addytywna migracja `0005` tworzy `audit_claim_decisions` (z `session_hash` i `UNIQUE (claim_id, session_hash)` gotowym pod S-10 `is_demo`) oraz append-only `audit_events` (z backfill zdarzeń dla istniejących audytów). `store.py` rejestruje zdarzenia systemowe atomowo w transakcjach cyklu życia i udostępnia `upsert_claim_decision` oraz rozszerzony odczyt `get_audit_for_session`.
2. **FastAPI + kontrakt OpenAPI/TS:** Endpoint `PUT /api/audits/{audit_id}/claims/{claim_id}/decision` zwraca pełny, autorytatywny `AuditDetailResponse` (lub zaktualizowany obiekt audytu, co eliminuje rozjazd stanu między `decision`, `decision_status`, `decisions_count` i `history`). Wyliczenie `decision_status` jest czystą, deterministyczną funkcją uwzględniającą `not_applicable` dla `failed` i `completed` z `claims_total == 0`. Kontrakt synchronizujemy w `openapi.json` i `schema.d.ts`.
3. **Frontend (`3`, `3N`, `3N-D`, `Historia`):** Wydzielamy `ClaimDecisionPanel` i `AuditHistoryDetails`, rozszerzamy `PanelFrame` o wariant `"decision"` i breakpoint `1280 px`, a w `AuditResultView` koordynujemy zamianę prawego panelu (`>= 1280 px`) oraz dolny pasek CTA + arkusz `3N-D` (`< 1280 px`), z ochroną skrótów klawiszowych (`isEditableTarget`) i `AbortController` na zapisie.

## Critical Implementation Details

- **Niezmienność migracji `0001`–`0004` i limit puli połączeń (`max_size=5`):** Nie edytuj istniejących plików SQL. Wszystkie nowe zapytania w `store.py` wykonuj w krótkich transakcjach na przekazanym `AsyncConnection`, bez równoległego otwierania drugiego połączenia.
- **Separacja `audits.status` od `decision_status`:** Nigdy nie wpisuj `'saved'` do `audits.status`. Reguła wyliczania `decision_status`:
  - `queued` / `running` → `"pending"`
  - `failed` → `"not_applicable"`
  - `completed` i `claims_total == 0` → `"not_applicable"`
  - `completed` i `decisions_count == 0` → `"pending"`
  - `completed` i `0 < decisions_count < claims_total` → `"in_progress"`
  - `completed` i `decisions_count == claims_total` (przy `claims_total > 0`) → `"saved"`
- **Koordynacja `Escape` i fokusu z `<textarea>`:** Na desktopie (`>= 1280 px`) `Escape` zamyka tylko tymczasowo otwarty `EvidencePanel`/`CaseContextPanel` (wracając do stałego panelu decyzji) i nie przechwytuje klawiszy sterujących z edytowalnych pól (`isEditableTarget`). Poniżej `1280 px` `Escape` zamyka otwarty arkusz (`3N-D`, dowód lub kontekst) i przywraca fokus na przycisk, który go otworzył.
- **Środowisko Windows (weryfikacja):** `mypy` uruchamiamy w kontenerze Docker (`--cache-dir=/tmp/.mypy_cache`), a testy `pytest` z `@pytest.mark.db` wymagają wyeksportowania zmiennych z `.env` w sesji PowerShell.

---

## Phase 1: Migracja ParadeDB (`0005`) i warstwa `store.py`

### Overview

Dodajemy schemat bazy dla bieżących decyzji redaktora per teza (`audit_claim_decisions`) oraz niemutowalnej historii zdarzeń (`audit_events`), uzupełniamy historię dla audytów utworzonych przed migracją i rozszerzamy `backend/app/auditing/store.py` o atomowy zapis zdarzeń, `upsert_claim_decision` oraz odczyt decyzji i historii w `get_audit_for_session`.

### Changes Required:

#### 1. Addytywna migracja SQL
**File**: `backend/migrations/0005_audit_decisions_and_history.sql`

**Intent**: Utworzyć tabele `audit_claim_decisions` i `audit_events` z twardymi więzami integralności (niepuste uzasadnienie, 4 kategorie, etykieta roli, izolacja per `session_hash` pod przyszłe `is_demo`) oraz jednorazowo uzupełnić zdarzenia systemowe dla istniejących rekordów `audits`.

**Contract**:
- Tabela `audit_claim_decisions`:
  - `id uuid PRIMARY KEY`
  - `audit_id uuid NOT NULL REFERENCES audits(id) ON DELETE CASCADE`
  - `claim_id uuid NOT NULL REFERENCES audit_claims(id) ON DELETE CASCADE`
  - `session_hash text NOT NULL`
  - `decision text NOT NULL CHECK (decision IN ('agree_with_system', 'request_source_or_verify', 'consider_doc_update', 'system_verdict_wrong'))`
  - `justification text NOT NULL CHECK (btrim(justification) <> '')`
  - `role_label text NOT NULL CHECK (role_label IN ('editor', 'consultant'))`
  - `created_at timestamptz NOT NULL DEFAULT now()`
  - `updated_at timestamptz NOT NULL DEFAULT now()`
  - `UNIQUE (claim_id, session_hash)` oraz indeks `audit_claim_decisions_audit_session_idx ON audit_claim_decisions (audit_id, session_hash)`.
- Tabela `audit_events` (append-only):
  - `id uuid PRIMARY KEY`
  - `audit_id uuid NOT NULL REFERENCES audits(id) ON DELETE CASCADE`
  - `claim_id uuid REFERENCES audit_claims(id) ON DELETE CASCADE`
  - `session_hash text` (NULL dla `actor_type = 'system'`, wymagane dla `actor_type = 'human'`: `CHECK ((actor_type = 'system' AND session_hash IS NULL) OR (actor_type = 'human' AND session_hash IS NOT NULL))`)
  - `event_type text NOT NULL CHECK (event_type IN ('audit_created', 'evaluation_completed', 'evaluation_failed', 'decision_saved', 'decision_updated'))`
  - `actor_type text NOT NULL CHECK (actor_type IN ('system', 'human'))`
  - `role_label text CHECK (role_label IS NULL OR role_label IN ('editor', 'consultant'))`
  - `payload jsonb NOT NULL DEFAULT '{}'::jsonb`
  - `created_at timestamptz NOT NULL DEFAULT now()`
  - Indeks `audit_events_audit_created_idx ON audit_events (audit_id, created_at ASC, id ASC)`.
- Deterministyczny backfill dla istniejących wierszy `audits`: wstaw `audit_created` (`created_at = audits.created_at`) dla każdego istniejącego audytu, `evaluation_completed` (`created_at = COALESCE(audits.completed_at, audits.updated_at)`) z `payload` zawierającym `note_verdict` i `claims_total` dla `status = 'completed'`, oraz `evaluation_failed` (`created_at = audits.updated_at`) dla `status = 'failed'`.

#### 2. Modele i operacje SQL w `store.py`
**File**: `backend/app/auditing/store.py`

**Intent**: Rejestrować zdarzenia cyklu życia audytu atomowo w istniejących transakcjach, dodać operację zapisu/edycji decyzji per teza oraz rozszerzyć odczyt audytu o decyzje i historię z izolacją `session_hash`.

**Contract**:
- Typy: `DecisionCategory = Literal["agree_with_system", "request_source_or_verify", "consider_doc_update", "system_verdict_wrong"]`, `RoleLabel = Literal["editor", "consultant"]`, `AuditEventType = Literal["audit_created", "evaluation_completed", "evaluation_failed", "decision_saved", "decision_updated"]`, `AuditEventActor = Literal["system", "human"]`, `DecisionStatus = Literal["pending", "in_progress", "saved", "not_applicable"]`.
- Modele: `StoredClaimDecision` (`id`, `audit_id`, `claim_id`, `decision`, `justification`, `role_label`, `created_at`, `updated_at`), `StoredAuditEvent` (`id`, `audit_id`, `claim_id`, `claim_index`, `event_type`, `actor_type`, `role_label`, `payload`, `created_at`).
- Rozszerzenie modeli: `StoredAuditClaim.decision: StoredClaimDecision | None = None`, `StoredAudit.history: list[StoredAuditEvent] = Field(default_factory=list)`.
- Atomowe wpisy w `audit_events` wewnątrz istniejących `conn.transaction()`:
  - `create_audit` → `audit_created` (`actor_type='system'`, `payload={"case_ref": case_ref}`)
  - `complete_audit` → `evaluation_completed` (`actor_type='system'`, `payload={"note_verdict": note_verdict, "claims_total": total}`)
  - `fail_audit` → `evaluation_failed` (`actor_type='system'`, `payload={}` — bez surowych śladów wyjątków)
  - `fail_orphaned_audits` → `UPDATE ... RETURNING id` + wstawienie `evaluation_failed` (`actor_type='system'`, `payload={"orphaned": True}`) dla każdego przerwanego audytu.
- Nowa funkcja `upsert_claim_decision(conn, *, audit_id, claim_id, session_hash, decision, justification, role_label) -> Literal["saved", "updated"]`:
  - Wewnątrz `conn.transaction()` sprawdza istnienie i własność audytu (`is_demo = true OR session_hash = %s`), jego `status == 'completed'` (rzuca dedykowany błąd `AuditNotCompletedError` dla `409`), oraz przynależność `claim_id` do `audit_id` (rzuca `AuditNotFoundError` dla `404`).
  - Wykonuje `INSERT INTO audit_claim_decisions ... ON CONFLICT (claim_id, session_hash) DO UPDATE SET decision = EXCLUDED.decision, justification = EXCLUDED.justification, role_label = EXCLUDED.role_label, updated_at = now() RETURNING (xmax = 0) AS inserted` (lub sprawdza istnienie wiersza z `FOR UPDATE`), a następnie dopisuje `decision_saved` (przy wstawieniu) albo `decision_updated` (przy aktualizacji) do `audit_events` z `actor_type='human'`, `session_hash`, `role_label` i `payload={"decision": decision, "claim_index": claim_index}`.
- Rozszerzenie `get_audit_for_session(conn, audit_id, session_hash)`:
  - Dołącza decyzje z `audit_claim_decisions` przefiltrowane przez `audit_id = %s AND session_hash = %s` do odpowiednich `StoredAuditClaim.decision`.
  - Pobiera `audit_events` (z opcjonalnym `LEFT JOIN audit_claims` po `claim_index`) dla `audit_id = %s AND (actor_type = 'system' OR session_hash = %s)` posortowane `ORDER BY created_at ASC, id ASC`.

#### 3. Testy warstwy danych i migracji
**File**: `backend/tests/auditing/test_store_decisions.py` (nowy plik) oraz aktualizacja `backend/tests/auditing/test_store.py` (jeśli asercje wymagają dostosowania)

**Intent**: Zweryfikować migrację `0005`, więzy `CHECK` i `UNIQUE (claim_id, session_hash)`, atomowość zdarzeń systemowych, `upsert_claim_decision` (`saved` vs `updated`), izolację sesji oraz błędy `404`/`409` na prawdziwej bazie ParadeDB (`@pytest.mark.db`).

**Contract**: Pokrycie przypadków: zapis pustego/białoznakowego uzasadnienia odrzucony przez DB, zapis i aktualizacja decyzji generują kolejno `decision_saved` i `decision_updated`, dwie sesje na `is_demo=true` nie nadpisują się nawzajem i widzą wyłącznie własne decyzje oraz zdarzenia `human` + wspólne `system`, `fail_orphaned_audits` dopisuje `evaluation_failed`.

### Success Criteria:

#### Automated Verification:
- Migracja `0005` aplikuje się czysto i idempotentnie (testy DB + `backend/app/migrations.py`): `cd backend; uv run pytest tests/auditing/test_store.py tests/auditing/test_store_decisions.py`
- Linter i formatowanie backendu przechodzą bez błędów: `cd backend; uv run ruff check .; uv run ruff format --check .`
- Kontrola typów `mypy` w kontenerze Docker przechodzi bez błędów: `docker run --rm -v d:\Repos\KnowledgeOps\backend:/app:ro -w /app -e UV_PROJECT_ENVIRONMENT=/tmp/venv ghcr.io/astral-sh/uv:python3.14-bookworm-slim sh -c "uv sync --frozen --no-install-project --quiet && uv run python -m mypy --cache-dir=/tmp/.mypy_cache ."`

#### Manual Verification:
- Po restarcie kontenera `backend` (`docker compose up -d --build backend`) migracja `0005` pojawia się w `schema_migrations`, a istniejące w lokalnej bazie audyty z S-08 mają wygenerowane wpisy w `audit_events`.

**Implementation Note**: Po ukończeniu Fazy 1 i przejściu wszystkich sprawdzeń automatycznych zatrzymaj się na ręczne potwierdzenie przed przejściem do Fazy 2.

---

## Phase 2: API decyzji, wyliczany status i kontrakt OpenAPI/TS

### Overview

Wystawiamy endpoint `PUT /api/audits/{audit_id}/claims/{claim_id}/decision`, rozszerzamy `GET /api/audits/{audit_id}` o decyzje per teza, wyliczany `decision_status`, `decisions_count` oraz `history`, dodajemy testy API, synchronizujemy `backend/openapi.json` i `frontend/app/api/schema.d.ts` oraz aktualizujemy lokalny `docs/przeplyw-danych.md`.

### Changes Required:

#### 1. Schematy i endpointy w `api/audits.py`
**File**: `backend/app/api/audits.py`

**Intent**: Udostępnić walidowany endpoint zapisu/edycji decyzji per teza oraz rozszerzyć odpowiedź szczegółów audytu o decyzje, wyliczany postęp/status decyzji i uporządkowaną historię zdarzeń.

**Contract**:
- Stała `MAX_JUSTIFICATION_LENGTH = 2000`.
- `SaveClaimDecisionRequest(BaseModel)`:
  - `decision: DecisionCategory`
  - `justification: str = Field(min_length=1, max_length=MAX_JUSTIFICATION_LENGTH)` z walidatorem odrzucającym wyłącznie białe znaki (`strip()`)
  - `role_label: RoleLabel = "editor"`
- `ClaimDecisionResponse(BaseModel)`: `decision`, `justification`, `role_label`, `created_at`, `updated_at`.
- `AuditHistoryEventResponse(BaseModel)`: `event_id`, `event_type`, `actor_type`, `role_label`, `claim_id`, `claim_index`, `decision` (opcjonalnie z `payload`), `note_verdict` (opcjonalnie z `payload`), `claims_total` (opcjonalnie z `payload`), `created_at`.
- Rozszerzenie `AuditClaimResponse`: `decision: ClaimDecisionResponse | None = None`.
- Rozszerzenie `AuditDetailResponse`:
  - `decision_status: DecisionStatus` (`pending` | `in_progress` | `saved` | `not_applicable`)
  - `decisions_count: int`
  - `history: list[AuditHistoryEventResponse]`
- Czysta funkcja `compute_decision_status(status: AuditStatus, claims_total: int, decisions_count: int) -> DecisionStatus` zgodna z regułą w sekcji `Critical Implementation Details`.
- Nowy endpoint `@router.put("/audits/{audit_id}/claims/{claim_id}/decision", response_model=AuditDetailResponse)`:
  - Wymaga `AuditSessionDep` (brak/inna sesja → `404`).
  - Wywołuje `upsert_claim_decision`, mapuje `AuditNotFoundError` → `404`, `AuditNotCompletedError` → `409 Conflict`.
  - Odczytuje świeży `get_audit_for_session` i zwraca pełny `AuditDetailResponse` (`200 OK`).
  - Nigdy nie wywołuje modelu LLM ani nie loguje treści uzasadnienia do Langfuse.

#### 2. Testy endpointów API
**File**: `backend/tests/api/test_audits_decisions.py` (nowy plik)

**Intent**: Przetestować walidację wejścia, kody HTTP, przejścia `decision_status`, rejestrowanie `decision_saved` / `decision_updated` oraz izolację sesji w warstwie HTTP FastAPI.

**Contract**: Scenariusze testowe:
- `422` dla pustego/białoznakowego uzasadnienia, nieznanej kategorii decyzji lub nieznanej roli.
- `404` bez ciasteczka sesji, dla obcej sesji lub nieistniejącego `claim_id` / `claim_id` z innego audytu.
- `409` dla audytu w stanie `queued`, `running` lub `failed`.
- `200` zapis dla pierwszej z 2 tez → `decision_status == "in_progress"`, `decisions_count == 1`, zdarzenie `decision_saved` w `history`.
- `200` zapis dla drugiej z 2 tez → `decision_status == "saved"`, `decisions_count == 2`.
- `200` ponowny zapis dla tej samej tezy → nadpisuje decyzję, `decisions_count` bez zmian, dopisuje `decision_updated` w `history`.
- Ukończony audyt z `claims_total == 0` → `decision_status == "not_applicable"`, `decisions_count == 0`.

#### 3. Synchronizacja kontraktu OpenAPI i typów TypeScript
**File**: `backend/openapi.json`, `frontend/app/api/schema.d.ts`

**Intent**: Utrzymać 100% zgodności kontraktu API między backendem a frontendem zgodnie z wymogiem CI (`AGENTS.md`).

**Contract**: Wygenerować przez `cd backend; uv run python scripts/export_openapi.py` oraz `cd frontend; npm run api:types`.

#### 4. Aktualizacja lokalnego dokumentu przepływu danych
**File**: `docs/przeplyw-danych.md` (plik lokalny w `.gitignore` — bez `git add -f`)

**Intent**: Dopisać tabele `audit_claim_decisions` i `audit_events` jako dane przechowywane wyłącznie w ParadeDB (bez wysyłki do LLM ani Langfuse) oraz zaktualizować nagłówek i sekcję retencji.

**Contract**: Zaktualizować nagłówek wersji, dopisać sekcję S-09 (decyzje i historia) oraz uzupełnić listę tabel w sekcji retencji o `audits`, `audit_claims`, `audit_claim_decisions`, `audit_events`.

### Success Criteria:

#### Automated Verification:
- Wszystkie testy backendu przechodzą: `cd backend; uv run pytest`
- Linter, formatowanie i `mypy` (Docker) przechodzą bez błędów: `cd backend; uv run ruff check .; uv run ruff format --check .` oraz `mypy` w Dockerze
- Kontrakt OpenAPI i typy TS są aktualne i `frontend` przechodzi `typecheck`: `cd backend; uv run python scripts/export_openapi.py` + `cd frontend; npm run api:types; npm run typecheck`

#### Manual Verification:
- W Swagger UI (`http://127.0.0.1:8000/docs`) widoczny jest `PUT /api/audits/{audit_id}/claims/{claim_id}/decision` oraz rozszerzony schemat `AuditDetailResponse` z `decision_status`, `decisions_count` i `history`.
- Zapis decyzji przez API nie tworzy żadnego śladu w Langfuse ani nie modyfikuje żadnego dokumentu w bazie.

**Implementation Note**: Po ukończeniu Fazy 2 i przejściu wszystkich sprawdzeń automatycznych zatrzymaj się na ręczne potwierdzenie przed przejściem do Fazy 3.

---

## Phase 3: Frontend — panel decyzji (`3`), pasek CTA + arkusz `3N-D` i sekcja `Historia`

### Overview

Wdrażamy pełny interfejs decyzji redaktora i historii analizy zgodny z makietami `S3.dc.html`, `S3N.dc.html` i `S3ND.dc.html` oraz rozstrzygniętymi decyzjami projektowymi (tryb read-only + szybkie przełączenie roli dla `consultant`, brak „Sugestii systemu”, edycja zapisanej decyzji, zamiana prawego panelu na `>= 1280 px`, przyklejony dolny pasek CTA + arkusz `3N-D` poniżej `1280 px`, zwinięty `<details>` `Historia` z rozróżnieniem system/człowiek, komplet PL/EN i testy Vitest).

### Changes Required:

#### 1. Klient API i czyste funkcje pomocnicze
**File**: `frontend/app/api/audits.ts`, `frontend/app/lib/audit.ts`, `frontend/app/lib/audit.test.ts`

**Intent**: Dodać wywołanie `saveClaimDecision` (z obsługą `AbortSignal`) oraz czyste, przetestowane funkcje mapowania kategorii decyzji, statusów decyzji, formatowania zdarzeń historii i sprawdzania `isEditableTarget`.

**Contract**:
- `frontend/app/api/audits.ts`: eksport typów `DecisionCategory`, `DecisionStatus`, `ClaimDecisionResponse`, `AuditHistoryEventResponse`, `SaveClaimDecisionRequest` ze `schema.d.ts` oraz funkcja `saveClaimDecision(auditId, claimId, body, { signal }): Promise<AuditDetailResponse>`.
- `frontend/app/lib/audit.ts`:
  - Stała kolejność 4 kategorii: `DECISION_CATEGORIES = ["agree_with_system", "request_source_or_verify", "consider_doc_update", "system_verdict_wrong"] as const`.
  - Mapy etykiet i18n dla kategorii decyzji, `DecisionStatus` i typów zdarzeń `AuditHistoryEventResponse`.
  - `canSubmitDecision(category, justification, savedDecision, isSaving)`: zwraca `false`, gdy brak wybranej kategorii, puste po `.trim()` uzasadnienie, trwa zapis albo wartości są identyczne z już zapisaną decyzją.
  - `isEditableTarget(target: EventTarget | null): boolean` (ochrona skrótów klawiszowych przy `INPUT`/`TEXTAREA`/`SELECT`/`isContentEditable`).
- `frontend/app/lib/audit.test.ts`: testy Vitest dla wszystkich powyższych czystych funkcji (w tym brak domyślnej kategorii, odrzucenie samych spacji, wykrywanie niezmienionej decyzji przy edycji, `isEditableTarget`).

#### 2. Ikona osoby i rozszerzenie `PanelFrame`
**File**: `frontend/app/components/assistant/Icon.tsx`, `frontend/app/components/assistant/PanelFrame.tsx`

**Intent**: Dodać `PersonIcon` dla nagłówka panelu decyzji, dolnego paska `3N` i zdarzeń człowieka w historii oraz umożliwić użycie `PanelFrame` z wariantem `"decision"` (`340 px`, tło `bg-surface-alt`) i konfigurowalnym `wideQuery` (`(min-width: 1280px)` dla `3N-D`).

**Contract**:
- `Icon.tsx`: eksport `PersonIcon` (SVG spójny stylowo z `SystemIcon` z `S3.dc.html:26`).
- `PanelFrame.tsx`: `PanelVariant = "evidence" | "checked" | "decision"`, opcjonalny prop `wideQuery?: string` (domyślnie `WIDE_QUERY`, więc istniejące wywołania `EvidencePanel`/`CaseContextPanel` zachowują dotychczasowe zachowanie).

#### 3. Komponent panelu decyzji (`ClaimDecisionPanel`)
**File**: `frontend/app/components/audit/ClaimDecisionPanel.tsx` (nowy plik)

**Intent**: Zaimplementować formularz decyzji redaktora dla wybranej tezy (wspólny dla desktopowego prawego panelu `3` i mobilnego arkusza `3N-D`), bez wyboru domyślnego i bez linii „Sugestia systemu”.

**Contract**:
- Nagłówek z `PersonIcon`, tytułem `Decyzja redaktora`, etykietą wybranej tezy (`T{n}`) oraz (w wariancie arkusza `3N-D`) przyciskiem zamknięcia `X` (`40x40px`) i skróconym wierszem kontekstu (`T{n}` + etykieta tezy + ocena systemu).
- Gdy `role === "consultant"`:
  - Jeśli teza ma zapisaną decyzję — wyświetla ją w trybie tylko do odczytu (kategoria, uzasadnienie, etykieta roli, data).
  - Formularz edycji/zapisu jest zablokowany z czytelnym komunikatem i przyciskiem „Przełącz na rolę Redaktor” (`setRole("editor")`) oraz zastrzeżeniem, że przełącznik ról nie jest kontrolą dostępu.
- Gdy `role === "editor"`:
  - `<div role="radiogroup" aria-label={...}>` z dokładnie 4 opcjami w kolejności z PRD, bez domyślnego zaznaczenia; pod spodem pomoc `Nic nie jest wybrane z góry.` (gdy brak wyboru).
  - `<textarea rows={4}>` z etykietą `Uzasadnienie (wymagane)` i limitem `MAX_JUSTIFICATION_LENGTH` (`2000`).
  - Przycisk zapisu:
    - Nieaktywny, gdy `!canSubmitDecision(...)` — etykieta `Wybierz decyzję i wpisz uzasadnienie` (lub `Zapisano` gdy brak zmian w już zapisanej decyzji).
    - Aktywny: `Zapisz decyzję dla T{n}` (pierwszy zapis) lub `Zaktualizuj decyzję dla T{n}` (edycja zapisanej decyzji), stan ładowania podczas żądania.
  - Komunikat potwierdzenia zapisu (z ikoną `SupportedIcon`, `role="status"`) oraz obsługa błędu API (`role="alert"`, bez surowych wyjątków, zachowanie wpisanego tekstu).
  - Zastrzeżenie pod przyciskiem: `Zapis nie zmienia ani nie publikuje dokumentacji. Rola „Redaktor” bez weryfikacji tożsamości.`
- Synchronizacja stanu formularza przy zmianie `claim.claim_id` (reset do zapisanej decyzji danej tezy lub pustego stanu) oraz anulowanie żądania w locie przez `AbortController` przy odmontowaniu / zmianie tezy.

#### 4. Komponent historii analizy (`AuditHistoryDetails`)
**File**: `frontend/app/components/audit/AuditHistoryDetails.tsx` (nowy plik)

**Intent**: Wyświetlić zwiniętą sekcję `<details>` `Historia` bezpośrednio nad `Jak powstała ta analiza`, prezentującą wyłącznie rzeczywiste zdarzenia z `audit.history` z wyraźnym rozróżnieniem systemu i człowieka.

**Contract**:
- Domyślnie zwinięty `<details>` (identyczny styl obramowania/nagłówka jak `AuditPreparationDetails`).
- W `<summary>`: tytuł `Historia` oraz rzeczywiste podsumowanie (`{N} zdarzeń · ostatnie: {etykieta ostatniego zdarzenia}` — bez słowa „szkic”).
- Wewnątrz: chronologiczna lista zdarzeń (`<ol>`), gdzie każdy wpis zawiera ikonę (`SystemIcon` dla `actor_type === "system"`, `PersonIcon` dla `actor_type === "human"`), słowny opis aktora (`System` vs `Redaktor` / `Konsultant`), nazwę zdarzenia (dla decyzji z numerem tezy `T{n}` i etykietą wybranej kategorii), oraz sformatowany czas.

#### 5. Integracja w `AuditResultView` i `audit-detail.tsx`
**File**: `frontend/app/components/audit/AuditResultView.tsx`, `frontend/app/routes/audit-detail.tsx`

**Intent**: Podłączyć aktualizację stanu audytu po zapisie decyzji, wskaźniki decyzji na liście tez i w nagłówku (słowo + ikona), stały prawy panel na `>= 1280 px` (z tymczasową zamianą na `EvidencePanel`/`CaseContextPanel`), przyklejony dolny pasek CTA + arkusz `3N-D` na `< 1280 px` oraz sekcję `AuditHistoryDetails` nad `AuditPreparationDetails`.

**Contract**:
- `audit-detail.tsx`: przekazuje `onAuditChange={setAudit}` do `AuditResultView`.
- `AuditResultView.tsx`:
  - W nagłówku sprawy obok `NoteVerdictPill` (oddzielnie od oceny systemu!) pokazuje zbiorczy status decyzji (`decision_status` + `{decisions_count}/{claims_total}` słowem i ikoną, np. `Zapisana` z `SupportedIcon`, `Decyzje: 1/2` z `PersonIcon`, `Do decyzji` z `PersonIcon`; pomijany dla `not_applicable` lub opisany jako brak tez do decyzji).
  - Na każdym przycisku tezy w liście `Tezy z notatki` pokazuje czytelny status decyzji dla tej tezy (np. ikona `SupportedIcon` + `Zapisana` vs neutralne `Bez decyzji`, oddzielone od `ClaimVerdictPill`).
  - Breakpoint desktopowy decyzji: `useMediaQuery("(min-width: 1280px)")`:
    - Gdy `isXl`: jeśli otwarty jest `EvidencePanel` lub `CaseContextPanel`, renderuje się ten panel w prawym slocie (jego zamknięcie `X`/`Escape` wraca do panelu decyzji); w przeciwnym razie (gdy `selectedClaim !== null`) w prawym slocie renderuje się stały `<aside className="w-[340px] ...">` z `ClaimDecisionPanel`.
    - Gdy `!isXl`: dolny margines (`pb-[104px]`) pod przyklejony dolny pasek CTA (`height: 48px`, `bg-primary`, po lewej `PersonIcon` + `Decyzja dla T{n}`, po prawej status `nie zapisano` / `zapisano` + szewron). Kliknięcie otwiera `activePanel = { kind: "decision" }` renderowany w `<PanelFrame variant="decision" wideQuery="(min-width: 1280px)">` jako arkusz `3N-D` z przywracaniem fokusu na przycisk paska po zamknięciu.
  - `AuditHistoryDetails` umieszczony bezpośrednio nad `AuditPreparationDetails` w kolumnie środkowej.
  - Guard `isEditableTarget(event.target)` przy globalnych skrótach klawiszowych (z wyjątkiem `Escape` zamykającego aktywny overlay/arkusz).

#### 6. Tłumaczenia PL/EN
**File**: `frontend/app/i18n/pl.ts`, `frontend/app/i18n/en.ts`

**Intent**: Zapewnić kompletne tłumaczenia PL i EN dla wszystkich nowych etykiet formularza decyzji, 4 kategorii, trybu roli `consultant`, zastrzeżenia MVP, paska `3N`, arkusza `3N-D`, statusów decyzji i wpisów `Historia`.

**Contract**: Wszystkie nowe klucze w `pl.ts` mają swoje odpowiedniki w `en.ts` (weryfikowane przez `npm run typecheck`). Cytowane fragmenty dokumentów i treść notatki pozostają nieprzetłumaczone.

### Success Criteria:

#### Automated Verification:
- Linter, formatowanie, typecheck, testy Vitest i build frontendu przechodzą bez błędów: `cd frontend; npm run lint; npm run format:check; npm run typecheck; npm test; npm run build`
- Pełna suita backendu (`ruff`, `mypy` w Dockerze, `pytest`) nadal przechodzi bez regresji.

#### Manual Verification:
- Ekran `3` przy `1280 px` i `1440 px`: prawy panel decyzji (`340 px`) jest widoczny obok oceny tezy, brak wyboru domyślnego i brak „Sugestii systemu”; otwarcie dowodu lub kontekstu sprawy tymczasowo go zastępuje, a `X`/`Escape` przywraca panel decyzji.
- Przełącznik ról: w roli `Konsultant` formularz jest tylko do odczytu z przyciskiem „Przełącz na rolę Redaktor” i komunikatem o braku kontroli dostępu; po przełączeniu na `Redaktor` można zapisać i edytować decyzję dla każdej tezy (także popartej).
- Zapis bez kategorii lub z pustym uzasadnieniem jest zablokowany w UI (i odrzucany `422` przez API); po zapisaniu decyzji dla wszystkich tez status analizy zmienia się na `Zapisana`, a po odświeżeniu strony decyzje i historia pozostają utrwalone.
- `Historia` (domyślnie zwinięta nad `Jak powstała ta analiza`) pokazuje wyłącznie rzeczywiste zdarzenia (`audit_created`, `evaluation_completed`, `decision_saved`, `decision_updated`) z rozróżnieniem systemu i człowieka.
- Ekran `3N` i arkusz `3N-D` przy `390 px`: przyklejony dolny pasek CTA otwiera arkusz modalny z trapem fokusu i `Escape`, zero przewijania w poziomie (`scrollWidth <= innerWidth`), pełny przepływ zapisu działa bez utraty funkcji.
- Przełącznik języka `PL`/`EN` przełącza wszystkie nowe etykiety interfejsu (bez tłumaczenia treści zgłoszenia i cytatów).

**Implementation Note**: Po ukończeniu Fazy 3 i przejściu wszystkich sprawdzeń automatycznych zatrzymaj się na ręczne potwierdzenie przed przejściem do `/10x-impl-review`.

---

## Testing Strategy

### Unit Tests:
- Backend: `compute_decision_status` (wszystkie kombinacje `queued`/`running`/`failed`/`completed` + `claims_total == 0` + częściowe i pełne decyzje), walidatory `SaveClaimDecisionRequest`.
- Frontend (Vitest): `DECISION_CATEGORIES` kolejność, `canSubmitDecision` (brak wyboru, same spacje, edycja bez zmian, edycja ze zmianą), `isEditableTarget`, formatowanie podsumowania historii.

### Integration Tests:
- Backend DB (`@pytest.mark.db`): migracja `0005`, `CHECK` pustego uzasadnienia, `UNIQUE (claim_id, session_hash)` dla 2 sesji na `is_demo=true`, atomowe zdarzenia w `create_audit`/`complete_audit`/`fail_audit`/`fail_orphaned_audits`, `upsert_claim_decision` (`saved` → `updated`).
- Backend API (`httpx`/`TestClient`): pełny przepływ `PUT` + `GET`, kody `200`/`404`/`409`/`422`, izolacja sesji, `claims_total == 0` → `not_applicable`.

### Manual Testing Steps:
1. Otworzyć ukończony audyt z co najmniej 2 tezami w oknie `1440 px` i `1280 px`; sprawdzić brak domyślnego wyboru, przełączenie `Konsultant` ↔ `Redaktor`, zapis decyzji dla obu tez, edycję pierwszej decyzji oraz przejście statusu do `Zapisana`.
2. Otworzyć `EvidencePanel` i `CaseContextPanel` na `1280 px`, zamknąć przez `X` i `Escape`, potwierdzić powrót do panelu decyzji.
3. Rozwinąć `Historia` nad `Jak powstała ta analiza`, zweryfikować obecność zdarzeń utworzenia, oceny systemu, `decision_saved` i `decision_updated` z właściwymi ikonami i etykietami.
4. Przełączyć okno na `390 px`, otworzyć arkusz `3N-D` z dolnego paska, zapisać/edytować decyzję, sprawdzić `document.documentElement.scrollWidth <= window.innerWidth`.
5. Przełączyć język na `EN`, zweryfikować brak brakujących kluczy i zachowanie oryginalnego języka cytatów.

## Performance Considerations

- Zapis decyzji to pojedyncza krótka transakcja SQL (`UPSERT` + `INSERT`) na indeksowanych kolumnach `(claim_id, session_hash)` i `(audit_id, created_at, id)` — czas odpowiedzi < 50 ms, brak wpływu na limit puli połączeń (`max_size=5`) i brak wywołań sieciowych do LLM/Langfuse.
- Odczyt `GET /api/audits/{audit_id}` wykonuje 2 dodatkowe, małe zapytania po indeksie `audit_id` (decyzje i zdarzenia) w ramach tego samego połączenia z puli.

## Migration Notes

- Migracja `0005_audit_decisions_and_history.sql` jest w pełni addytywna (nie modyfikuje `audits` ani `audit_claims`) i zawiera jednorazowy backfill `audit_events` dla istniejących wierszy `audits`.
- Wycofanie (gdyby było potrzebne lokalnie) ogranicza się do `DROP TABLE audit_events; DROP TABLE audit_claim_decisions;` i usunięcia wpisu `0005` z `schema_migrations`, bez utraty danych z `audits`/`audit_claims`.

## References

- Related research: `context/changes/editor-decision-and-history/research.md`
- PRD: `context/foundation/prd.md` (`US-02`, `FR-009`, `FR-021`, `FR-011`)
- Roadmap: `context/foundation/roadmap.md` (`S-09`)
- Mockups: `design/mockups/canvas/S3.dc.html`, `design/mockups/canvas/S3N.dc.html`, `design/mockups/canvas/S3ND.dc.html`
- Prior audit schema & store: `backend/migrations/0004_audits.sql`, `backend/app/auditing/store.py`
- Prior UI & sheet frame: `frontend/app/components/audit/AuditResultView.tsx`, `frontend/app/components/assistant/PanelFrame.tsx`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Migracja ParadeDB (`0005`) i warstwa `store.py`

#### Automated

- [x] 1.1 Migracja `0005` aplikuje się czysto i idempotentnie (testy DB + `backend/app/migrations.py`): `cd backend; uv run pytest tests/auditing/test_store.py tests/auditing/test_store_decisions.py` — 55bdc76
- [x] 1.2 Linter i formatowanie backendu przechodzą bez błędów: `cd backend; uv run ruff check .; uv run ruff format --check .` — 55bdc76
- [x] 1.3 Kontrola typów `mypy` w kontenerze Docker przechodzi bez błędów — 55bdc76

#### Manual

- [x] 1.4 Po restarcie kontenera `backend` migracja `0005` pojawia się w `schema_migrations`, a istniejące w lokalnej bazie audyty z S-08 mają wygenerowane wpisy w `audit_events` — 55bdc76

### Phase 2: API decyzji, wyliczany status i kontrakt OpenAPI/TS

#### Automated

- [x] 2.1 Wszystkie testy backendu przechodzą: `cd backend; uv run pytest` — b7b48da
- [x] 2.2 Linter, formatowanie i `mypy` (Docker) przechodzą bez błędów — b7b48da
- [x] 2.3 Kontrakt OpenAPI i typy TS są aktualne i `frontend` przechodzi `typecheck`: `export_openapi.py` + `npm run api:types; npm run typecheck` — b7b48da

#### Manual

- [x] 2.4 W Swagger UI widoczny jest `PUT /api/audits/{audit_id}/claims/{claim_id}/decision` oraz rozszerzony schemat `AuditDetailResponse` z `decision_status`, `decisions_count` i `history` — b7b48da
- [x] 2.5 Zapis decyzji przez API nie tworzy żadnego śladu w Langfuse ani nie modyfikuje żadnego dokumentu w bazie — b7b48da

### Phase 3: Frontend — panel decyzji (`3`), pasek CTA + arkusz `3N-D` i sekcja `Historia`

#### Automated

- [x] 3.1 Linter, formatowanie, typecheck, testy Vitest i build frontendu przechodzą bez błędów: `cd frontend; npm run lint; npm run format:check; npm run typecheck; npm test; npm run build` — 3f39fc7
- [x] 3.2 Pełna suita backendu (`ruff`, `mypy` w Dockerze, `pytest`) nadal przechodzi bez regresji — 3f39fc7

#### Manual

- [x] 3.3 Ekran `3` przy `1280 px` i `1440 px`: prawy panel decyzji (`340 px`) obok oceny tezy, brak wyboru domyślnego i brak „Sugestii systemu”, tymczasowa zamiana przy otwarciu dowodu/kontekstu i powrót po `X`/`Escape` — 3f39fc7
- [x] 3.4 Przełącznik ról: tryb tylko do odczytu + przycisk „Przełącz na rolę Redaktor” dla `Konsultant`, zapis i edycja decyzji dla każdej tezy w roli `Redaktor` — 3f39fc7
- [x] 3.5 Zapis bez kategorii lub uzasadnienia jest zablokowany; po zapisaniu decyzji dla wszystkich tez status analizy zmienia się na `Zapisana` i przetrwa odświeżenie strony — 3f39fc7
- [x] 3.6 `Historia` (domyślnie zwinięta nad `Jak powstała ta analiza`) pokazuje wyłącznie rzeczywiste zdarzenia z rozróżnieniem systemu i człowieka — 3f39fc7
- [x] 3.7 Ekran `3N` i arkusz `3N-D` przy `390 px`: przyklejony dolny pasek CTA otwiera arkusz modalny z trapem fokusu i `Escape`, zero przewijania w poziomie — 3f39fc7
- [x] 3.8 Przełącznik języka `PL`/`EN` przełącza wszystkie nowe etykiety interfejsu bez tłumaczenia treści zgłoszenia i cytatów — 3f39fc7
