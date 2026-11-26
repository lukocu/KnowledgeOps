---
date: 2026-11-26T22:16:00+01:00
researcher: Antigravity
git_commit: 4d4e65426d66159b470ff8956d69a3120bad35c1
branch: main
repository: KnowledgeOps
topic: "S-08: Analiza rozwiązanej sprawy (resolved-case-audit)"
tags: [research, codebase, audit, langgraph, paradedb, fastapi, react, mockups, ai-devs-4]
status: complete
last_updated: 2026-11-26
last_updated_by: Antigravity
---

# Research: S-08 — Analiza rozwiązanej sprawy (`resolved-case-audit`)

**Date**: 2026-11-26T22:16:00+01:00
**Researcher**: Antigravity
**Git Commit**: `4d4e65426d66159b470ff8956d69a3120bad35c1`
**Branch**: `main`
**Repository**: `KnowledgeOps`

## Research Question

Jakie są aktualne fundamenty kodu, schematu bazy, sesji, obserwowalności, makiet kanwy (`2`, `2P`, `3`, `3N`), wzorców z AI Devs 4 (`01_01_grounding`, `01_01_structured`, `02_02_hybrid_rag`) oraz decyzji z wcześniejszych zmian (`S-02`, `S-07`), na których powinien oprzeć się plan wdrożenia etapu **S-08 (`resolved-case-audit`)** — i jakie luki, rozbieżności lub decyzje otwarte wymagają rozstrzygnięcia przed `/10x-plan`?

## Summary

Repozytorium ma gotowe i zweryfikowane bloki pod S-08: anonimową sesję w ciasteczku `kops_session` (`backend/app/session.py:14-59`), wyszukiwanie BM25 ParadeDB po wielu zestawach (`backend/app/retrieval.py:185-233`), weryfikację dosłowności cytatu (`locate_quote`, `backend/app/answering/nodes.py:112-125`), wzorzec strict structured output + 3-stanowy werdykt tezy (`supported | contradicted | insufficient`, `backend/app/answering/schemas.py:11,31-38`), deterministycznego strażnika zakresu (`resolve_conflict_type`, `backend/app/answering/nodes.py:247-266`), warstwę dowodów `/api/evidence` i `/api/documents` (`backend/app/api/evidence.py:46-94`), komponenty UI `EvidencePanel` + `PanelFrame` + `PreparationDetails` (`frontend/app/components/assistant/`), oraz 12 przypadków pilotażowych (`docs/pilotaz-audytu-techqa.md:13-79`).

