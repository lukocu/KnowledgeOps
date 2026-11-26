# S-08: Analiza rozwiązanej sprawy (`resolved-case-audit`) — Plan implementacji

## Overview

Wdrażamy pełny przepływ **analizy rozwiązanej sprawy (S-08)**: ręczne przekazanie opisu zgłoszenia i notatki z rozwiązaniem (ekran `2`), wykonanie wieloetapowego grafu audytu w tle z utrwalaniem stanu w Postgresie i podglądem postępu na żywo przetrwającym odświeżenie strony (ekran `2P`) oraz podgląd oceny systemu dla każdej tezy i całej notatki wraz z fragmentami dowodów i kontekstem sprawy (ekrany `3` i `3N` w tym `390 px`). Panel decyzji redaktora i historia (`FR-009`, `FR-021`) pozostają w `S-09`, a lista analiz (`FR-010`) w `S-10`.

## Current State Analysis

- **Gotowe fundamenty backendu**:
  - Anonimowa sesja w ciasteczku `kops_session` ([backend/app/session.py](file:///d:/Repos/KnowledgeOps/backend/app/session.py#L14-L59)) z SHA-256 `session_hash` w bazie i `404` bez tworzenia ciasteczka na `GET`.
  - Wyszukiwanie BM25 ParadeDB po wielu zestawach fragmentów: `resolve_active_chunk_set_ids()` + `search_bm25()` z `ANY(%(chunk_set_ids)s)` ([backend/app/retrieval.py](file:///d:/Repos/KnowledgeOps/backend/app/retrieval.py#L185-L233)) oraz gotowe endpointy dowodów `GET /api/evidence` i `GET /api/documents` ([backend/app/api/evidence.py](file:///d:/Repos/KnowledgeOps/backend/app/api/evidence.py#L46-L94)).
  - Reużywalne prymitywy z `answering/`: `locate_quote()` ([backend/app/answering/nodes.py](file:///d:/Repos/KnowledgeOps/backend/app/answering/nodes.py#L112-L125)), `Verdict = Literal["supported", "contradicted", "insufficient"]` ([backend/app/answering/schemas.py](file:///d:/Repos/KnowledgeOps/backend/app/answering/schemas.py#L11)), wzorzec `reasoning`-przed-`verdict`, deterministyczny strażnik zakresu `resolve_conflict_type()` ([backend/app/answering/nodes.py](file:///d:/Repos/KnowledgeOps/backend/app/answering/nodes.py#L247-L266)), fabryka modelu `make_chat_model()` ([backend/app/answering/model.py](file:///d:/Repos/KnowledgeOps/backend/app/answering/model.py#L60-L79)) oraz wersjonowanie promptów `*.md` przez SHA-256.
  - Migracje `0001`–`0003` są niezmienne (weryfikowane przez SHA-256 w [backend/app/migrations.py](file:///d:/Repos/KnowledgeOps/backend/app/migrations.py#L39-L61)); pula połączeń `create_pool()` ma `max_size=5` ([backend/app/db.py](file:///d:/Repos/KnowledgeOps/backend/app/db.py#L20-L29)).
- **Luki do uzupełnienia**:
  - Brak tabel audytu (`0004_audits.sql`) oraz brak mechanizmu wykonywania zadań w tle w `lifespan`.
  - `require_session()` ([backend/app/session.py](file:///d:/Repos/KnowledgeOps/backend/app/session.py#L54)) ma zaszyty komunikat `404` `"Nie znaleziono odpowiedzi"`, a `run_config()` ([backend/app/observability.py](file:///d:/Repos/KnowledgeOps/backend/app/observability.py#L69-L93)) ma zaszyte `run_name="answer"` i prompty z `answering`.
  - Frontend ma tylko trasy `/` i `/odpowiedz/:id` ([frontend/app/routes.ts](file:///d:/Repos/KnowledgeOps/frontend/app/routes.ts#L8-L13)), jedną pozycję w `NavRail`, brak tokenów statusów (`supported`/`partial`/`insufficient`) w [frontend/app/app.css](file:///d:/Repos/KnowledgeOps/frontend/app/app.css#L4-L35) oraz brak kluczy i18n dla audytu.

## Desired End State

- Użytkownik przechodzi z `NavRail` (lub z linku w `AbstentionView` na ekranie `1C`) na `/audyt` (ekran `2`), widzi ostrzeżenie o publicznym demo i ręcznym przekazaniu, wpisuje opcjonalny identyfikator sprawy, wymagany opis zgłoszenia i notatkę z rozwiązaniem (do 4000 znaków) i uruchamia analizę (`POST /api/audits` → `202`).
- Aplikacja przekierowuje na `/audyt/:id`: w trakcie analizy pokazuje rzeczywiste etapy postępu (ekran `2P`) odpytywane przez `GET /api/audits/:id`. Odświeżenie lub ponowne otwarcie adresu nie przerywa analizy ani nie gubi postępu; restart backendu oznacza przerwane analizy jako `failed` z czytelnym komunikatem.
- Po zakończeniu ekran `3` (i `3N` na `390 px` bez przewijania w poziomie) pokazuje:
  - ocenę całej notatki (`● Pełne pokrycie` / `◐ Częściowe pokrycie` / `✕ Sprzeczność` / `○ Niewystarczające dowody`) wyliczoną deterministycznie z ocen tez;
  - tekst notatki z podświetlonymi, dosłownymi fragmentami (`T1`, `T2`, …) i pionową listę tez `<button aria-pressed>` ze zwięzłą treścią tezy i pigułką oceny (`● Poparta` / `✕ Sprzeczność` / `○ Niewystarczające dowody`);
  - przycisk `Kontekst sprawy` otwierający `PanelFrame` (panel boczny na desktopie / arkusz od dołu na `390 px`) z polami `FR-007` (`problem`, `environment`, `solution`, `constraints`, `missing_info`) oraz treścią opisu zgłoszenia;
  - kolumnę `OCENA SYSTEMU · automatyczna, nie jest decyzją` z uzasadnieniem, sprawdzonym zakresem (w tym `chunk_set_ids` i oznaczeniem `synthetic@v1`, gdy `include_synthetic=True`), najbliższym/cytowanym fragmentem i przyciskami `Pokaż szerszy kontekst` / `Otwórz cały dokument` otwierającymi `EvidencePanel`;
  - zwiniętą sekcję `Jak powstała ta analiza` (`FR-020`) wyłącznie z rzeczywistymi danymi przebiegu.
- Wszystkie 12 przypadków pilotażowych z [docs/pilotaz-audytu-techqa.md](file:///d:/Repos/KnowledgeOps/docs/pilotaz-audytu-techqa.md) przechodzą przez graf i zostają ręcznie zweryfikowane, a [docs/przeplyw-danych.md](file:///d:/Repos/KnowledgeOps/docs/przeplyw-danych.md) opisuje nowy przepływ danych audytu.

### Key Discoveries:

- Brak `langgraph-checkpoint-postgres` w `pyproject.toml` i zasada `AGENTS.md` („nie dodawaj zależności bez decyzji”) → uzgodniono utrwalanie stanu etapów i wyników bezpośrednio w tabelach domenowych `0004_audits.sql` + `asyncio.Task` zarządzany w `lifespan`.
- `0001`–`0003` są niezmienne i bez FK z tabel wyników do `snapshots`/`documents`/`chunks` (reimport kasuje migawkę kaskadowo) — `0004_audits.sql` musi zachować tę samą konwencję.
- `EvidencePanel.tsx` i `PanelFrame.tsx` są bezpośrednio reużywalne dla dowodów i `Kontekstu sprawy`; drobny props `initialMode?: "window" | "document"` w `EvidencePanel` pozwala przyciskowi `Otwórz cały dokument` otwierać od razu zakładkę pełnego dokumentu.
- Makiety `S3.dc.html` i `S3N.dc.html` stosują pionową listę `<button aria-pressed>` (nie poziome zakładki), co rozwiązuje decyzję otwartą #5 dla kilkunastu tez przez przewijanie `min-h-0 overflow-y-auto`.

## What We're NOT Doing

- **Panel decyzji redaktora, 4 kategorie decyzji, „Sugestia systemu”, dolna belka `S3N-D` i `Historia` (`FR-009`, `FR-021`)** — odroczone do `S-09` (`editor-decision-and-history`).
- **Lista analiz, filtry, przykłady demo i okruszek/link `Analizy i decyzje` (`FR-010`)** — odroczone do `S-10` (`analyses-list`); nie dodajemy martwych linków.
- **Pomiar końcowy, macierz pomyłek i progi zgodności audytu (`FR-015`)** — odroczone do `S-11` (`audit-evaluation`).
- **Instalacja `langgraph-checkpoint-postgres`, Redis/Celery ani osobnej kolejki zadań** — poza MVP i niezgodne z decyzją D1.
- **Integracja z systemem zgłoszeń, edycja/publikacja dokumentacji, wyszukiwanie w internecie, logowanie/konta, ciemny motyw** — poza zakresem MVP (`AGENTS.md`, `prd.md`).

## Implementation Approach

1. **Jedna pula DB, krótkie transakcje, brak blokowania podczas LLM**: jak w `answers.py`, połączenie z `app.state.pool` (`max_size=5`) jest pobierane wyłącznie na czas zapytań SQL (zapis etapu, `search_bm25`, zapis wyników tez i finalizacja), nigdy na czas wywołań LLM.
2. **Wieloetapowy, deterministyczny graf LangGraph (`backend/app/auditing/`)**: `extract` (FR-007 + lista tez z dosłownym `source_excerpt`, zwięzłym `claim_text` i `search_query` + deterministyczna walidacja `locate_quote()`) → `retrieve` (równoległe wyszukiwanie BM25 per teza z `resolve_active_chunk_set_ids()` i `asyncio.Semaphore`) → `verify` (równoległa ocena każdej tezy osobno z `reasoning`-przed-`verdict`, `locate_quote()` dla cytatu z dokumentu, strażnikiem zakresu i bezpieczną degradacją pojedynczej tezy do `insufficient` przy błędzie/timeoucie LLM) → `aggregate` (czysta funkcja Pythona mapująca oceny tez na 4-stanową ocenę notatki).
3. **Przewidywalny cykl życia w tle**: `POST /api/audits` zapisuje wiersz `audits` ze statusem `queued`, uruchamia `asyncio.Task` w rejestrze przypiętym do `app.state.audit_tasks` (z budżetem `audit_deadline_s` i `flush_traces()` w `finally` pod `CancelScope(shield=True)`) i zwraca `202` z `audit_id`. Przy starcie `lifespan` oznacza osierocone wiersze `queued`/`running` jako `failed`; przy zamykaniu anuluje aktywne zadania.
4. **Przygotowanie schematu pod `S-09` i `S-10` bez nadmiarowego kodu**: `audits` i `audit_claims` mają stabilne klucze (`audit_id uuid`, `claim_id uuid`, `claim_index smallint`, `is_demo boolean NOT NULL DEFAULT false`, `case_ref text`) tak, aby `S-09` i `S-10` mogły dołożyć tabele decyzji/historii w `0005_*.sql` bez przebudowy `0004_audits.sql`.

## Critical Implementation Details

- **Timing & lifecycle**: Rejestr zadań w tle musi przechować silne referencje do `asyncio.Task` w `app.state.audit_tasks` (set zadań z `add_done_callback(tasks.discard)`), aby GC Pythona nie usunął działającego zadania w trakcie lotu. Czyszczenie osieroconych audytów przy starcie `lifespan` musi być odporne na niedostępność bazy przy starcie (tak jak `pool.open(wait=False)` w [backend/app/main.py](file:///d:/Repos/KnowledgeOps/backend/app/main.py#L28-L29) — zalogować ostrzeżenie i nie blokować uruchomienia API).
- **State sequencing**: Po każdym ukończonym etapie grafu (`extract`, każda teza w `retrieve`, `verify`, `aggregate`) aktualizujemy postęp w `audits` (`stage`, `claims_total`, `claims_done`, `status`) i zapisujemy wyniki tez w `audit_claims` przed ustawieniem `status='completed'`, żeby polling `GET /api/audits/:id` nigdy nie zobaczył stanu `completed` bez kompletu tez.
- **User experience spec**: `EvidencePanel` i `CaseContextPanel` współdzielą prawy slot `PanelFrame` (otwarcie jednego zamyka drugie). Na ekranie `3` brak dowodu jest zawsze szary (`--color-insufficient-*`), nigdy czerwony, a każdy status ma jednocześnie słowo i ikonę.

---

## Phase 1: Migracja `0004_audits.sql`, repozytorium audytów i wspólne poprawki backendu

### Overview

Tworzymy trwały model danych audytu w Postgresie (`0004_audits.sql`), warstwę zapisu/odczytu postępu i wyników (`audit_store.py`) oraz usuwamy dwa sprzężenia z istniejących modułów (`session.py`, `observability.py`) i dodajemy ustawienia limitów audytu w `settings.py`.

### Changes Required:

#### 1. Migracja schematu audytu
**File**: `backend/migrations/0004_audits.sql`
**Intent**: Dodać tabele `audits` i `audit_claims` do przechowywania wejścia sprawy, rzeczywistego postępu etapów, wyodrębnionego kontekstu `FR-007`, ocen tez `FR-008`, oceny całej notatki i konfiguracji przebiegu — bez modyfikowania `0001`–`0003` i bez FK do tabel migawek.
**Contract**:
- Tabela `audits`: `id uuid PRIMARY KEY`, `session_hash text NOT NULL`, `is_demo boolean NOT NULL DEFAULT false`, `case_ref text`, `case_description text NOT NULL`, `resolution_note text NOT NULL`, `status text NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed'))`, `stage text NOT NULL CHECK (stage IN ('queued', 'extracting', 'retrieving', 'verifying', 'aggregating', 'completed', 'failed'))`, `claims_total integer NOT NULL DEFAULT 0`, `claims_done integer NOT NULL DEFAULT 0`, `note_verdict text CHECK (note_verdict IN ('full', 'partial', 'contradiction', 'insufficient'))`, `case_context jsonb`, `snapshot_id text NOT NULL`, `chunk_set_ids text[] NOT NULL`, `config jsonb NOT NULL`, `error text`, `trace_id text`, `duration_ms integer`, `created_at timestamptz NOT NULL DEFAULT now()`, `updated_at timestamptz NOT NULL DEFAULT now()`, `completed_at timestamptz`.
- Tabela `audit_claims`: `id uuid PRIMARY KEY`, `audit_id uuid NOT NULL REFERENCES audits(id) ON DELETE CASCADE`, `claim_index smallint NOT NULL`, `claim_label text NOT NULL`, `claim_text text NOT NULL`, `source_excerpt text NOT NULL`, `source_start integer`, `source_end integer`, `search_query text NOT NULL`, `verdict text NOT NULL CHECK (verdict IN ('supported', 'contradicted', 'insufficient'))`, `rationale text NOT NULL`, `scope_note text`, `evidence jsonb NOT NULL DEFAULT '[]'::jsonb`, `checked_docs jsonb NOT NULL DEFAULT '[]'::jsonb`, `error text`, `UNIQUE (audit_id, claim_index)`.
- Indeks `audits_session_created_idx ON audits (session_hash, created_at DESC)` oraz `audit_claims_audit_idx ON audit_claims (audit_id, claim_index)`.

#### 2. Repozytorium audytów
**File**: `backend/app/auditing/store.py` (nowy moduł)
**Intent**: Udostępnić funkcje SQL do tworzenia audytu (`create_audit`), aktualizacji etapu i liczników postępu (`update_audit_progress`), atomowego zapisu końcowych tez i oceny notatki (`complete_audit`), oznaczania błędu (`fail_audit`), czyszczenia osieroconych audytów przy starcie (`fail_orphaned_audits`) oraz odczytu audytu z tezami w ramach `session_hash` (`get_audit_for_session`).
**Contract**: Wszystkie operacje przyjmują `AsyncConnection` (bez trzymania połączenia poza zapytaniem SQL). `get_audit_for_session(conn, audit_id, session_hash)` zwraca `None`, gdy rekord nie istnieje lub należy do innej sesji (albo `is_demo=false` z innym `session_hash`). `fail_orphaned_audits(conn, reason)` aktualizuje wiersze `status IN ('queued', 'running')` na `status='failed', stage='failed', error=reason` i zwraca liczbę zaktualizowanych wierszy.

#### 3. Uogólnienie `session.py`, `observability.py` i `settings.py`
**File**: `backend/app/session.py`, `backend/app/observability.py`, `backend/app/settings.py`
**Intent**: Usunąć zaszyte założenia z przepływu pytań i dodać parametry konfiguracyjne audytu bez łamania istniejących testów `answers`.
**Contract**:
- `backend/app/session.py`: zmienić domyślny komunikat `404` w `require_session()` na neutralny (np. `"Nie znaleziono zasobu"` — lub zachować istniejący kontrakt przez `make_require_session(detail)` z zachowaniem `"Nie znaleziono odpowiedzi"` dla `ExistingSessionDep` i osobnym `AuditSessionDep` z `"Nie znaleziono analizy"`, aby nie złamać istniejących testów `answers`).
- `backend/app/observability.py`: rozszerzyć `run_config()` o opcjonalne parametry `run_name: str = "answer"`, `prompt_versions_map: dict[str, str] | None = None`, `extra_metadata: dict[str, object] | None = None` (domyślne wywołanie z `answers.py` zachowuje 100% dotychczasowego zachowania; nadal bez `session_hash`).
- `backend/app/settings.py`: dodać `audit_k: int = 8`, `audit_deadline_s: float = 90`, `audit_claim_concurrency: int = 3`, `audit_max_claims: int = 12`.

#### 4. Testy Fazy 1
**File**: `backend/tests/test_audit_store.py`, `backend/tests/test_observability.py` (rozszerzenie)
**Intent**: Zweryfikować poprawność migracji `0004_audits.sql`, cyklu życia wiersza `audits`/`audit_claims`, izolacji sesji, `fail_orphaned_audits()` oraz parametryzowanego `run_config()`.
**Contract**: Testy DB oznaczone `@pytest.mark.db`; testy `observability` i `settings` działają bez bazy.

### Success Criteria:

#### Automated Verification:
- Migracja `0004_audits.sql` stosuje się idempotentnie: `cd backend; uv run python -m app.cli migrate`
- Testy Fazy 1 i brak regresji przechodzą: `cd backend; uv run pytest tests/test_audit_store.py tests/test_observability.py tests/test_answers_api.py`
- Kontrole jakości backendu przechodzą: `cd backend; uv run ruff check .; uv run ruff format --check .; uv run python -m mypy .`

#### Manual Verification:
- Brak (weryfikacja automatyczna wyczerpuje Fazę 1).

**Implementation Note**: Po przejściu weryfikacji automatycznej Fazy 1 przejdź do Fazy 2.

---

## Phase 2: Graf audytu LangGraph (`backend/app/auditing/`) i deterministyczne reguły

### Overview

Implementujemy rdzeń domenowy audytu: schematy wejścia/wyjścia, wersjonowane prompty `*.md`, 4-etapowy graf LangGraph (`extract` → `retrieve` → `verify` → `aggregate`), deterministyczną walidację cytatów/spanów i zakresu oraz pełny zestaw testów jednostkowych z wstrzykiwanym `BaseChatModel`.

### Changes Required:

#### 1. Schematy domenowe i prompt loader
**File**: `backend/app/auditing/schemas.py`, `backend/app/auditing/prompts/__init__.py`, `backend/app/auditing/prompts/extract.md`, `backend/app/auditing/prompts/verify_claim.md`
**Intent**: Zdefiniować ścisłe modele Pydantic dla wyodrębnienia kontekstu `FR-007` i tez oraz dla 3-stanowej oceny pojedynczej tezy `FR-008`, wraz z wersjonowaniem promptów przez 12-znakowy prefiks SHA-256 (identycznie jak w `answering/prompts/`).
**Contract**:
- `CaseContext`: `problem: str | None`, `environment: str | None`, `solution: str | None`, `constraints: list[str]`, `missing_info: list[str]` (wszystkie pola jawne w `strict=True`, bez pomijania kluczy — wzorzec AI Devs 4 `01_01_structured`).
- `ExtractedClaim`: `claim_label: str` (krótka etykieta na listę tez), `claim_text: str` (zwięzła, weryfikowalna teza), `source_excerpt: str` (dosłowny fragment z notatki), `search_query: str` (czyste słowa kluczowe dla BM25 bez szumu narracyjnego — wzorzec `02_02_hybrid_rag`).
- `ExtractOutput`: `case_context: CaseContext`, `claims: list[ExtractedClaim]`.
- `ClaimVerdictOutput`: `reasoning: str` (przed `verdict`), `verdict: Literal["supported", "contradicted", "insufficient"]`, `scope_relation: Literal["same_scope", "different_scope", "unclear"]`, `scope_note: str | None`, `evidence_chunk_id: str | None`, `evidence_quote: str | None`.
- `NoteVerdict = Literal["full", "partial", "contradiction", "insufficient"]`.
- Prompty `extract.md` i `verify_claim.md` po angielsku (zgodnie z `FR-018` i korpusem TechQA), z jawnymi regułami: notatka nie jest traktowana jako prawda; brak wyniku nie jest sprzecznością; sprzeczność tylko przy tym samym zakresie (produkt, wersja, kontekst); `evidence_quote` musi być dosłownym cytatem z wybranego fragmentu.

#### 2. Deterministyczne reguły domenowe i graf LangGraph
**File**: `backend/app/auditing/rules.py`, `backend/app/auditing/graph.py`
**Intent**: Wydzielić czyste, deterministyczne funkcje domenowe (walidacja spanów w notatce, walidacja cytatów z bazy, strażnik zakresu dla sprzeczności, agregacja oceny notatki) oraz złożyć 4-węzłowy graf LangGraph raportujący rzeczywiste etapy przez callback postępu.
**Contract**:
- `aggregate_note_verdict(verdicts: Sequence[Verdict]) -> NoteVerdict` (czysta funkcja Pythona):
  - `len == 0` lub wszystkie `insufficient` → `"insufficient"`;
  - co najmniej jedna `contradicted` → `"contradiction"`;
  - wszystkie `supported` → `"full"`;
  - co najmniej jedna `supported` i co najmniej jedna `insufficient` → `"partial"`.
- `resolve_claim_verdict(raw: ClaimVerdictOutput, candidates: list[RetrievedChunk]) -> ResolvedClaimEvidence`:
  - Weryfikuje `evidence_chunk_id` w `candidates` i dosłowność `evidence_quote` przez `locate_quote()`. Jeśli model zwrócił `supported` lub `contradicted` bez zweryfikowanego cytatu z kandydata → degraduje werdykt do `insufficient`.
  - Strażnik zakresu: jeśli model zwrócił `contradicted`, ale `scope_relation == "different_scope"` → degraduje werdykt do `insufficient` z zachowaniem `scope_note` (nigdy nie oznacza różnej wersji/kontekstu jako sprzeczności).
  - Dla `insufficient`, gdy istnieją kandydaci z `retrieve`, dołącza najbliższy sprawdzony fragment (`closest_chunk`, `supports_claim=False`) do wyświetlenia w bloku „Najbliższy fragment” na ekranie `3`.
- `extract` ucina listę tez do `settings.audit_max_claims`, dopasowuje `source_excerpt` do `resolution_note` przez `locate_quote()` (zapisując `source_start`/`source_end` lub `None`, gdy brak dokładnego dopasowania; fallback `claim_text`/`claim_label` na `source_excerpt`, jeśli puste).
- `retrieve` i `verify` uruchamiają operacje per teza równolegle pod `asyncio.Semaphore(settings.audit_claim_concurrency)`. `retrieve` używa `resolve_active_chunk_set_ids()` + `search_bm25()` (dziedzicząc `settings.include_synthetic`) i aktualizuje postęp po każdej tezie (`claims_done`).
- Błąd lub `TimeoutError` wywołania LLM w `verify` dla pojedynczej tezy nie przerywa grafu — zapisuje tę tezę jako `insufficient` z jawnym `error` i zachowuje najbliższy sprawdzony fragment (decyzja D3).

#### 3. Testy jednostkowe grafu i reguł
**File**: `backend/tests/test_audit_rules.py`, `backend/tests/test_audit_graph.py`
**Intent**: Pokryć wszystkie 4 kategorie agregacji notatki, przypadki brzegowe (0 tez, brak dopasowania cytatu, degradacja `contradicted` przy `different_scope`, błąd LLM pojedynczej tezy, przekroczenie `audit_max_claims`, dziedziczenie `include_synthetic`) bez wywołań sieciowych.
**Contract**: Deterministyczne testy z wstrzykiwanym `FakeChatModel` i stubowanym `search_bm25`.

### Success Criteria:

#### Automated Verification:
- Testy jednostkowe reguł i grafu audytu przechodzą: `cd backend; uv run pytest tests/test_audit_rules.py tests/test_audit_graph.py`
- Kontrole jakości backendu przechodzą: `cd backend; uv run ruff check .; uv run ruff format --check .; uv run python -m mypy .`

#### Manual Verification:
- Brak (weryfikacja automatyczna wyczerpuje Fazę 2).

**Implementation Note**: Po przejściu weryfikacji automatycznej Fazy 2 przejdź do Fazy 3.

---

## Phase 3: Wykonanie w tle (`lifespan`), API `/api/audits` i synchronizacja OpenAPI/TS

### Overview

Podłączamy graf audytu do wykonania w tle zarządzanego przez `lifespan` FastAPI, wystawiamy endpointy `POST /api/audits` i `GET /api/audits/{audit_id}` z izolacją anonimowej sesji `kops_session` i śladem Langfuse oraz synchronizujemy kontrakt OpenAPI i typy TypeScript.

### Changes Required:

#### 1. Runner zadań w tle i cykl życia w `main.py`
**File**: `backend/app/auditing/runner.py`, `backend/app/main.py`
**Intent**: Uruchamiać audyty w tle jako zarządzane zadania `asyncio.Task` powiązane z `app.state`, z czyszczeniem osieroconych audytów przy starcie i bezpiecznym zamykaniem przy shutdown (decyzje D1 i D3).
**Contract**:
- `AuditTaskManager` w `backend/app/auditing/runner.py`: utrzymuje `set[asyncio.Task[None]]`, udostępnia `schedule(audit_id, ...)` (uruchamia graf pod `asyncio.timeout(settings.audit_deadline_s)`, zapisuje postęp przez `store.py`, obsługuje błędy przez `fail_audit()`, wysyła ślady przez `run_in_threadpool(flush_traces)` w `finally` pod `anyio.CancelScope(shield=True)`) oraz `shutdown()` (anuluje i oczekuje zakończenia aktywnych zadań).
- `backend/app/main.py`: w `lifespan` tworzy `app.state.audit_tasks = AuditTaskManager()`, wywołuje best-effort `fail_orphaned_audits()` (w bloku `try/except`, aby nie blokować startu bez DB), rejestruje `audits.router`, a w `finally` wywołuje `await app.state.audit_tasks.shutdown()` przed `await pool.close()`.

#### 2. Endpointy `/api/audits`
**File**: `backend/app/api/audits.py`
**Intent**: Wystawić kontrakt REST dla ekranów `2`, `2P`, `3` i `3N` z walidacją wejścia, izolacją sesji i jawnym modelem odpowiedzi.
**Contract**:
- `POST /api/audits` (HTTP `202 Accepted`, `SessionDep`):
  - Wejście `CreateAuditRequest`: `case_ref: str | None = Field(default=None, max_length=120)`, `case_description: str = Field(min_length=1, max_length=4000)`, `resolution_note: str = Field(min_length=1, max_length=4000)` (walidator odrzuca ciągi złożone z samych białych znaków).
  - Sprawdza dostępność klucza/konfiguracji modelu i aktywnej migawki (`corpus_info` + `resolve_active_chunk_set_ids`), tworzy wiersz `audits` ze statusem `queued`, zleca zadanie w `AuditTaskManager` i zwraca `CreateAuditResponse(audit_id, status="queued", stage="queued")`.
- `GET /api/audits/{audit_id}` (HTTP `200 OK` lub `404`, `AuditSessionDep`):
  - Zwraca `AuditDetailResponse`: `audit_id`, `case_ref`, `case_description`, `resolution_note`, `status`, `stage`, `claims_total`, `claims_done`, `note_verdict`, `case_context`, `claims` (lista z `claim_id`, `claim_index`, `claim_label`, `claim_text`, `source_excerpt`, `source_start`, `source_end`, `verdict`, `rationale`, `scope_note`, `evidence`, `checked_docs`, `error`), `snapshot_id`, `chunk_set_ids`, `include_synthetic`, `config`, `error`, `duration_ms`, `created_at`, `completed_at`.
  - Zwraca `404` przy braku ciasteczka, innym `session_hash` lub nieistniejącym `audit_id` (bez tworzenia ciasteczka).

#### 3. Testy integracyjne API i synchronizacja kontraktu OpenAPI/TS
**File**: `backend/tests/test_audits_api.py`, `backend/openapi.json`, `frontend/app/api/schema.d.ts`
**Intent**: Zweryfikować pełny cykl `POST /api/audits` → `202` → `GET /api/audits/{id}` (postęp + wynik końcowy + `404` dla innej sesji + walidacja pustych pól i limitu 4000 znaków + `fail_orphaned_audits` na starcie) oraz wygenerować aktualne typy API.
**Contract**: Wygenerować `backend/openapi.json` przez `uv run python scripts/export_openapi.py` oraz `frontend/app/api/schema.d.ts` przez `npm run api:types`.

### Success Criteria:

#### Automated Verification:
- Testy API audytu i cały zestaw testów backendu przechodzą: `cd backend; uv run pytest`
- Kontrole jakości backendu przechodzą: `cd backend; uv run ruff check .; uv run ruff format --check .; uv run python -m mypy .`
- Kontrakt OpenAPI i typy frontendu są zsynchronizowane i przechodzą typecheck: `cd backend; uv run python scripts/export_openapi.py` oraz `cd frontend; npm run api:types; npm run typecheck`

#### Manual Verification:
- Brak (weryfikacja UI i end-to-end w Fazie 4).

**Implementation Note**: Po przejściu weryfikacji automatycznej Fazy 3 przejdź do Fazy 4.

---

## Phase 4: Frontend (`2`, `2P`, `3`, `3N`), panel `Kontekst sprawy`, i18n i weryfikacja pilotażu

### Overview

Budujemy ekrany `2`, `2P`, `3` i `3N` (desktop `>= 1280 px` i wąskie okno `390 px` bez przewijania w poziomie), dodajemy brakujące tokeny statusów i ikony, podłączamy nawigację (`NavRail` + link w `AbstentionView`), dodajemy tłumaczenia PL/EN i testy Vitest, a na koniec ręcznie weryfikujemy 12 przypadków pilotażowych i aktualizujemy `docs/przeplyw-danych.md`.

### Changes Required:

#### 1. Tokeny CSS, ikony statusów i drobne uogólnienia wspólnych komponentów
**File**: `frontend/app/app.css`, `frontend/app/components/shared/Icon.tsx`, `frontend/app/components/assistant/ProgressCard.tsx`, `frontend/app/components/assistant/EvidencePanel.tsx`, `frontend/app/components/assistant/AbstentionView.tsx`, `frontend/app/components/shell/NavRail.tsx`
**Intent**: Dodać tokeny kolorów z makiet `S2`/`S2P`/`S3` oraz reużywalne prymitywy ikon/dowodów i podłączyć nawigację do `/audyt`.
**Contract**:
- `app.css`: dodać tokeny dla `supported` (`#e7f4ec`, `#1f7a3d`, `#2f8a4f`), `partial` (`#fbf0dc`, `#7a4e0c`, `#8a5a12`), `insufficient` (`#eeeff1`, `#43474e`), podświetlenia wybranej tezy (`#eef2fc`), panelu bocznego S2/S2P (`#fafaf8`) oraz nieaktywnych pól S2P (`#ececea`).
- `Icon.tsx`: dodać `SupportedIcon`, `PartialIcon`, `InsufficientIcon` (zastąpić duplikat inline w `AbstentionView.tsx`), `SystemIcon` i `AuditNavIcon`; wydzielić współdzielony `StepStatusIcon` używany przez `ProgressCard` i `AuditProgressAside`.
- `EvidencePanel.tsx`: dodać opcjonalny props `initialMode?: "window" | "document"` (domyślnie `"window"`), resetowany przy zmianie cytatu, aby przycisk `Otwórz cały dokument` na ekranie `3` otwierał od razu cały dokument.
- `NavRail.tsx`: dodać drugą pozycję `/audyt` („Przekaż sprawę do audytu”, ikona clipboard-check); bez linku do nieistniejącego jeszcze S-10.
- `AbstentionView.tsx`: dodać subtelny drugorzędny link do `/audyt` (decyzja D6).

#### 2. Klient API, czyste funkcje pomocnicze i tłumaczenia PL/EN
**File**: `frontend/app/api/audits.ts`, `frontend/app/lib/audit.ts`, `frontend/app/lib/audit.test.ts`, `frontend/app/i18n/pl.ts`, `frontend/app/i18n/en.ts`
**Intent**: Udostępnić typowane wywołania `createAudit()` i `fetchAudit()`, czyste funkcje budujące segmenty podświetlanej notatki (`T1`/`T2` z obsługą nakładających się lub brakujących offsetów) oraz mapowanie statusów na etykiety/ikony, wraz z kompletem kluczy PL/EN.
**Contract**:
- `buildNoteSegments(noteText, claims)` w `frontend/app/lib/audit.ts` — czysta funkcja zwracająca uporządkowane segmenty tekstu zwykłego i zakotwiczonych tez (bez nakładania się; tezy bez dopasowanego offsetu nie psują renderowania notatki i pozostają na liście tez).
- `pl.ts` i `en.ts` zachowują ścisły `Record<TranslationKey, string>` ze wszystkimi tekstami ekranów `2`, `2P`, `3`, `3N` i `Kontekstu sprawy`, z jawnym komunikatem, że analiza nie zmienia dokumentacji i brak dowodu nie dowodzi luki.

#### 3. Trasy `/audyt` (ekran 2) i `/audyt/:id` (ekrany 2P, 3, 3N) oraz komponenty audytu
**File**: `frontend/app/routes.ts`, `frontend/app/routes/audit-new.tsx`, `frontend/app/routes/audit-detail.tsx`, `frontend/app/components/audit/AuditFormView.tsx`, `frontend/app/components/audit/AuditProgressAside.tsx`, `frontend/app/components/audit/AuditResultView.tsx`, `frontend/app/components/audit/CaseContextPanel.tsx`, `frontend/app/components/audit/AuditPreparationDetails.tsx`
**Intent**: Zaimplementować pełny przepływ UI audytu w trybie SPA (`ssr: false`), ściśle odwzorowując makiety `S2`, `S2P`, `S3` i `S3N` w granicach zakresu S-08.
**Contract**:
- `routes.ts`: dodać `route("audyt", "routes/audit-new.tsx")` i `route("audyt/:id", "routes/audit-detail.tsx")` wewnątrz `routes/_layout.tsx`.
- `audit-new.tsx` (ekran `2`): baner z ostrzeżeniem o ręcznym przekazaniu i braku danych osobowych/poufnych, pola `Identyfikator sprawy` (opcjonalne), `Opis problemu lub zgłoszenia` (wymagane), `Notatka z rozwiązaniem` (wymagane, licznik znaków `N / 4000`), przyciski `Uruchom analizę` i `Wyczyść`, notatka „Analiza nie zmienia dokumentacji”, prawy panel „Co się stanie po uruchomieniu” (układ pionowy poniżej `1024 px`). Po `POST /api/audits` → nawigacja na `/audyt/:id`.
- `audit-detail.tsx` (ekrany `2P` → `3` / `3N`):
  - Dla `status` w `queued` / `running`: renderuje widok `2P` (zablokowane pola ze złożonej sprawy + prawy panel `role="status"` z rzeczywistymi etapami i postępem `Szukanie dowodów dla tezy X z Y…`, oraz informacją o działaniu w tle bez martwego linku do S-10) i odpytuje `GET /api/audits/:id` co ~1.5 s (z zatrzymaniem po `completed`/`failed` lub odmontowaniu).
  - Dla `status === "failed"`: czytelny komunikat błędu + przycisk powrotu do `/audyt` (z możliwością ponownego przekazania sprawy).
  - Dla `status === "completed"`: renderuje `AuditResultView` (`S3` na desktopie, układ pionowy `S3N` na `390 px` bez przewijania w poziomie): nagłówek sprawy + pigułka oceny całej notatki (słowo + ikona); lewa kolumna z podświetlaną notatką, przewijaną (`min-h-0 overflow-y-auto`) pionową listą tez `<button aria-pressed>` (etykieta + pigułka oceny) i przyciskiem `Kontekst sprawy · brakuje N informacji ›`; środkowa kolumna `OCENA SYSTEMU · automatyczna, nie jest decyzją` z uzasadnieniem, sprawdzonym zakresem (w tym oznaczeniem `synthetic@v1`), blokiem cytowanego/najbliższego fragmentu z przyciskami `Pokaż szerszy kontekst` (`initialMode="window"`) i `Otwórz cały dokument` (`initialMode="document"`) oraz zwiniętym `<details>` `Jak powstała ta analiza` (`FR-020`).
  - `CaseContextPanel`: renderowany w `PanelFrame` (wspólny slot z `EvidencePanel` — otwarcie jednego zamyka drugie), wyświetla pola `FR-007` (`problem`, `environment`, `solution`, `constraints`, `missing_info`) oraz oryginalny opis zgłoszenia (decyzja D4).

#### 4. Aktualizacja opisu przepływu danych i ręczna weryfikacja pilotażu
**File**: `docs/przeplyw-danych.md` (lokalny plik gitignored — nie dodawać przez `git add -f`)
**Intent**: Dopisać wiersz dla przepływu audytu (wklejony opis zgłoszenia i notatka wysyłane do `CHAT_MODEL` i śladu Langfuse, przechowywane w `audits` w ramach sesji `kops_session`) zgodnie z `prd.md:273`.
**Contract**: Sekcja/tabela przepływów w `docs/przeplyw-danych.md` zaktualizowana o audyt S-08; ręczne przepuszczenie 12 przypadków z `docs/pilotaz-audytu-techqa.md` przez działający graf (bez traktowania wyniku jako pomiaru końcowego S-11).

### Success Criteria:

#### Automated Verification:
- Kontrole frontendu przechodzą bez błędów: `cd frontend; npm run lint; npm run format:check; npm run typecheck; npm test; npm run build`
- Pełna weryfikacja backendu nadal przechodzi: `cd backend; uv run ruff check .; uv run ruff format --check .; uv run python -m mypy .; uv run pytest`

#### Manual Verification:
- Przekazanie sprawy na `/audyt` (ekran `2`), przejście przez stan postępu (ekran `2P`) oraz odświeżenie strony w trakcie trwania analizy — postęp przetrwa odświeżenie i przejdzie do wyniku (ekran `3`).
- Widok wyniku na `1280 px` i `390 px` bez przewijania w poziomie: przełączanie tez `T1`/`T2`, otwieranie `Kontekstu sprawy` w `PanelFrame`, otwieranie `Pokaż szerszy kontekst` i `Otwórz cały dokument` w `EvidencePanel`, przełączanie języka `PL`/`EN`, widoczność linku w `AbstentionView` (1C).
- Ręczne przepuszczenie 12 przypadków pilotażu z `docs/pilotaz-audytu-techqa.md` przez graf audytu z ręcznym porównaniem kategorii i cytatów (bez raportowania jako pomiar końcowy S-11) oraz potwierdzenie aktualizacji `docs/przeplyw-danych.md`.

**Implementation Note**: Po przejściu weryfikacji automatycznej Fazy 4 zatrzymaj się na ręczną weryfikację UI i 12 przypadków pilotażowych przez człowieka.

---

## Testing Strategy

### Unit Tests:
- `backend/tests/test_audit_rules.py`: wszystkie kombinacje `aggregate_note_verdict` (0 tez, same `insufficient`, same `supported`, mix `supported`+`insufficient`, dowolne `contradicted`), degradacja `supported`/`contradicted` bez dosłownego cytatu w kandydacie, degradacja `contradicted` przy `scope_relation == "different_scope"`.
- `backend/tests/test_audit_graph.py`: pełny przebieg grafu na `FakeChatModel` (wyodrębnienie kontekstu i tez, limit `audit_max_claims`, równoległe `retrieve`/`verify`, degradacja pojedynczej tezy do `insufficient` przy wyjątku/timeoucie LLM, dziedziczenie `include_synthetic`).
- `frontend/app/lib/audit.test.ts`: `buildNoteSegments()` dla wielu spanów, brakujących offsetów, nakładających się offsetów i znaków specjalnych; mapowanie statusów na tokeny/etykiety.

### Integration Tests:
- `backend/tests/test_audit_store.py` (`@pytest.mark.db`): migracja `0004_audits.sql`, zapis/odczyt postępu i wyników, izolacja `session_hash`, `fail_orphaned_audits()`.
- `backend/tests/test_audits_api.py`: `POST /api/audits` (`202`, wydanie `kops_session`, walidacja pustych pól i `> 4000` znaków), polling `GET /api/audits/{id}` do `completed`, `404` dla innej sesji lub braku ciasteczka (bez wydawania ciasteczka).

### Manual Testing Steps:
1. Uruchom `docker compose up -d db backend` oraz `cd frontend; npm run dev`, otwórz `/audyt`, zweryfikuj ostrzeżenie o danych i licznik znaków, prześlij przykład `P04`.
2. Podczas etapu `Szukanie dowodów…` odśwież kartę (`F5`) — potwierdź, że ekran `2P` odtwarza bieżący etap z backendu i płynnie przechodzi do ekranu `3`.
3. Na ekranie `3` sprawdź oba rozmiary okna (`1280 px` i `390 px`): przełączanie tez, `Kontekst sprawy` w `PanelFrame`, `Pokaż szerszy kontekst` / `Otwórz cały dokument`, zwinięte `Jak powstała ta analiza` oraz przełącznik `PL`/`EN`.
4. Przepuść 12 przypadków z `docs/pilotaz-audytu-techqa.md` przez graf i zanotuj obserwacje (czy system rozróżnia brak dowodu od sprzeczności).

## Performance Considerations

- Pula DB ma `max_size=5` (`backend/app/db.py:23`), więc każde zapytanie SQL w `retrieve` i aktualizacji postępu zwalnia połączenie przed wywołaniem LLM.
- Współbieżność per teza jest ograniczona przez `audit_claim_concurrency=3` (domyślnie), a maksymalna liczba tez przez `audit_max_claims=12` oraz całkowity budżet `audit_deadline_s=90`, co chroni przed nadmiernym kosztem i wyczerpaniem puli.

## Migration Notes

- Nowa migracja `backend/migrations/0004_audits.sql` jest czysto addytywna i nie dotyka `0001`–`0003`.
- Brak kluczy obcych do `snapshots`/`documents`/`chunks` zapewnia, że reimport migawki (`import-techqa`) nie usuwa zapisanych audytów.
- Wycofanie w środowisku deweloperskim sprowadza się do `DROP TABLE IF EXISTS audit_claims, audits;` i usunięcia wpisu z `schema_migrations`.

## References

- Research: `context/changes/resolved-case-audit/research.md`
- PRD: `context/foundation/prd.md` (`US-02`, `FR-006`, `FR-007`, `FR-008`, `FR-020`, `Business Logic`)
- Architektura: `context/foundation/architecture-notes.md`
- Makiety: `design/mockups/README.md`, `design/mockups/canvas/S2.dc.html`, `S2P.dc.html`, `S3.dc.html`, `S3N.dc.html`
- Pilotaż: `docs/pilotaz-audytu-techqa.md`
- Podobne implementacje: `backend/app/answering/nodes.py`, `backend/app/api/answers.py`, `frontend/app/components/assistant/EvidencePanel.tsx`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Migracja `0004_audits.sql`, repozytorium audytów i wspólne poprawki backendu

#### Automated

- [x] 1.1 Migracja `0004_audits.sql` stosuje się idempotentnie: `cd backend; uv run python -m app.cli migrate` — 6cbd843
- [x] 1.2 Testy Fazy 1 i brak regresji przechodzą: `cd backend; uv run pytest tests/test_audit_store.py tests/test_observability.py tests/test_answers_api.py` — 6cbd843
- [x] 1.3 Kontrole jakości backendu przechodzą: `cd backend; uv run ruff check .; uv run ruff format --check .; uv run python -m mypy .` — 6cbd843

### Phase 2: Graf audytu LangGraph (`backend/app/auditing/`) i deterministyczne reguły

#### Automated

- [x] 2.1 Testy jednostkowe reguł i grafu audytu przechodzą: `cd backend; uv run pytest tests/test_audit_rules.py tests/test_audit_graph.py`
- [x] 2.2 Kontrole jakości backendu przechodzą: `cd backend; uv run ruff check .; uv run ruff format --check .; uv run python -m mypy .`

### Phase 3: Wykonanie w tle (`lifespan`), API `/api/audits` i synchronizacja OpenAPI/TS

#### Automated

- [ ] 3.1 Testy API audytu i cały zestaw testów backendu przechodzą: `cd backend; uv run pytest`
- [ ] 3.2 Kontrole jakości backendu przechodzą: `cd backend; uv run ruff check .; uv run ruff format --check .; uv run python -m mypy .`
- [ ] 3.3 Kontrakt OpenAPI i typy frontendu są zsynchronizowane i przechodzą typecheck: `cd backend; uv run python scripts/export_openapi.py` oraz `cd frontend; npm run api:types; npm run typecheck`

### Phase 4: Frontend (`2`, `2P`, `3`, `3N`), panel `Kontekst sprawy`, i18n i weryfikacja pilotażu

#### Automated

- [ ] 4.1 Kontrole frontendu przechodzą bez błędów: `cd frontend; npm run lint; npm run format:check; npm run typecheck; npm test; npm run build`
- [ ] 4.2 Pełna weryfikacja backendu nadal przechodzi: `cd backend; uv run ruff check .; uv run ruff format --check .; uv run python -m mypy .; uv run pytest`

#### Manual

- [ ] 4.3 Przekazanie sprawy na `/audyt` (ekran `2`), przejście przez stan postępu (ekran `2P`) oraz odświeżenie strony w trakcie trwania analizy — postęp przetrwa odświeżenie i przejdzie do wyniku (ekran `3`).
- [ ] 4.4 Widok wyniku na `1280 px` i `390 px` bez przewijania w poziomie: przełączanie tez `T1`/`T2`, otwieranie `Kontekstu sprawy` w `PanelFrame`, otwieranie `Pokaż szerszy kontekst` i `Otwórz cały dokument` w `EvidencePanel`, przełączanie języka `PL`/`EN`, widoczność linku w `AbstentionView` (1C).
- [ ] 4.5 Ręczne przepuszczenie 12 przypadków pilotażu z `docs/pilotaz-audytu-techqa.md` przez graf audytu z ręcznym porównaniem kategorii i cytatów (bez raportowania jako pomiar końcowy S-11) oraz potwierdzenie aktualizacji `docs/przeplyw-danych.md`.