Zidentyfikowano **5 kluczowych luk/rozbieżności** do rozstrzygnięcia w planie S-08:
1. **Brak pakietu checkpointingu i workera w tle**: `langgraph-checkpoint-postgres` nie jest zainstalowany w `backend/pyproject.toml:7-14`, a obecna pula połączeń (`backend/app/db.py:20-29`, `max_size=5`) nie używa `autocommit=True` ani `dict_row` wymaganych przez `AsyncPostgresSaver`. W `backend/` nie istnieje też jeszcze uruchamianie zadań w tle — `POST /api/answers` strumieniuje graf inline przez SSE (`backend/app/api/answers.py:238-263`), podczas gdy S-08 wymaga wykonania w tle z zapisem stanu w Postgresie i przetrwaniem odświeżenia strony (`context/foundation/architecture-notes.md:23,30`).
2. **Dwa sprzężenia w istniejącym backendzie**: `require_session()` w `backend/app/session.py:54` ma zaszyty komunikat `404` `"Nie znaleziono odpowiedzi"`, a `run_config()` w `backend/app/observability.py:69-93` ma zaszyte `run_name="answer"` i `app.answering.prompts.prompt_versions()`.
3. **Granica zakresu S-08 vs S-09 / S-10 na makietach**: ekrany `S3.dc.html` i `S3N.dc.html` zawierają elementy odroczone do S-09 (prawy panel decyzji redaktora, belka decyzji na 390 px, „Historia”, „Sugestia systemu”) oraz linki do listy analiz z S-10 („Analizy /”, stopka S2P). Natomiast wymagane przez `FR-007` pola kontekstu sprawy (`problem`, `environment`, `solution`, `constraints`, `missing_info`) mają na makiecie tylko zwinięty przycisk `Kontekst sprawy · brakuje 3 informacji ›` bez makiety stanu rozwiniętego (`design/mockups/canvas/S3.dc.html:26`).
4. **Brakujące tokeny CSS i ikony statusów na frontendzie**: w `frontend/app/app.css:4-35` istnieją tokeny dla `✕ Sprzeczność` (`--color-conflict-*`), ale brakuje dedykowanych tokenów tła/ikon dla `● Poparta` / `● Pełne pokrycie` (`#e7f4ec`, `#1f7a3d`, `#2f8a4f`), `◐ Częściowe pokrycie` (`#fbf0dc`, `#7a4e0c`, `#8a5a12`), `○ Niewystarczające dowody` (`#eeeff1`, `#43474e`) oraz tła podświetlenia wybranej tezy (`#eef2fc`).
5. **Cztery otwarte wybory projektowe**: (a) model zapisu stanu w tle (`langgraph-checkpoint-postgres` vs własne tabele Postgres + `asyncio.Task` zarządzane w lifespan), (b) zakres wyszukiwania w audycie (`include_synthetic` dziedziczone z `Settings` jak w S-07 czy tylko bazowa migawka TechQA), (c) sposób prezentacji tezy (dosłowne zdanie + krótka etykieta jak na `S3.dc.html`, decyzja otwarta #3) oraz (d) czy w `AbstentionView` (ekran 1C) dodać link do ekranu 2 (`AbstentionView.tsx:13`).

---

## Detailed Findings

### 1. Backend: zależności, baza, migracje i sesje

- **Zależności (`backend/pyproject.toml:7-14`, `backend/uv.lock`)**: zainstalowane pakiety produkcyjne to `fastapi[standard]` (`0.165.0`), `langchain-openai` (`1.8.5`, tranzytywnie `langchain-core==1.8.4`), `langfuse` (`5.2.0`), `langgraph` (`1.2.24`, tranzytywnie `langgraph-checkpoint==4.3.2`), `psycopg[binary,pool]` (`3.3.9` / `3.3.3`) oraz `pydantic-settings` (`2.16.3`). Pakiet `langgraph-checkpoint-postgres` nie występuje ani w `backend/pyproject.toml`, ani w `backend/uv.lock` (stan na commit `4d4e654`).
- **Lifespan i pula połączeń (`backend/app/main.py:24-39`, `backend/app/db.py:12-50`)**:
  - `lifespan(app)` tworzy pulę `create_pool(settings.database_url)` z `min_size=1`, `max_size=5`, `open=False`, `connect_timeout=5`, wywołuje `await pool.open(wait=False)` i zamyka ją przy shutdown (`main.py:26-31`, `db.py:20-29`).
  - `answers.py` pobiera połączenie z puli tylko na czas zapytań SQL (pobranie `corpus_info`, `search_bm25`, końcowy `INSERT`), nigdy nie trzyma połączenia podczas wywołań LLM — przy `max_size=5` (`db.py:23`) ten sam wzorzec jest konieczny dla współbieżnych etapów audytu w tle.
  - Migracje nie są uruchamiane w `lifespan`; uruchamia je synchroniczne CLI `python -m app.cli migrate` (`backend/app/cli.py:58-68`, `backend/app/migrations.py:1-77`).
- **Niezmienność migracji i schemat (`backend/app/migrations.py:39-61`, `backend/migrations/0001..0003`)**:
  - Runner migracji skanuje pliki `^\d{4}_\w+\.sql$` i weryfikuje SHA-256 już wdrożonych plików w `schema_migrations` (`migrations.py:9,39-61`). Istniejące pliki `0001_techqa_schema.sql`, `0002_answers.sql`, `0003_synthetic_and_conflicts.sql` są niemodyfikowalne — tabele audytu S-08 muszą trafić do `0004_*.sql`.
  - Tabela `answers` (`0002_answers.sql:1-17`) celowo nie posiada kluczy obcych (`FOREIGN KEY`) do `snapshots`/`documents`/`chunks`, ponieważ `import-techqa` kasuje migawkę kaskadowo przy reimporcie (`0001_techqa_schema.sql:15-25`). Tabele audytu S-08 muszą zachować tę samą konwencję (przechowywanie `snapshot_id`, `chunk_set_id`, `doc_id`, `chunk_id` jako `text` bez FK).
- **Anonimowa sesja (`backend/app/session.py:14-59`)**:
  - Ciasteczko `kops_session` (`path="/api"`, `httponly=True`, `samesite="lax"`, `secure=settings.session_cookie_secure`, `MAX_TOKEN_LENGTH=256`); w bazie przechowywany jest wyłącznie `hash_token(token)` (SHA-256 hex).
  - `SessionDep` (`get_or_create_session`, `:30-47`) wydaje ciasteczko na żądaniach `POST`; `ExistingSessionDep` (`require_session`, `:50-55`) na żądaniach `GET` zwraca `404` bez tworzenia sesji.
  - **Luka do poprawy**: `require_session` w `backend/app/session.py:54` ma zaszyty komunikat `"Nie znaleziono odpowiedzi"`. Przy reużyciu na `/api/audits/{id}` należy go uogólnić lub sparametryzować, aby nie zwracał mylącego komunikatu z przepływu pytań.

### 2. Backend: reużywalne prymitywy z `answering/`, `retrieval.py` i `observability.py`

- **Wyszukiwanie nakładkowe BM25 (`backend/app/techqa/search.py:15-16,80-95`, `backend/app/retrieval.py:32-45,185-233`)**:
  - `resolve_active_chunk_set_ids(conn, base_chunk_set_id, *, include_synthetic, synthetic_chunk_set_id)` zwraca `[base_chunk_set_id, synthetic_chunk_set_id]` gdy `include_synthetic=True` i zestaw istnieje w `chunk_sets`, a w przeciwnym razie bezpiecznie `[base_chunk_set_id]`.
  - `search_bm25(conn, query, *, chunk_set_id, extra_chunk_set_ids=(), k)` używa `chunk_set_id = ANY(%(chunk_set_ids)s) AND text ||| %(query)s` (wymóg ParadeDB `pg_search` 0.27.0 dla listy zestawów) i zwraca `RetrievedChunk` z pełnymi metadanymi (`snapshot_id`, `is_synthetic`, `doc_date`, `product_version`, `audience`, `retrieval.py:107-120`).
  - Endpointy dowodów (`backend/app/api/evidence.py:46-94`) — `GET /api/evidence` (okno `before`/`after` z limitem `MAX_CONTEXT_CHUNKS=5`) oraz `GET /api/documents` (z obsługą `snapshot_id` dla `synthetic@v1` i bazowej migawki) — są w pełni gotowe do reużycia przez ekran 3/3N bez zmian schematu.
- **Weryfikacja cytatów, tez i zakresu (`backend/app/answering/nodes.py`, `schemas.py`, `model.py`)**:
  - `locate_quote(chunk_text, quote) -> tuple[int, int] | None` (`nodes.py:112-125`) — czysta funkcja Pythona dopasowująca cytat dosłownie po normalizacji białych znaków i zwracająca offsety `[start, end)` w oryginalnym tekście. Nadaje się bezpośrednio zarówno do weryfikacji fragmentów z notatki/zgłoszenia (`source_span_check`), jak i dosłownych cytatów z dokumentów bazy wiedzy (`quote_check`).
  - `Verdict = Literal["supported", "contradicted", "insufficient"]` (`schemas.py:11`) oraz wzorzec `reasoning` przed `verdict` (`ClaimVerdict`, `schemas.py:31-34`) odpowiadają dokładnie trzem kategoriom oceny tezy w `FR-008` (`prd.md:174`).
  - `resolve_conflict_type(scope_relation, side_a_doc, side_b_doc)` (`nodes.py:247-266`) — wzorzec deterministycznego strażnika w Pythonie, który dla niezgodnych metadanych zakresu (`product_version`, `audience`) blokuje fałszywą etykietę `contradiction`. W audycie (teza z notatki vs dokument z bazy) tę samą zasadę z `Business Logic` (`prd.md:229`: „Sprzeczność dotyczy tego samego zakresu; dokument dla innej wersji lub okresu nie jest automatycznie sprzeczny”) można wdrożyć jako deterministyczną regułę na etapie oceny tezy i agregacji notatki.
  - `make_chat_model(settings)` (`model.py:60-79`) i wzorzec `with_structured_output(schema, strict=True)` + `asyncio.timeout(chat_timeout_s)` (`nodes.py:543-552`) zapewniają przenośność OpenAI / Gemini / OpenRouter i deterministyczne testy z wstrzykiwanym `BaseChatModel`.
  - Wersjonowanie promptów (`backend/app/answering/prompts/__init__.py:11-37`): pliki `*.md` cachowane w pamięci procesu i hashowane 12-znakowym prefiksem SHA-256.
- **Limity czasu (`backend/app/settings.py:36-37`)**:
  - `chat_timeout_s = 12` i `answer_deadline_s = 25` są skalibrowane pod 2–3 wywołania LLM w trybie pytań. Audyt (ekstrakcja + wyszukiwanie i ocena `N` tez osobno) wymaga osobnego budżetu czasu (np. `audit_deadline_s`, w PRD `NFR Czas analizy` jest mierzony bez twardego celu w MVP, `prd.md:219`).
- **Obserwowalność Langfuse (`backend/app/observability.py:24-93`)**:
  - `make_trace_handler()` zwraca `CallbackHandler` albo `None` bez kluczy; `flush_traces()` jest blokujące i uruchamiane w `finally` pod `anyio.CancelScope(shield=True)` przez `run_in_threadpool` (`answers.py:326-331`).
  - **Luka do poprawy**: `run_config()` (`observability.py:69-93`) ma zaszyte `run_name="answer"` i `app.answering.prompts.prompt_versions()`. Dla audytu potrzebny jest parametr `run_name` i przekazywane `prompt_versions` (lub osobny helper `audit_run_config`), przy zachowaniu zakazu wysyłania `session_hash` (`observability.py:80`).

### 3. Frontend i makiety kanwy (`S2`, `S2P`, `S3`, `S3N`)

- **Mapowanie plików kanwy (`design/mockups/canvas/canvas.json`)**:
  - `S2.dc.html` (`:41-47`, `1440×900`): formularz przekazania sprawy — **w całości S-08**.
  - `S2P.dc.html` (`:97-103`, `1440×900`): formularz zablokowany + prawy panel postępu na żywo (`role="status"`) — **w całości S-08**.
  - `S3.dc.html` (`:48-54`, `1440×900`) i `S3N.dc.html` (`:83-89`, `390×1640`): widok wyniku audytu — **podział S-08 / S-09**:
    - **W S-08**: nagłówek sprawy + pigułka oceny całej notatki (`● Pełne pokrycie`, `◐ Częściowe pokrycie`, `✕ Sprzeczność`, `○ Niewystarczające dowody`), lewa kolumna z tekstem notatki (inline znaczniki `T1`/`T2` i podkreślenia), pionowa lista tez `<button aria-pressed>` z pigułką oceny per teza (`● Poparta`, `✕ Sprzeczność`, `○ Niewystarczające dowody`), wejście do `Kontekst sprawy` (`problem`, `environment`, `solution`, `constraints`, `missing_info` — `FR-007`), środkowa kolumna `OCENA SYSTEMU · automatyczna, nie jest decyzją` z uzasadnieniem, sprawdzonym zakresem, blokiem cytowanego fragmentu oraz przyciskami `Pokaż szerszy kontekst` / `Otwórz cały dokument`, zwinięte `<details>` `Jak powstała ta analiza` (`FR-020`).
    - **Odroczone do S-09**: prawy `<aside aria-label="Decyzja redaktora">` (`340px`, `#f4f2ec`), dolna belka decyzji na `390px` (`S3N`) i arkusz `S3ND.dc.html`, zwinięte `<details>` `Historia` (`FR-021`), oraz etykieta „Sugestia systemu” odnosząca się do 4 kategorii decyzji z S-09.
    - **Odroczone do S-10**: okruszek `Analizy /` (`S3`), przycisk `Wróć do listy analiz` (`S3N`) oraz odnośnik do „Analizy i decyzje” w stopce `S2P` — zgodnie z komentarzem w `NavRail.tsx:22` nie dodajemy martwych linków.
- **Istniejące trasy, powłoka i nawigacja (`frontend/app/routes.ts:8-13`, `routes/_layout.tsx:13-50`, `components/shell/NavRail.tsx:22-33`)**:
  - Obecnie zdefiniowane są 2 trasy: `/` (`assistant.tsx`) i `/odpowiedz/:id` (`answer.tsx`).
  - `NavRail.tsx:22` zawiera jedną pozycję (`/`) z komentarzem: `Jedna pozycja do S-08/S-10: nie pokazujemy linków prowadzących donikąd.` W S-08 dochodzi druga pozycja nawigacji (`Przekaż sprawę do audytu`, ikona clipboard-check z `S2.dc.html:26`) oraz trasy dla ekranu 2/2P i 3/3N (np. `/audyt` i `/audyt/:id`).
  - `RoleSwitch` (`frontend/app/session/role.tsx:12-44`) przechowuje rolę `consultant | editor` w `localStorage` wyłącznie jako etykietę UI (`FR-011`). W S-08 obie role mogą przekazać sprawę i obejrzeć wynik oceny systemu; rozdział akcji zapisu decyzji wchodzi dopiero w S-09.
- **Reużywalne komponenty i luki w tokenach / i18n**:
  - `EvidencePanel.tsx` (`:15-530`) i `PanelFrame.tsx` (`:5-115`) są gotowe do reużycia dla przycisków `Pokaż szerszy kontekst` i `Otwórz cały dokument`; drobne rozszerzenie `initialMode?: "window" | "document"` w `EvidencePanel.tsx:312` pozwoli otwierać przycisk `Otwórz cały dokument` od razu w zakładce całego dokumentu.
  - `PreparationDetails.tsx` (`:87-103`) i `lib/snapshot.ts` dają gotowy wzorzec zwiniętego `<details>` dla „Jak powstała ta analiza”.
  - `ProgressCard.tsx` (`:18-45`) ma gotowe ikony `StatusIcon` (zielony check / niebieski łuk / szare kółko) identyczne z `S2P.dc.html:26`, ale jest sprzężony z `StepId` Asystenta — warto wydzielić wspólny prymityw `StatusIcon`.
  - `Icon.tsx` (`:4-119`) wymaga dodania ikon: `SupportedIcon` (`●`), `PartialIcon` (`◐`), `InsufficientIcon` (`○?`, obecnie inline w `AbstentionView.tsx:36-60`), `SystemIcon` (robot na S3/S3N) i ikony nawigacji audytu.
  - `app.css` (`:4-35`) wymaga dodania tokenów kolorystycznych z `S2.dc.html`, `S2P.dc.html`, `S3.dc.html`, `S5.dc.html`: `supported` (`#e7f4ec`, `#1f7a3d`, `#2f8a4f`), `partial` (`#fbf0dc`, `#7a4e0c`, `#8a5a12`), `insufficient` (`#eeeff1`, `#43474e`), podświetlenie wybranej tezy (`#eef2fc`), tło prawego panelu S2/S2P (`#fafaf8`) i nieaktywnych pól S2P (`#ececea`).
  - `i18n/pl.ts` i `i18n/en.ts` (strict `Record<TranslationKey, string>`) nie mają jeszcze żadnych kluczy audytu.
- **Konkretne obserwacje dla decyzji otwartych z `design/mockups/README.md:72-79`**:
  - **Decyzja #3 (dosłowne zdanie vs teza przeredagowana)**: `S3.dc.html:26` i `S3N.dc.html:26` pokazują **oba** — oryginalny tekst notatki z podświetlonym i zakotwiczonym fragmentem `T1`/`T2` oraz zwięzłą, weryfikowalną treść/etykietę tezy na liście tez i w nagłówku oceny.
  - **Decyzja #4 (panele poniżej 1400 px)**: w S-08 (bez 340 px panelu decyzji z S-09) dwie kolumny mieszczą się przy `1280 px`, ale po otwarciu `EvidencePanel` (`min(400px, 45%)`, `PanelFrame.tsx:10`) lewa kolumna powinna się zwężać lub przechodzić w układ pionowy jak `S3N` na węższych ekranach.
  - **Decyzja #5 (wiele tez)**: wbrew sformułowaniu „Zakładki tez” w `README.md:78`, makiety `S3.dc.html:26` i `S3N.dc.html:26` używają **pionowej listy przycisków `<button aria-pressed>`**, nie poziomych zakładek. Nadanie lewej kolumnie (lub liście tez) własnego przewijania (`min-h-0 overflow-y-auto`) rozwiązuje przypadek kilkunastu tez bez przycinania przycisku `Kontekst sprawy`.

### 4. Wzorce z AI Devs 4 (`01_01_grounding`, `01_01_structured`, `02_02_hybrid_rag`)

- **`01_01_grounding`** (`app.js:36-50`, `src/pipeline/concept-filter.js:10-48,95-119`, `src/schemas/extract.js:26-33`, `src/pipeline/search.js:10,136-146`):
  - **Do adaptacji**: wieloetapowy potok z izolacją na jednostkę (`extract` → `search` → `ground`), deterministyczna walidacja występowania wyodrębnionego fragmentu w tekście źródłowym (`!paragraph.includes(trimmed)` → u nas `locate_quote`), generowanie dedykowanego `search_query` per wyodrębniona teza oraz ograniczona współbieżność (`CONCURRENCY = 5` → u nas `asyncio.Semaphore` w Pythonie).
  - **Różnice domenowe**: `01_01_grounding` używa `web_search` (zakazane w KnowledgeOps), traktuje wyniki wyszukiwania jako prawdę do adnotacji tooltipami i nie posiada weryfikacji 3-stanowej ani reguły „brak dowodu ≠ luka w dokumentacji”.
- **`01_01_structured`** (`app.js:42-70`):
  - **Do adaptacji**: ścisłe schematy JSON (`strict: true`, wszystkie pola w `required`, jawne `null` i puste tablice zamiast pomijania kluczy) — odpowiada naszemu `with_structured_output(schema, strict=True)` z jawnym `missing_info: list[str]` i polami `str | None` dla brakujących informacji (`FR-007`).
- **`02_02_hybrid_rag`** (`src/agent/tools.js:19-34`, `src/db/search.js:19-28`):
  - **Do adaptacji**: budowanie czystego zapytania słów kluczowych (`keywords`) dla BM25 pozbawionego szumu narracyjnego z opisu zgłoszenia oraz sanitacja zapytania.
  - **Różnice domenowe**: `02_02_hybrid_rag` uruchamia otwartą pętlę agenta (`MAX_STEPS = 30`, `src/agent/index.js:12`) na SQLite FTS5; u nas graf audytu jest deterministyczną maszyną stanów w LangGraph nad ParadeDB SQL (`architecture-notes.md:30-31`).

### 5. Pilotaż audytu (`docs/pilotaz-audytu-techqa.md`)

- Plik `docs/pilotaz-audytu-techqa.md:13-79` definiuje **12 przypadków deweloperskich** (`P01`–`P12`, po 3 na każdą z 4 kategorii notatki: `FULL`, `PARTIAL`, `CONTRADICTION`, `INSUFFICIENT`) opartych na 3 sprawach TechQA (`TRAIN_Q000` / `swg21996508`, `TRAIN_Q001` / `swg21675316`, `TRAIN_Q012` / `swg21648497`).
- **Istotna różnica kontraktu pilotażu vs produktu (`pilotaz-audytu-techqa.md:7,91` vs `prd.md:108`)**: etykiety `P01`–`P12` powstały w kontrakcie **jednego wskazanego dokumentu**, natomiast produkt w S-08 przeszukuje **całą migawkę bazy wiedzy** (`prd.md:108`, `roadmap.md:318`). Weryfikacja S-08 (`roadmap.md:337`) przewiduje ręczne przepuszczenie 12 przypadków przez graf (bez traktowania wyniku jako pomiaru końcowego — pomiar wchodzi w `S-11`).

---

## Code References

- `backend/pyproject.toml:7-14` — lista zależności Pythona (brak `langgraph-checkpoint-postgres`).
- `backend/app/main.py:24-39` — lifespan FastAPI, otwarcie puli `app.state.pool`, rejestracja routerów.
- `backend/app/db.py:12-50` — `create_pool()` (`max_size=5`), `PoolDep`, `http_connection()`.
- `backend/app/migrations.py:9-77` — runner migracji z weryfikacją SHA-256 (`0001`–`0003` niemodyfikowalne).
- `backend/app/session.py:14-59` — obsługa ciasteczka `kops_session` i `require_session()` (zaszyty komunikat `404` w linii `:54`).
- `backend/app/observability.py:24-93` — `make_trace_handler()`, `flush_traces()`, `run_config()` (zaszyte `run_name="answer"` w linii `:90`).
- `backend/app/retrieval.py:107-120,185-233` — `RetrievedChunk`, `search_bm25()` z `ANY(%(chunk_set_ids)s)`, `resolve_active_chunk_set_ids()`.
- `backend/app/api/evidence.py:46-94` — `/api/evidence` i `/api/documents` (gotowe dla ekranu 3/3N).
- `backend/app/answering/nodes.py:112-125,247-266,543-552` — `locate_quote()`, `resolve_conflict_type()`, `_call_model()`.
- `backend/app/answering/schemas.py:11,31-38` — `Verdict`, `ClaimVerdict`, `VerifyOutput`.
- `backend/app/settings.py:22,36-37` — `include_synthetic=True`, `chat_timeout_s=12`, `answer_deadline_s=25`.
- `frontend/app/routes.ts:8-13` i `frontend/app/components/shell/NavRail.tsx:22-33` — obecne trasy i nawigacja z komentarzem dla S-08/S-10.
- `frontend/app/components/assistant/EvidencePanel.tsx:15-530` i `PanelFrame.tsx:5-115` — reużywalny panel/arkusz dowodu (`initialMode` do rozważenia w `:312`).
- `frontend/app/components/assistant/AbstentionView.tsx:13,36-60` — komentarz o linku do audytu w S-08 oraz inline SVG ikony `○?`.
- `frontend/app/app.css:4-35` — tokeny kolorystyczne (brak tokenów `supported`/`partial`/`insufficient`).
- `design/mockups/canvas/S2.dc.html:26`, `S2P.dc.html:26`, `S3.dc.html:26`, `S3N.dc.html:26` — wzorce ekranów S-08.

---

## Architecture Insights

1. **Jednolita architektura przepływów, inny model wykonania**: S-02/S-07 używają krótkiego strumienia SSE w ramach żądania HTTP (`POST /api/answers`). S-08 realizuje dłuższy wielotezowy przepływ w tle: `POST /api/audits` tworzy rekord w bazie (status `queued`/`running`, przypisany do `session_hash`), uruchamia graf w tle i natychmiast zwraca `audit_id` (HTTP `202`), a frontend przekierowuje na `/audyt/:id` i odpytuje `GET /api/audits/:id` aż do zakończenia (`completed`/`failed`). Dzięki temu odświeżenie lub zamknięcie i ponowne otwarcie strony nie przerywa analizy ani nie gubi postępu (`roadmap.md:315,338`).
2. **Spójność kontraktu z S-09 i S-10 bez naruszania S-08**: Tabele `0004_*.sql` powinny od razu przewidzieć stabilne identyfikatory audytu (`audit_id uuid`) oraz stabilne identyfikatory tez (`claim_id` / `claim_index`) i strukturę statusu/etapów, tak aby S-09 (decyzje per teza + historia zdarzeń) i S-10 (lista analiz + przykłady demo) mogły dodać własne tabele/kolumny w `0005_*.sql` bez przepisywania schematu S-08.
3. **Deterministyczna agregacja oceny całej notatki (`Business Logic`, `prd.md:231`)**: Reguła mapowania ocen tez na ocenę notatki jest w pełni deterministyczna i powinna żyć w czystym Pythonie (bez LLM):
   - brak wyodrębnionych weryfikowalnych tez lub wszystkie tezy `insufficient` → `insufficient`;
   - co najmniej jedna teza `contradicted` (w tym samym zakresie) → `contradiction`;
   - wszystkie tezy `supported` → `full`;
   - co najmniej jedna `supported` i co najmniej jedna `insufficient` (bez `contradicted`) → `partial`.
4. **Aktualizacja `docs/przeplyw-danych.md`**: zgodnie z adnotacją w `docs/przeplyw-danych.md:3` (plik lokalny/gitignored — nie dodawać przez `git add -f`), S-08 dopisuje wiersz dla nowego przepływu zewnętrznych danych (wklejony opis zgłoszenia i notatka wysyłane do `CHAT_MODEL` i śladu Langfuse).

---

## Historical Context (from prior changes)

- `context/archive/2026-11-23-grounded-answer-or-abstention/plan.md` — **supported**: ustanowił wzorzec `kops_session` (tylko SHA-256 w bazie, `404` bez tworzenia sesji na `GET`), brak FK do tabel migawek, `locate_quote` + izolację weryfikatora tez (`verify` bez treści pytania), SHA-256 wersjonowanie promptów `*.md` oraz `flush_traces()` w `run_in_threadpool` pod `CancelScope(shield=True)`.
- `context/archive/2026-11-26-conflicting-sources/plan.md` — **supported**: ustanowił nakładkę `synthetic@v1` z `resolve_active_chunk_set_ids()` + `ANY(%(chunk_set_ids)s)`, per-cytatowe `snapshot_id` dla `/api/documents`, deterministycznego strażnika zakresu `resolve_conflict_type()` oraz utrzymanie kompatybilności wstecznej `answers` i `eval-abstention`.
- `context/foundation/roadmap.md:327` — **partially stale**: pole `Unknowns` przy `S-08` nadal oznacza „Dostawca modelu czatu” jako `Block: yes` i `Status: blocked`, podczas gdy ten sam dokument w `Open Roadmap Questions #13` (`roadmap.md:552`) i w `S-02` (`roadmap.md:174`) potwierdza, że dostawca modelu czatu został już rozstrzygnięty w S-02 (`langchain-openai` + `OPENAI_BASE_URL`). Pozostałe nieznane S-08 (decyzje #3 i #5 makiet, `roadmap.md:328-329`) są nadal aktualne i nieblokujące.

---

## Related Research

- [context/archive/2026-11-23-grounded-answer-or-abstention/research.md](file:///d:/Repos/KnowledgeOps/context/archive/2026-11-23-grounded-answer-or-abstention/research.md) — fundamenty grafu pytań, sesji `kops_session`, Langfuse i powłoki UI.
- [context/archive/2026-11-26-conflicting-sources/research.md](file:///d:/Repos/KnowledgeOps/context/archive/2026-11-26-conflicting-sources/research.md) — nakładka `synthetic@v1`, wyszukiwanie wielozestawowe ParadeDB i reguły zakresu.

---

## Open Questions (do rozstrzygnięcia w `/10x-plan resolved-case-audit`)

1. **Mechanizm checkpointingu grafu w Postgresie**: czy dodać zależność `langgraph-checkpoint-postgres` (`AsyncPostgresSaver` z dedykowanym połączeniem `autocommit=True` + `dict_row`, zgodnie z literalnym zapisem w `architecture-notes.md:23,30`), czy zapisywać stan każdego kroku grafu bezpośrednio w tabelach domenowych `0004_audits.sql` (z bezstanowym grafem wznawianym z wiersza tabeli)? *(Wymaga uwzględnienia zasady z `AGENTS.md`: „Nie zmieniaj stosu ani nie dodawaj frameworków bez decyzji użytkownika”.)*
2. **Zakres wyszukiwania (`include_synthetic`)**: czy audyt w S-08 domyślnie dziedziczy `settings.include_synthetic` (`True` w demo UI, pokazując `is_synthetic` i `chunk_set_ids` w szczegółach przygotowania jak w S-07), czy przeszukuje wyłącznie bazową migawkę TechQA?
3. **Sposób wyświetlania wyodrębnionych pól `FR-007` (`Kontekst sprawy`)**: brak makiety stanu rozwiniętego — czy rozwinąć `problem`, `environment`, `solution`, `constraints`, `missing_info` w zwijanym panelu bocznym / arkuszu (`PanelFrame`), czy w rozwijanej sekcji inline pod przyciskiem `Kontekst sprawy`?
4. **Teza w audycie (decyzja otwarta #3 z `design/mockups/README.md:76`)**: potwierdzić podejście z makiety `S3.dc.html` — przechowywanie i wyświetlanie obu: dosłownego fragmentu z notatki (`source_excerpt` + offsety podświetlone w notatce) oraz zwięzłej tezy weryfikowalnej na liście tez.
5. **Link z ekranu 1C (`AbstentionView.tsx:13`) do ekranu 2**: czy dodać w S-08 przycisk/link przejścia do „Przekaż sprawę do audytu” w widoku abstencji, czy udostępnić ekran 2 wyłącznie z nawigacji `NavRail`?
