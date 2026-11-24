# Odpowiedź z cytatami albo abstencja (S-02) — plan implementacji

## Overview

S-02 to gwiazda przewodnia roadmapy. Konsultant zadaje pytanie po angielsku. System szuka fragmentów w migawce TechQA, a model składa tezy z cytatami. Osobny weryfikator sprawdza, czy cytowany fragment wspiera konkretnie daną tezę. Konsultant dostaje odpowiedź złożoną wyłącznie z tez popartych albo jawną abstencję z listą sprawdzonych fragmentów.

Postęp pochodzi z rzeczywistych etapów grafu LangGraph. Dowód otwiera się w panelu bocznym: fragment, jego sąsiedztwo i cały dokument na żądanie. Odpowiedź jest zapisana w anonimowej sesji, a każde zapytanie zostawia ślad w Langfuse Cloud. Etap obejmuje też pełną powłokę aplikacji z zakresu S-03: przełącznik ról, PL/EN i oznaczenie DEMO.

Ten sam krok weryfikacji tezy wykorzysta później audyt (S-08), a S-06 go zmierzy.

## Current State Analysis

- **Backend:** FastAPI ma tylko `GET /api/health` (`backend/app/main.py:39-54`) i nie ma routerów.
  - Ustawienia: `Settings` z `database_url` i `techqa_dir` (`backend/app/settings.py:6-12`).
  - Pula: asynchroniczna pula psycopg, `PoolDep` (`backend/app/db.py:9-26`).
  - Migracje: własny runner SQL (`backend/app/migrations.py`). Istnieje tylko `0001_techqa_schema.sql`.
- **Wyszukiwanie z S-01:** `search_chunks` (`backend/app/techqa/search.py:39-46`) jest synchroniczne i zwraca 200-znakowy `snippet`. BM25 to `text ||| query` z `pdb.score(id)` i rozstrzyganiem remisów po `id COLLATE "C"` (`search.py:12-18`). Wywołują je tylko CLI i testy.
  - Na pełnej migawce TRAIN_Q000 trafia w `swg21996508` na pozycji 1 (`context/archive/2026-11-22-techqa-snapshot-import/`).
- **Schemat** (`backend/migrations/0001_techqa_schema.sql`):
  - `snapshots`, `documents` (`text` to znormalizowane ciało, `title`), `chunk_sets`, `chunks`.
  - `chunks` ma `ordinal`, `headings`, `start_offset`/`end_offset` w `documents.text` oraz `UNIQUE (chunk_set_id, doc_id, ordinal)`.
  - Fragmenty mają do 1500 znaków z nakładką 150 znaków. Mediana to 3 fragmenty na dokument, maksimum 159.
- **Pułapka importu:** import usuwa kaskadowo całą migawkę (`backend/app/techqa/importer.py:573-662`). Każda tabela z kluczem obcym do `chunks`, `documents` lub `snapshots` straciłaby wiersze przy reimporcie. Przegląd S-01 (`impl-review.md` F1) wskazał to wprost.
- **Brak zależności:** w `backend/pyproject.toml` nie ma LangChain, LangGraph, Langfuse ani SDK modelu. W `.env.example` nie ma zmiennych LLM ani Langfuse.
- **Frontend:** szablon React Router w trybie SPA z jedną trasą `index("routes/home.tsx")`, która renderuje ekran powitalny.
  - Klient openapi-fetch: `frontend/app/api/client.ts:5`.
  - Tailwind v4 z `@theme` w `frontend/app/app.css`.
  - Brak i18n, brak test runnera i brak Playwrighta.
- **Kontrakt:** CI sprawdza aktualność `backend/openapi.json` i `frontend/app/api/schema.d.ts` (`.github/workflows/ci.yml`, job `contract`).
- **Makiety:** `design/mockups/canvas/S1A.dc.html`, `S1P.dc.html`, `S1C.dc.html` (markup w linii 26), tokeny opisane w sekcji „Key Discoveries”.
- **AI Devs 4:** żaden przykład nie ocenia, czy fragment wspiera tezę (`01_01_grounding` tylko adnotuje tekst wynikami wyszukiwania). Krok weryfikacji i ścieżkę abstencji projektujemy od zera.
- **Dane pilotażu:** etykieta `is_impossible` dla TRAIN_Q002 (`MQRC_CLUSTER_RESOLUTION_ERROR`) nie jest zweryfikowana: „Przeszukaj korpus przed przygotowaniem etykiety” (`docs/raport-techqa.md:40`).

## Desired End State

Po `docker compose up -d db backend` i `npm run dev` konsultant otwiera aplikację i widzi powłokę z kanwy:
- nagłówek z logo, przełącznikiem ról z komunikatem, że rola nie jest kontrolą dostępu, oznaczeniem DEMO, przełącznikiem PL/EN (domyślnie PL) i migawką korpusu;
- nawigację z pozycją „Asystent”.

Po wpisaniu pytania widzi:
- **Postęp (1P):** kroki wynikające z rzeczywistych zdarzeń grafu.
- **Odpowiedź (1A):** tezy z numerami cytatów (przy tezie z kodem numer stoi przed blokiem kodu), wiersz źródeł i szczegóły przygotowania (migawka, zakres wyszukiwania, liczba sprawdzonych fragmentów, liczba pominiętych tez). Kliknięcie numeru otwiera panel dowodu z zaznaczonym fragmentem, sąsiedztwem rozwijanym w górę i w dół oraz całym dokumentem na żądanie.
- **Abstencję (1C):** wyjaśnienie, że brak dowodów nie znaczy „nie”, oraz panel sprawdzonych fragmentów.
- **Stan błędu**, gdy model lub baza zawiedzie, z możliwością ponowienia.

Odpowiedź ma adres `/odpowiedz/:id` i po odświeżeniu wraca z bazy. Inna sesja dostaje 404. Każde zapytanie ma ślad w Langfuse Cloud z etapami i identyfikatorami fragmentów, o ile ustawiono klucze.

Weryfikacja:
- kontrole backendu i frontendu oraz zgodność kontraktu przechodzą w CI;
- przebieg `live` daje odpowiedź z cytatem do `swg21996508` dla TRAIN_Q000 i abstencję dla ustalonej kontroli abstencji;
- zrzuty przy 1280 i 1440 px zestawione z kanwą akceptuje użytkownik.

### Key Discoveries:

- **SSE przez POST:** FastAPI 0.165 ma `fastapi.sse.EventSourceResponse` i `ServerSentEvent`, które działają także z POST. Postęp nie wymaga nowej biblioteki (dokumentacja FastAPI, „Server-Sent Events”).
- **Zdarzenia z grafu:** LangGraph emituje własne zdarzenia z węzła przez `langgraph.config.get_stream_writer()` i `astream(..., stream_mode=["updates", "custom"])`. To naturalne źródło zdarzeń etapów.
- **Langfuse:** `from langfuse.langchain import CallbackHandler` mapuje przebieg LangChain i LangGraph na ślad, a `handler.last_trace_id` zwraca id śladu. Bez `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` klient jest no-op z ostrzeżeniem, więc CI i lokalny start bez kluczy działają. Adres to `LANGFUSE_BASE_URL` (domyślnie chmura).
- **Okno dowodu bez dublowania nakładki:** wycinek `documents.text[prev.start_offset : next.end_offset]` z zaznaczeniem `[start_offset, end_offset)` bieżącego fragmentu. Fragmenty nakładają się o 150 znaków, więc sklejanie ich tekstów dublowałoby treść.
- **Identyfikatory fragmentów są deterministyczne** (`<snapshot>/sections-v1/<doc_id>/<ordinal>`, `importer.py:634`). Odpowiedź może je przechowywać jako tekst bez klucza obcego i nadal wskazywać ten sam fragment po reimporcie.
- **Tokeny z kanwy (S1A/S1P/S1C, linia 26):**
  - tekst `#1f2023`, wyciszony `#6b6f76`;
  - ramki `#d9d6cc`/`#e9e7e0`, powierzchnie `#f2f0ea`/`#f4f2ec`;
  - akcent `#c98a2c`, mocny akcent `#8f5512`, zaznaczenie `#f7e2b5`, aktywne źródło `#fbf2e2`;
  - główny/link `#2f5fc4`, sukces `#1a6b36`, fokus 2px `#2f5fc4`;
  - kroje: Inter (interfejs), Source Serif 4 (tekst dokumentu), `ui-monospace` (kod i id).
- **Kompletność tłumaczeń bez nowego frameworka:** słownik EN typowany kluczami słownika PL sprawia, że `npm run typecheck` padnie przy brakującym kluczu. AGENTS.md zabrania dodawania frameworków bez decyzji, więc nie dodajemy biblioteki i18n ani Vitesta.

## What We're NOT Doing

- **Kopiowanie odpowiedzi z cytatami i wąskie okno 390 px z arkuszem dowodu.** To S-05. Przycisk „Kopiuj odpowiedź z cytatami” z 1A nie wchodzi. Układ nie może jednak blokować węższych okien: nie zakładamy stałych szerokości, które psułyby się poniżej 1280 px.
- **Sprzeczne źródła i stan „różne zalecenia”.** To S-07. Teza oceniona przez weryfikator jako sprzeczna jest w S-02 pomijana tak samo jak niepoparta i liczona w „pominiętych tezach”.
- **Wektory, hybryda i RRF.** To S-04. Zakres wyszukiwania w szczegółach przygotowania mówi „BM25”, nie „hybrydowe” jak na makiecie, bo pokazujemy tylko rzeczywiste dane.
- **Przepisywanie zapytania przez LLM i reranking.** Pytanie trafia do BM25 wprost (S-13 i S-04 zmierzą alternatywy).
- **Cache odpowiedzi.** To S-14.
- **Pomiar abstencji, fałszywych odmów i wsparcia cytatów na zestawie oznaczonym.** To S-06. Tu są tylko kontrole działania (Q000, kontrola abstencji).
- **Retencja i usuwanie danych sesji.** Okres pozostaje otwarty (PRD pyt. 10) i blokuje publiczne demo, nie ten etap.
- **Linki nawigacji do „Przekaż sprawę do audytu” i „Analizy i decyzje”.** Dochodzą w S-08 i S-10 razem z ekranami. Do tego czasu nie pokazujemy linków prowadzących donikąd.
- **Lokalny Langfuse w Compose.** Ślad idzie do Langfuse Cloud (decyzja tego planu).
- **Zarządzanie wersjami promptów w Langfuse.** Wersją promptu jest hash jego pliku, zapisany w konfiguracji odpowiedzi i w metadanych śladu.
- **Ciemny motyw** (FR-022, Parked).
- **Konfiguracja Playwrighta.** Zrzuty w tym etapie robimy ręcznie przez przeglądarkę. Automatyzacja to `/10x-e2e-setup`.

## Implementation Approach

Kolejność to „dane → logika → API → interfejs”:

1. **Faza 1** daje asynchroniczny dostęp do fragmentów i dowodu oraz od razu ustala kontrolę abstencji (sprawdzenie Q002 w korpusie).
2. **Faza 2** buduje graf pytania jako czystą logikę. Model czatu jest wstrzykiwany, więc graf da się przetestować w CI na fałszywym modelu.
3. **Faza 3** podłącza graf do HTTP: SSE z postępem, zapis odpowiedzi w sesji, odczyt po id i kontrakt OpenAPI.
4. **Fazy 4–5** budują front: najpierw powłokę i słownik tekstów, potem ekrany.
5. **Faza 6** zamyka etap przebiegiem na żywo, kontrolą śladu, porównaniem z kanwą i dokumentacją przepływu danych.

**Reguła odpowiedzi** (wspólna dla grafu, testów i interfejsu):

1. `retrieve`: BM25 na pełnym pytaniu, `k = ANSWER_K` (domyślnie 8). Brak trafień oznacza abstencję bez wywołania modelu.
2. `draft`: jedno wywołanie modelu z ponumerowanymi fragmentami. Wynik to lista tez `{text, code | null, chunk_id, quote}`. Pusta lista oznacza, że model sam nie znalazł podstaw, i prowadzi do abstencji.
3. `quote_check` (kod, bez modelu): `quote` musi występować w tekście wskazanego fragmentu po normalizacji białych znaków. `chunk_id` musi należeć do pobranych. Teza, która nie przejdzie, jest odrzucona z powodem `quote_not_found` albo `unknown_chunk`. Dla tezy, która przejdzie, `quote_check` zapisuje offsety cytatu `[quote_start, quote_end)` względem oryginalnego (nieznormalizowanego) tekstu fragmentu.
4. `verify`: jedno wywołanie weryfikatora dla wszystkich ocalałych tez. Dla każdej tezy zwraca pola w kolejności `reasoning` → `verdict ∈ {supported, contradicted, insufficient}`. Weryfikator widzi tylko tezę i tekst jej fragmentu, nie całe pytanie, żeby oceniał wsparcie, a nie trafność tematu.
5. Decyzja:
   - co najmniej jedna teza `supported` → `compose`: odpowiedź z tez `supported` w kolejności szkicu, numery cytatów nadawane po fragmentach w kolejności pierwszego użycia, liczba pominiętych tez w szczegółach;
   - zero tez `supported` → `abstain`.

## Critical Implementation Details

**Timing & lifecycle:**
- Zapis do `answers` następuje po zakończeniu grafu, w tym samym generatorze SSE, przed wysłaniem zdarzenia `result` z `answer_id`. Klient przechodzi na `/odpowiedz/:id` dopiero wtedy, gdy wiersz już istnieje.
- Rozłączenie klienta w trakcie przerywa generator i nic nie zapisuje.
- `langfuse.flush()` jest blokujące. Wywołuj je w wątku (`run_in_threadpool`) w `finally` generatora, żeby nie blokować pętli zdarzeń.

**User experience spec:**
- Krok „Sprawdzanie, czy fragmenty wspierają odpowiedź” obejmuje zdarzenia `draft`, `quote_check` i `verify`.
- Trzeci krok to „Składanie odpowiedzi z cytatami” albo, przy abstencji, przejście prosto do ekranu 1C.
- Interfejs nie pokazuje czasów ani liczników, których nie ma w zdarzeniach.

**State sequencing:**
- Numer cytatu przypisuje `compose` po weryfikacji, nie `draft`. Numery są ciągłe (1..N) wyłącznie wśród tez pokazanych konsultantowi, bez dziur po tezach pominiętych.

## Faza 1: Wyszukiwanie i API dowodu

### Overview

Asynchroniczny dostęp do fragmentów, okna dowodu i całego dokumentu, endpointy dowodu i migawki oraz ustalenie kontroli abstencji.

### Changes Required:

#### 1. Asynchroniczne wyszukiwanie i odczyt dowodu

**File**: `backend/app/retrieval.py` (nowy)

**Intent**: Asynchroniczne odpowiedniki dla API i grafu, korzystające z puli. Kanoniczne SQL BM25 pozostaje w jednym miejscu. Synchroniczne `search_chunks` z CLI zostaje bez zmian, a zapytanie przenosimy do wspólnej stałej, żeby oba warianty nie rozjechały się.

**Contract**:
- `async def search_bm25(conn: AsyncConnection, query: str, *, chunk_set_id: str, k: int) -> list[RetrievedChunk]`. Zwraca `RetrievedChunk(rank, score, chunk_id, doc_id, title, headings, text)` z pełnym tekstem fragmentu i tytułem dokumentu (join z `documents`). Kolejność i rozstrzyganie remisów są takie jak w `search.py:12-18`.
- `async def get_evidence_window(conn, chunk_id: str, *, before: int, after: int) -> EvidenceWindow | None`. Zwraca `{chunk_id, snapshot_id, doc_id, title, headings, window_text, highlight_start, highlight_end, window_ordinal_from, window_ordinal_to, has_more_before, has_more_after}`. Offsety zaznaczenia są względne do `window_text`.
- `async def get_document(conn, snapshot_id: str, doc_id: str) -> DocumentText | None`. Zwraca `{snapshot_id, doc_id, title, text, chunks: [{chunk_id, ordinal, start_offset, end_offset}]}`, żeby panel mógł zaznaczyć cytat w całym dokumencie.
- `async def get_corpus_info(conn, chunk_set_id: str) -> CorpusInfo`. Zwraca `{snapshot_id, revision, revision_short (7 znaków), source, chunk_set_id, variant, document_count, chunk_count}`.

#### 2. Ustawienia

**File**: `backend/app/settings.py`

**Intent**: Parametry wyszukiwania i domyślny zestaw fragmentów w jednym miejscu.

**Contract**: nowe pola `chunk_set_id: str | None = None` (gdy puste, wyprowadzane z `load_manifest().chunk_set_id(ChunkerConfig())`), `answer_k: int = 8`, `evidence_context_chunks: int = 1`.

#### 3. Endpointy dowodu i migawki

**File**: `backend/app/api/evidence.py` (nowy router), `backend/app/main.py` (rejestracja routerów)

**Intent**: Panel dowodu i nagłówek pobierają dane po stabilnych identyfikatorach. To pierwszy router, więc ustala wzorzec `backend/app/api/`.

**Contract**:
- `GET /api/corpus` → `CorpusInfo`.
- `GET /api/evidence?chunk_id=...&before=1&after=1` → `EvidenceWindow`, 404 dla nieznanego id. `before` i `after` mieszczą się w zakresie 0–5. Identyfikator idzie w query, bo zawiera `/` i `@`.
- `GET /api/documents?snapshot_id=...&doc_id=...` → `DocumentText`, 404 gdy brak.

Wszystkie modele odpowiedzi to Pydantic z jawnymi nazwami, żeby typy frontu miały czytelne nazwy.

#### 4. Kontrola abstencji

**File**: `context/changes/grounded-answer-or-abstention/abstention-check.md` (nowy)

**Intent**: Przed oparciem weryfikacji na TRAIN_Q002 sprawdzić korpus.
- Wykonaj `python -m app.cli search` dla TRAIN_Q002 (pełne pytanie) oraz dla `MQRC_CLUSTER_RESOLUTION_ERROR` i `2189`.
- Jeśli wśród pierwszych 10 trafień jest dokument opisujący ten błąd, kontrolą abstencji staje się pytanie z makiety 1C: „After setting variables with `streamtool setproperty --application-ev` in Streams, do I need to restart the DB2 server that the database toolkit connects to?”.
- W przeciwnym razie zostaje TRAIN_Q002.

- Tą samą procedurą sprawdź pytanie z makiety 1C (pełne pytanie oraz `streamtool setproperty` i `application-ev`), bo TechQA zawiera technoty o InfoSphere Streams.
- Jeśli oba pytania mają w top 10 dokument odpowiadający na pytanie, zatrzymaj się i ustal z użytkownikiem inne pytanie kontrolne, zanim powstanie test `live` (Faza 2).

**Contract**: plik zawiera zapytania i wyniki (id i tytuły top 10) dla każdego sprawdzonego pytania, wniosek i dosłowny tekst wybranego pytania kontrolnego. Faza 2 (test `live`) i Faza 6 używają tego pytania.

#### 5. Testy

**File**: `backend/tests/conftest.py`, `backend/tests/techqa/conftest.py`, `backend/tests/api/__init__.py`, `backend/tests/test_retrieval.py`, `backend/tests/api/test_evidence.py` (nowe testy z `pytest.mark.db` na mini-migawce)

**Intent**: Kontrakt odczytu dowodu na syntetycznych fixture'ach oraz wspólne fikstury dla testów async i API, z których korzystają też Fazy 2 i 3.

**Contract**:
- Fikstury (wzorzec dla Faz 1–3):
  - `conn` i `imported_conn` przechodzą z `tests/techqa/conftest.py` do `tests/conftest.py`, bez zmiany zachowania testów S-01;
  - `anyio_backend` (`"asyncio"`) oraz `async_imported_conn`, czyli `AsyncConnection` na `temp_database` po imporcie mini-migawki; testy funkcji async mają `@pytest.mark.anyio` (wtyczka anyio przychodzi ze starlette, bez nowej zależności);
  - `api_client`: `monkeypatch.setenv("DATABASE_URL", temp_database)` po imporcie i `with TestClient(app)`, żeby lifespan utworzył pulę we własnej pętli; nie przekazujemy do aplikacji puli otwartej w pętli testu;
  - jeśli psycopg async na Windows wymaga pętli selector, `anyio_backend` ustawia ją jawnie.
- BM25 async zwraca tę samą kolejność co sync `search_chunks`.
- Okno dla pierwszego i ostatniego fragmentu dokumentu ma poprawne `has_more_*`.
- `window_text[highlight_start:highlight_end] == chunks.text`.
- Nieznane id daje 404.
- `get_document` zwraca offsety zgodne z niezmiennikiem `documents.text[start:end] == chunks.text`.

### Success Criteria:

#### Automated Verification:

- Kontrole backendu przechodzą: `cd backend; uv run ruff check .; uv run ruff format --check .; uv run mypy .`
- Testy wyszukiwania i dowodu przechodzą: `cd backend; uv run pytest tests/test_retrieval.py tests/api/test_evidence.py`
- Pełny zestaw testów backendu przechodzi: `cd backend; uv run pytest`

#### Manual Verification:

- `GET /api/evidence` dla pierwszego fragmentu `swg21996508` na pełnej migawce zwraca czytelne okno z zaznaczonym fragmentem
- `abstention-check.md` zawiera wynik przeszukania korpusu i wybrane pytanie kontrolne abstencji

**Implementation Note**: Po automatycznej weryfikacji zatrzymaj się na potwierdzenie ręcznych kroków przez człowieka.

---

## Faza 2: Graf odpowiedzi

### Overview

Graf LangGraph `retrieve → draft → quote_check → verify → compose | abstain` z wstrzykiwanym modelem czatu, schematami Pydantic, promptami w plikach, zdarzeniami etapów i śladem Langfuse.

### Changes Required:

#### 1. Zależności i konfiguracja modelu

**File**: `backend/pyproject.toml`, `backend/uv.lock`, `backend/app/settings.py`, `.env.example`

**Intent**: Dodać integrację z OpenAI przez LangChain, LangGraph i SDK Langfuse (przez `uv add`).

**Contract**:
- Pakiety: `langchain-openai`, `langgraph`, `langfuse`.
- Nowe ustawienia: `openai_api_key: SecretStr | None`, `chat_model: str`, `chat_timeout_s: float = 12` (jedno wywołanie modelu), `answer_deadline_s: float = 25` (całe zapytanie), `langfuse_public_key`, `langfuse_secret_key`, `langfuse_base_url` (wszystkie opcjonalne).
- `.env.example` dostaje te zmienne z komentarzem: bez `OPENAI_API_KEY` endpoint odpowiedzi zwraca błąd konfiguracji, a bez kluczy Langfuse ślad jest wyłączony.
- Wartość `CHAT_MODEL` to mały, aktualny model czatu OpenAI z obsługą strict structured output. Implementujący ustala ją z bieżącej oferty i cennika i zapisuje w `.env.example`.

#### 2. Schematy i prompty

**File**: `backend/app/answering/schemas.py`, `backend/app/answering/prompts/draft.md`, `backend/app/answering/prompts/verify.md` (nowe)

**Intent**: Wyjście ustrukturyzowane przez `with_structured_output` (strict).

**Contract**:
- `DraftOutput{claims: list[DraftClaim{text: str, code: str | null, chunk_id: str, quote: str}]}`. Pusta lista jest dozwolona.
- `VerifyOutput{verdicts: list[ClaimVerdict{claim_index: int, reasoning: str, verdict: Literal["supported","contradicted","insufficient"]}]}`.

Kluczowe instrukcje promptu `draft`:
- odpowiadaj po angielsku wyłącznie z podanych fragmentów;
- każda teza ma jeden `chunk_id` z listy i dosłowny `quote` z tego fragmentu;
- polecenia i kod tylko w `code`;
- gdy fragmenty nie odpowiadają na pytanie, zwróć pustą listę.

Kluczowe instrukcje promptu `verify`:
- oceniaj, czy fragment wspiera konkretnie tę tezę, a nie podobny temat;
- `insufficient` gdy brak podstaw;
- `contradicted` tylko gdy fragment twierdzi coś przeciwnego.

Wersja promptu to SHA-256 pliku (pierwsze 12 znaków).

#### 3. Graf i węzły

**File**: `backend/app/answering/graph.py`, `backend/app/answering/nodes.py` (nowe)

**Intent**: Logika z sekcji „Implementation Approach”. Każdy węzeł emituje zdarzenie etapu przez `get_stream_writer()`.

**Contract**:
- Stan: `{question, chunk_set_id, k, retrieved, draft_claims, rejected (z powodami), verdicts, outcome: "answered" | "abstained", answer}`.
- `build_answer_graph(*, chat_model: BaseChatModel, pool: AsyncPool, settings) -> CompiledGraph`.
- Zdarzenie etapu: `{"stage": "retrieve" | "draft" | "quote_check" | "verify" | "compose" | "abstain", "status": "started" | "done", "data": {...}}`. Dane po `retrieve` to `{"checked": n}`. Dane po `verify` to `{"supported": n, "omitted": m}`.
- Wynik `answered`:
  - `claims: [{text, code, citation: n}]`;
  - `citations: [{n, chunk_id, doc_id, title, headings, claims: [{claim_index, quote, quote_start, quote_end}]}]`. Jeden numer przypada na fragment, a lista `claims` obejmuje wszystkie pokazane tezy z tego fragmentu. Offsety cytatu są względne do tekstu fragmentu;
  - `checked_chunks: [{rank, chunk_id, doc_id, title, headings, score}]`;
  - `omitted_claims: m`.
- Wynik `abstained`: `checked_chunks`, `reason` (`no_hits` | `no_claims` | `none_supported`) i `omitted_claims`.

#### 4. Ślad Langfuse

**File**: `backend/app/observability.py` (nowy)

**Intent**: Jeden ślad na pytanie: węzły grafu jako spany, wywołania modelu jako generacje. Identyfikatory pobranych fragmentów, wersje promptów i model idą do metadanych.

**Contract**:
- `make_trace_handler() -> CallbackHandler`, przekazywany w `config={"callbacks": [...], "metadata": {...}, "run_name": "answer"}`.
- `flush_traces()` jest bezpieczne bez kluczy.
- Metadane: `chunk_set_id`, `k`, `chat_model`, `prompt_versions`, `retrieved_chunk_ids`.
- Do śladu nie trafia identyfikator sesji ani jego hash.

#### 5. Testy grafu

**File**: `backend/tests/answering/test_graph.py` (nowy, `pytest.mark.db`, na fiksturach z Fazy 1: `async_imported_conn`, `anyio`), `backend/tests/answering/fakes.py`, `backend/pyproject.toml` (marker `live`)

**Intent**: Deterministyczne ścieżki w CI na fałszywym modelu ze skryptowanymi odpowiedziami strukturalnymi oraz kontrola na żywo poza CI.

**Contract**:
- Przypadki na fałszywym modelu:
  - pełna odpowiedź;
  - częściowa: 2 z 3 tez `supported`, odpowiedź z 2 tez, `omitted_claims=1`, numery 1..N bez dziur;
  - abstencja `no_hits`, bez wywołania modelu;
  - abstencja `no_claims`;
  - abstencja `none_supported`;
  - cytat spoza fragmentu odrzucony przez `quote_check`;
  - `chunk_id` spoza pobranych odrzucony;
  - teza `contradicted` pominięta;
  - kolejność zdarzeń etapów.
- Marker `live`, w CI pomijany (domyślne `-m "not live"` w konfiguracji pytest), z osobną fiksturą łączącą się z bazą z `DATABASE_URL` zamiast `temp_database`: na pełnej migawce i prawdziwym OpenAI TRAIN_Q000 daje `answered` z cytatem do `swg21996508`, a pytanie kontrolne z `abstention-check.md` daje `abstained`.

### Success Criteria:

#### Automated Verification:

- Zależności są zablokowane: `cd backend; uv sync --locked`
- Kontrole backendu przechodzą: `cd backend; uv run ruff check .; uv run ruff format --check .; uv run mypy .`
- Testy grafu na fałszywym modelu przechodzą: `cd backend; uv run pytest tests/answering`
- Pełny zestaw testów backendu przechodzi bez kluczy OpenAI i Langfuse: `cd backend; uv run pytest`

#### Manual Verification:

- `uv run pytest -m live` na pełnej migawce: TRAIN_Q000 odpowiada z cytatem do `swg21996508`, a pytanie kontrolne kończy się abstencją
- Ślad przebiegu `live` w Langfuse Cloud ma spany węzłów, generacje `draft` i `verify` oraz identyfikatory pobranych fragmentów

**Implementation Note**: Po automatycznej weryfikacji zatrzymaj się na potwierdzenie ręcznych kroków przez człowieka.

---

## Faza 3: API odpowiedzi i sesja

### Overview

Tabela odpowiedzi bez kluczy obcych do danych migawki, anonimowa sesja w ciasteczku, strumień SSE z postępem i wynikiem, odczyt zapisanej odpowiedzi oraz aktualny kontrakt OpenAPI i typy frontu.

### Changes Required:

#### 1. Migracja `answers`

**File**: `backend/migrations/0002_answers.sql` (nowy)

**Intent**: Trwały zapis pytania i wyniku w sesji. Brak kluczy obcych do `snapshots`, `documents` i `chunks`, żeby reimport nie kasował odpowiedzi.

**Contract**: kolumny tabeli `answers`:
- `id uuid PK`;
- `session_hash text NOT NULL` (SHA-256 tokenu sesji);
- `question text NOT NULL`;
- `outcome text NOT NULL CHECK (outcome IN ('answered','abstained','failed'))`;
- `snapshot_id text NOT NULL`, `chunk_set_id text NOT NULL`;
- `result jsonb`, `config jsonb NOT NULL` (model, k, wersje promptów, chunk set);
- `error text`, `trace_id text`, `duration_ms int`;
- `created_at timestamptz NOT NULL DEFAULT now()`.

Indeks na `(session_hash, created_at DESC)`.

#### 2. Sesja anonimowa

**File**: `backend/app/session.py` (nowy)

**Intent**: Rozdzielenie danych odwiedzających bez kont (PRD Access Control). Ten sam mechanizm wykorzysta S-08.

**Contract**:
- Ciasteczko `kops_session`: losowy token `secrets.token_urlsafe(32)`, `HttpOnly`, `SameSite=Lax`, `Path=/api`, `Secure` sterowane ustawieniem `session_cookie_secure: bool = False`.
- Zależność `SessionDep` zwraca hash tokenu. Brak ciasteczka przy POST oznacza wydanie nowego. Przy GET brak ciasteczka daje 404, bez tworzenia sesji.
- W bazie trzymamy tylko hash.

#### 3. Endpointy odpowiedzi

**File**: `backend/app/api/answers.py` (nowy router)

**Intent**: Strumień postępu z rzeczywistych etapów i odczyt wyniku.

**Contract**:
- `POST /api/answers` z ciałem `{question: str}` (przycięte, 1–2000 znaków, inaczej 422), `response_class=EventSourceResponse`. Zdarzenia SSE:
  - `event: stage` z danymi zdarzenia etapu z Fazy 2;
  - `event: result` z `{answer_id, outcome}`;
  - `event: error` z `{answer_id | null, code: "model_unavailable" | "model_not_configured" | "database_unavailable" | "internal", message}`.
- Kolejność: zapis → `result`. Graf działa w `asyncio.timeout(answer_deadline_s)`. Błąd modelu (timeout wywołania lub całego zapytania, odpowiedź poza schematem, błąd API) zapisuje wiersz `outcome='failed'` z `error` i wysyła `error`.
- Brak `OPENAI_API_KEY` daje `error` z kodem `model_not_configured`, bez zapisu.
- `GET /api/answers/{id}` → `AnswerRecord{id, question, outcome, result, snapshot_id, chunk_set_id, config, created_at, duration_ms}`. 404 dla nieistniejącego id albo innej sesji, bez rozróżnienia.

#### 4. Kontrakt

**File**: `backend/openapi.json`, `frontend/app/api/schema.d.ts`

**Intent**: Typy frontu dla nowych endpointów, w tym modele zdarzeń SSE jako nazwane schematy.

**Contract**: `uv run python scripts/export_openapi.py`, potem `npm run api:types`. Modele zdarzeń (`StageEvent`, `ResultEvent`, `ErrorEvent`) trafiają do `components.schemas`, np. przez jawne odwołanie w odpowiedzi endpointu albo `openapi_extra`.

#### 5. Testy

**File**: `backend/tests/api/test_answers.py` (nowy, `pytest.mark.db`, na fiksturze `api_client` z Fazy 1)

**Intent**: Kontrakt HTTP na fałszywym modelu (nadpisanie zależności fabryki modelu).

**Contract**:
- Strumień zawiera etapy w kolejności i kończy się `result`.
- `GET` w tej samej sesji zwraca zapisany wynik.
- Inne ciasteczko i brak ciasteczka dają 404.
- Błąd modelu daje `failed` i `error`.
- Brak klucza daje `model_not_configured` bez wiersza.
- Puste pytanie daje 422.
- Test reimportu: wiersz `answers` przetrwa `import_snapshot` (mini-migawka).

### Success Criteria:

#### Automated Verification:

- Migracja nakłada się czysto: `cd backend; uv run python -m app.cli migrate`
- Testy API odpowiedzi przechodzą: `cd backend; uv run pytest tests/api/test_answers.py`
- Pełne kontrole backendu przechodzą: `cd backend; uv run ruff check .; uv run ruff format --check .; uv run mypy .; uv run pytest`
- Kontrakt jest aktualny (ponowna generacja po `git add` nie zmienia plików): `git add backend/openapi.json frontend/app/api/schema.d.ts; cd backend; uv run python scripts/export_openapi.py; cd ../frontend; npm run api:types; git diff --exit-code ../backend/openapi.json app/api/schema.d.ts`
- Typy frontu się kompilują: `cd frontend; npm run typecheck`

#### Manual Verification:

- `curl -N -X POST` na `/api/answers` z pytaniem TRAIN_Q000 pokazuje kolejne zdarzenia `stage`, a potem `result` w czasie widocznie krótszym niż 10 s

**Implementation Note**: Po automatycznej weryfikacji zatrzymaj się na potwierdzenie ręcznych kroków przez człowieka.

---

## Faza 4: Powłoka aplikacji (zakres S-03)

### Overview

Tokeny i kroje z kanwy oraz wspólny układ: nagłówek z logo, przełącznik ról z komunikatem, DEMO z opisem, PL/EN (domyślnie PL) i informacja o migawce. Do tego nawigacja i słownik tekstów z kontrolą kompletności przez typy.

### Changes Required:

#### 1. Tokeny i kroje

**File**: `frontend/app/app.css`, `frontend/app/root.tsx`

**Intent**: Przenieść tokeny z „Key Discoveries” do `@theme` (kolory, fokus, kroje Inter, Source Serif 4, mono). Usunąć ciemne tło szablonu z `prefers-color-scheme`, bo ciemny motyw jest w Parked. Uszanować `prefers-reduced-motion`.

**Contract**: nazwy tokenów semantyczne (`--color-text`, `--color-muted`, `--color-border`, `--color-surface`, `--color-accent`, `--color-accent-strong`, `--color-mark`, `--color-primary`, `--color-success`, `--font-serif`, `--font-mono`). Fonty ładowane w `root.tsx` jak obecnie Inter.

#### 2. Słownik tekstów i język

**File**: `frontend/app/i18n/pl.ts`, `frontend/app/i18n/en.ts`, `frontend/app/i18n/context.tsx` (nowe)

**Intent**: Wszystkie teksty interfejsu w słownikach. PL z makiet jest bazą, EN to tłumaczenie. Cytaty i treść odpowiedzi nie są tłumaczone.

**Contract**:
- `pl` jest `as const`, a `en: Record<keyof typeof pl, string>`, więc brakujący klucz to błąd `tsc`.
- `useT()` zwraca funkcję po kluczu.
- Wybrany język trafia do `localStorage` (`kops.lang`) i ustawia `<html lang>`.

#### 3. Rola

**File**: `frontend/app/session/role.tsx` (nowy)

**Intent**: Przełącznik Konsultant/Redaktor (FR-011). Rola w S-02 nie zmienia uprawnień ani danych.

**Contract**:
- Kontekst roli z `localStorage` (`kops.role`), domyślnie Konsultant.
- Kontrolka `role="group"` z `aria-label` i `aria-pressed`.
- Stały komunikat (tooltip DEMO i tekst przy przełączniku), że przełącznik nie jest kontrolą dostępu.

#### 4. Układ i nawigacja

**File**: `frontend/app/components/shell/*` (nowe: `AppHeader`, `NavRail`, `DemoBadge`, `LanguageSwitch`, `RoleSwitch`), `frontend/app/routes/_layout.tsx`, `frontend/app/routes.ts`

**Intent**: Wspólny układ dla tras aplikacji według S1A/S1P (szyna 56 px z przyciskiem „Rozwiń menu z podpisami” i rozwinięta nawigacja 232 px).

**Contract**:
- Nawigacja ma jedną pozycję „Asystent”.
- Informacja o migawce pochodzi z `GET /api/corpus` (np. „Korpus TechQA”, title „Migawka 0b5bbc8”). Gdy endpoint zawiedzie, wyświetla się neutralny tekst bez migawki.
- Ikony to inline SVG jak na kanwie.
- Fokus jest widoczny na wszystkich kontrolkach.

### Success Criteria:

#### Automated Verification:

- Kontrole frontu przechodzą, w tym kompletność słownika EN przez typy: `cd frontend; npm run lint; npm run format:check; npm run typecheck; npm run build`

#### Manual Verification:

- Nagłówek przy 1280 i 1440 px odpowiada kanwie: logo, role, DEMO z opisem, PL/EN, migawka
- Przełączenie na EN zmienia wszystkie teksty interfejsu i `lang`, a odświeżenie zachowuje wybór języka i roli
- Przełącznik ról i język działają z klawiatury i mają czytelne etykiety dla czytnika ekranu

**Implementation Note**: Po automatycznej weryfikacji zatrzymaj się na potwierdzenie ręcznych kroków przez człowieka.

---

## Faza 5: Ekrany 1P, 1A i 1C

### Overview

Ekran asystenta: pole pytania, postęp z prawdziwych etapów, odpowiedź z cytatami i panelem dowodu, abstencja z panelem sprawdzonych fragmentów oraz stan błędu. Trasy `/` (nowe pytanie) i `/odpowiedz/:id` (zapisana odpowiedź).

### Changes Required:

#### 1. Klient strumienia

**File**: `frontend/app/api/answers.ts` (nowy)

**Intent**: POST z odczytem SSE przez `fetch` i `ReadableStream`. `EventSource` obsługuje tylko GET.

**Contract**:
- `askQuestion(question, {signal, onStage}) -> Promise<ResultEvent | ErrorEvent>`. Typy pochodzą z `schema.d.ts`.
- Parser obsługuje zdarzenia rozcięte między porcjami.
- `AbortController` przerywa żądanie przy opuszczeniu widoku.
- `getAnswer(id)` i `getEvidence(...)`/`getDocument(...)` idą przez openapi-fetch z `credentials: "same-origin"`.

#### 2. Pole pytania i postęp (1P)

**File**: `frontend/app/routes/assistant.tsx`, `frontend/app/components/assistant/Composer.tsx`, `ProgressCard.tsx` (nowe)

**Intent**: Kompozytor i karta postępu według S1P.

**Contract**:
- Kompozytor:
  - `aria-label` pola pytania;
  - podpowiedź o zakresie (cała dokumentacja TechQA, bez internetu, pytania i odpowiedzi po angielsku);
  - przycisk „Zapytaj”, wyłączony dla pustego pytania i w trakcie;
  - Enter wysyła, Shift+Enter daje nową linię.
- Karta postępu `role="status"` z trzema krokami. Stan kroku (oczekuje, trwa, zakończony) wynika wyłącznie z otrzymanych zdarzeń. Status to zawsze ikona i słowo.
- Po `result` następuje nawigacja do `/odpowiedz/:id`.

#### 3. Odpowiedź (1A) i panel dowodu

**File**: `frontend/app/routes/answer.tsx`, `frontend/app/components/assistant/AnswerView.tsx`, `CitationMarker.tsx`, `SourcesRow.tsx`, `PreparationDetails.tsx`, `EvidencePanel.tsx` (nowe)

**Intent**: Widok według S1A.

**Contract**:
- **Teza:** numer cytatu to przycisk `aria-label="Cytat n z N"`. Przy tezie z `code` numer kończy zdanie tezy, a blok kodu jest pod nim z przyciskiem „Kopiuj” samego kodu. Aktywna teza ma lewy pasek akcentu.
- **Wiersz źródeł:** „Źródło · <doc_id>” albo lista dokumentów, pigułki z numerami i nagłówkiem sekcji.
- **Status w 1A:** „Sprawdzone cytaty: X z N”, gdzie X to liczba cytatów otwartych w panelu w tym widoku (stan klienta, nie zapisywany), plus przycisk „Otwórz wszystkie cytaty” przechodzący po kolei.
- **Szczegóły przygotowania** (`<details>`, zwinięte): migawka (krótka rewizja), zakres „BM25, zestaw `<variant>`, top k”, liczba sprawdzonych fragmentów, liczba pominiętych tez, model i czas. Wszystkie wartości pochodzą z `AnswerRecord`, bez tekstów przykładowych.
- **Panel dowodu** (`<aside aria-label>`):
  - „Źródło n z N” z poprzednim, następnym i zamknięciem;
  - pole „Wspiera tezę n” z treścią wszystkich tez z `citations[n].claims`;
  - tytuł, `doc_id`, nagłówki, „data dokumentu: nieznana”, migawka;
  - okno z `GET /api/evidence`, sąsiedztwo wyciszonym krojem szeryfowym, granice cytowanego fragmentu zaznaczone subtelnie (`highlight_start`/`highlight_end`), a cytaty w `<mark>` jak na S1A (`highlight_start + quote_start` … `highlight_start + quote_end`);
  - przyciski „Więcej kontekstu powyżej/poniżej” (zwiększają `before`/`after`, ukryte przy `has_more_*=false`);
  - „Pokaż cały dokument” (`GET /api/documents` z zaznaczeniem i przewinięciem do fragmentu).
- **Klawiatura:** Escape zamyka panel, a fokus wraca na numer cytatu.

#### 4. Abstencja (1C)

**File**: `frontend/app/components/assistant/AbstentionView.tsx`, `CheckedChunksPanel.tsx` (nowe)

**Intent**: Widok według S1C, bez czerwieni.

**Contract**:
- Nagłówek „Nie znaleziono wystarczających dowodów”, wyjaśnienie i notka, że to nie oznacza odpowiedzi „nie” ani braku informacji w całym korpusie.
- Akcje:
  - „Doprecyzuj pytanie” ustawia fokus w kompozytorze z poprzednim pytaniem;
  - „Sprawdzone fragmenty (n)” otwiera panel.
- Pozycji „Po rozwiązaniu sprawy przekaż ją do audytu” nie pokazujemy do S-08.
- Panel listuje `checked_chunks` (`doc_id`, sekcja, tytuł) z „Otwórz fragment”. Otwiera on ten sam panel dowodu bez pola „Wspiera tezę”, a bez cytatu w `<mark>` jest cały fragment. Lista pokazuje pierwsze 3 pozycje i przycisk „Pokaż pozostałe”.
- Szczegóły przygotowania podają rzeczywisty powód (`no_hits`/`no_claims`/`none_supported`) słowami.

#### 5. Stan błędu i brak odpowiedzi

**File**: `frontend/app/components/assistant/ErrorState.tsx` (nowy)

**Intent**: Stan, którego makiety nie pokazują, zaprojektowany w tonie 1C: neutralny, z ikoną i słowem.

**Contract**:
- Komunikat zależny od `code`:
  - `model_not_configured`: informacja dla operatora o braku klucza;
  - `model_unavailable` i `database_unavailable`: „spróbuj ponownie”;
  - `internal`: ogólny.
- Przycisk „Spróbuj ponownie” wysyła to samo pytanie.
- Trasa `/odpowiedz/:id` z 404 pokazuje „Nie znaleziono odpowiedzi w tej sesji” z linkiem do nowego pytania.
- Odpowiedź `failed` pokazuje stan błędu z pytaniem.

### Success Criteria:

#### Automated Verification:

- Kontrole frontu przechodzą: `cd frontend; npm run lint; npm run format:check; npm run typecheck; npm run build`
- Kontrakt pozostaje aktualny (porównanie z indeksem): `git add frontend/app/api/schema.d.ts; cd frontend; npm run api:types; git diff --exit-code app/api/schema.d.ts`

#### Manual Verification:

- Pytanie TRAIN_Q000 pokazuje kroki postępu w kolejności zdarzeń, potem odpowiedź z numerami cytatów i cytatem do `swg21996508`
- Panel dowodu pokazuje zaznaczony fragment, rozwija kontekst w górę i w dół i otwiera cały dokument z zaznaczeniem
- Pytanie kontrolne abstencji pokazuje ekran 1C z listą sprawdzonych fragmentów, a każdy otwiera się w panelu
- Odświeżenie `/odpowiedz/:id` przywraca odpowiedź, a otwarcie tego adresu w oknie prywatnym daje stan „Nie znaleziono odpowiedzi w tej sesji”
- Zatrzymany backend lub brak klucza daje stan błędu ze słowem i ikoną oraz działające ponowienie
- Panel dowodu, numery cytatów i kompozytor obsługuje się samą klawiaturą (Tab, Enter, Escape z powrotem fokusu)

**Implementation Note**: Po automatycznej weryfikacji zatrzymaj się na potwierdzenie ręcznych kroków przez człowieka.

---

## Faza 6: Weryfikacja i dokumentacja

### Overview

Przebieg na żywo, kontrola śladu, porównanie z kanwą, opis przepływu danych do usług zewnętrznych oraz notatki o decyzjach, które zmieniają dokumenty fundamentowe.

### Changes Required:

#### 1. Przepływ danych

**File**: `docs/przeplyw-danych.md` (nowy)

**Intent**: Odpowiedź planu technicznego na PRD pyt. 11 dla stanu po S-02.

**Contract**: tabela z kolumnami: dane, cel, czas przechowywania. Wiersze:
- do OpenAI: pytanie i teksty pobranych fragmentów;
- do Langfuse Cloud: pytanie, fragmenty, tezy, werdykty, model, czasy; bez sesji;
- do bazy (`answers`): pytanie, wynik, hash sesji, bez retencji, co blokuje publiczne demo;
- do logów backendu.

Do tego zalecenie, żeby nie wklejać danych osobowych, i odwołanie do pyt. 10.

#### 2. Notatki o decyzjach

**File**: `context/foundation/architecture-notes.md`, `context/foundation/roadmap.md`

**Intent**: Zapisać odstępstwa i rozstrzygnięcia z planowania S-02.

**Contract**:
- `architecture-notes.md`:
  - „Otwarte 1” rozstrzygnięte dla czatu: OpenAI. Embeddingi wybiera S-04.
  - Sekcja Langfuse: Cloud już od S-02, a nie tylko dla demo.
  - Sesja anonimowa wchodzi w S-02.
- `roadmap.md`:
  - w S-03 notatka, że zakres realizuje S-02, a S-03 zamyka się razem z S-02;
  - w S-02 rozstrzygnięte Unknowns (dostawca, metoda oceny, znacznik przed blokiem kodu);
  - Open Roadmap Questions poz. 9 (język domyślny: polski) i 13 (czat: OpenAI) oznaczone jako rozstrzygnięte.
- `design/mockups/README.md`: decyzja otwarta nr 1 rozstrzygnięta (numer przed blokiem kodu) i nr 6 rozstrzygnięta (domyślnie polski).

### Success Criteria:

#### Automated Verification:

- Pełne kontrole backendu przechodzą: `cd backend; uv run ruff check .; uv run ruff format --check .; uv run mypy .; uv run pytest`
- Pełne kontrole frontu przechodzą: `cd frontend; npm run lint; npm run format:check; npm run typecheck; npm run build`
- CI na gałęzi jest zielone (jobs `backend`, `frontend`, `contract`)

#### Manual Verification:

- `uv run pytest -m live` przechodzi na pełnej migawce (TRAIN_Q000 z cytatem do `swg21996508`, pytanie kontrolne kończy się abstencją)
- Ślad TRAIN_Q000 w Langfuse Cloud ma etapy, identyfikatory pobranych fragmentów, wersje promptów i czasy
- Zrzuty 1P, 1A i 1C przy 1280 i 1440 px zestawione z kanwą przechodzą listę kontrolną z „Jak weryfikujemy” i są zaakceptowane przez użytkownika
- `docs/przeplyw-danych.md` i notatki w dokumentach fundamentowych odpowiadają decyzjom z planu

**Implementation Note**: Po automatycznej weryfikacji zatrzymaj się na potwierdzenie ręcznych kroków przez człowieka.

---

## Testing Strategy

### Unit Tests:

- `quote_check`:
  - normalizacja białych znaków;
  - cytat częściowo poza fragmentem;
  - cytat z innego pobranego fragmentu niż wskazany;
  - nieznany `chunk_id`.
- Składanie odpowiedzi:
  - numery 1..N w kolejności pierwszego użycia;
  - dwie tezy z tego samego fragmentu dostają ten sam numer, a `citations[n].claims` zawiera obie z ich cytatami;
  - offsety cytatu po normalizacji białych znaków wskazują w oryginalnym tekście fragmentu dokładnie cytat;
  - pominięte tezy nie zostawiają dziur.
- Okno dowodu: pierwszy i ostatni fragment dokumentu, dokument jednofragmentowy, `before`/`after` poza zakresem.

### Integration Tests:

- Graf na fałszywym modelu: wszystkie ścieżki z Fazy 2 oraz kolejność zdarzeń.
- API: SSE od pierwszego etapu do `result`, odczyt w sesji, izolacja sesji, błąd modelu, brak klucza, walidacja pytania, przetrwanie odpowiedzi po reimporcie.
- `live` (ręcznie): TRAIN_Q000 i pytanie kontrolne abstencji na pełnej migawce.

### Manual Testing Steps:

1. `docker compose up -d db backend`, `cd frontend; npm run dev`, ustawione `OPENAI_API_KEY` i klucze Langfuse w `.env`.
2. Zadaj TRAIN_Q000. Obserwuj kroki postępu, potem odpowiedź z cytatem do `swg21996508`. Otwórz każdy cytat, rozwiń kontekst, otwórz cały dokument.
3. Zadaj pytanie kontrolne abstencji. Sprawdź ekran 1C, otwórz sprawdzone fragmenty.
4. Odśwież `/odpowiedz/:id`, otwórz go w oknie prywatnym (404 w innej sesji).
5. Zatrzymaj backend w trakcie i usuń klucz. Sprawdź stany błędu.
6. Przełącz EN, sprawdź teksty i `lang`. Przełącz rolę, sprawdź komunikat o braku kontroli dostępu.
7. Otwórz ślad w Langfuse Cloud.

## Performance Considerations

- Budżet to p95 < 10 s dla odpowiedzi lub abstencji (PRD NFR). Składowe: BM25 (milisekundy), `draft` i `verify` (dwa wywołania modelu, dominują czas).
- `chat_timeout_s` (12 s) ogranicza każde wywołanie, a `answer_deadline_s` (25 s) całe zapytanie. Przekroczenie któregokolwiek daje `failed` z `model_unavailable`, a nie wiszący strumień.
- Postęp jest widoczny od pierwszej sekundy (zdarzenie `retrieve` przed pierwszym wywołaniem modelu).
- Pomiar p95 na zestawie należy do S-06. Tu `duration_ms` zapisujemy dla każdej odpowiedzi.
- `GET /api/documents` może zwrócić do ~178 KB tekstu, co jest akceptowalne bez paginacji. Okno dowodu jest domyślną ścieżką (FR-004).

## Migration Notes

- `0002_answers.sql` tylko dodaje tabelę. Runner migracji odmówi pracy, jeśli zmienisz zastosowany już plik, więc poprawki idą w kolejnych migracjach.
- Tabela `answers` nie ma kluczy obcych do danych migawki. `snapshot_id` i `chunk_set_id` zapisane w wierszu mówią, na jakim stanie korpusu powstała odpowiedź. Po imporcie innej migawki stare odpowiedzi nadal się otwierają, ale ich dowody mogą zwracać 404, a panel pokazuje wtedy komunikat „fragment niedostępny w bieżącej migawce”.

## References

- Roadmapa: `context/foundation/roadmap.md` (S-02, S-03, „Jak weryfikujemy”)
- Wymagania: `context/foundation/prd.md` (US-01, FR-001–FR-004, FR-011, FR-018, FR-020, Business Logic, Guardrails, NFR)
- Architektura: `context/foundation/architecture-notes.md`
- Makiety: `design/mockups/README.md`, `design/mockups/canvas/S1A.dc.html`, `S1P.dc.html`, `S1C.dc.html`
- Poprzednia zmiana: `context/archive/2026-11-22-techqa-snapshot-import/` (plan, raport importu, przegląd F1)
- Wyszukiwanie: `backend/app/techqa/search.py:12-46`
- Import i kaskada: `backend/app/techqa/importer.py:573-662`, `:634`
- Dane pilotażu: `docs/raport-techqa.md:37-40`, `docs/pilotaz-audytu-techqa.md:15-18,87`
- AI Devs 4: `01_01_grounding` (cache etapów, test dosłowności cytatu), `01_01_structured` (kolejność pól, wartości „unknown”), `03_01_observability` (span na etap, flush w `finally`)

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Wyszukiwanie i API dowodu

#### Automated

- [x] 1.1 Kontrole backendu przechodzą: `cd backend; uv run ruff check .; uv run ruff format --check .; uv run mypy .` — c9c3f1f
- [x] 1.2 Testy wyszukiwania i dowodu przechodzą: `cd backend; uv run pytest tests/test_retrieval.py tests/api/test_evidence.py` — c9c3f1f
- [x] 1.3 Pełny zestaw testów backendu przechodzi: `cd backend; uv run pytest` — c9c3f1f

#### Manual

- [x] 1.4 `GET /api/evidence` dla pierwszego fragmentu `swg21996508` na pełnej migawce zwraca czytelne okno z zaznaczonym fragmentem — c9c3f1f
- [x] 1.5 `abstention-check.md` zawiera wynik przeszukania korpusu i wybrane pytanie kontrolne abstencji — c9c3f1f

### Phase 2: Graf odpowiedzi

#### Automated

- [x] 2.1 Zależności są zablokowane: `cd backend; uv sync --locked` (53fa1a8)
- [x] 2.2 Kontrole backendu przechodzą: `cd backend; uv run ruff check .; uv run ruff format --check .; uv run mypy .` (53fa1a8)
- [x] 2.3 Testy grafu na fałszywym modelu przechodzą: `cd backend; uv run pytest tests/answering` (53fa1a8)
- [x] 2.4 Pełny zestaw testów backendu przechodzi bez kluczy OpenAI i Langfuse: `cd backend; uv run pytest` (53fa1a8)

#### Manual

- [ ] 2.5 `uv run pytest -m live` na pełnej migawce: TRAIN_Q000 odpowiada z cytatem do `swg21996508`, a pytanie kontrolne kończy się abstencją (53fa1a8)
- [ ] 2.6 Ślad przebiegu `live` w Langfuse Cloud ma spany węzłów, generacje `draft` i `verify` oraz identyfikatory pobranych fragmentów (53fa1a8)

### Phase 3: API odpowiedzi i sesja

#### Automated

- [x] 3.1 Migracja nakłada się czysto: `cd backend; uv run python -m app.cli migrate` (89d8e45)
- [x] 3.2 Testy API odpowiedzi przechodzą: `cd backend; uv run pytest tests/api/test_answers.py` (89d8e45)
- [x] 3.3 Pełne kontrole backendu przechodzą: `cd backend; uv run ruff check .; uv run ruff format --check .; uv run mypy .; uv run pytest` (89d8e45)
- [x] 3.4 Kontrakt jest aktualny (ponowna generacja po `git add` nie zmienia plików): `git add backend/openapi.json frontend/app/api/schema.d.ts; cd backend; uv run python scripts/export_openapi.py; cd ../frontend; npm run api:types; git diff --exit-code ../backend/openapi.json app/api/schema.d.ts` (89d8e45)
- [x] 3.5 Typy frontu się kompilują: `cd frontend; npm run typecheck` (89d8e45)

#### Manual

- [ ] 3.6 `curl -N -X POST` na `/api/answers` z pytaniem TRAIN_Q000 pokazuje kolejne zdarzenia `stage`, a potem `result` w czasie widocznie krótszym niż 10 s (89d8e45)

### Phase 4: Powłoka aplikacji (zakres S-03)

#### Automated

- [x] 4.1 Kontrole frontu przechodzą, w tym kompletność słownika EN przez typy: `cd frontend; npm run lint; npm run format:check; npm run typecheck; npm run build`

#### Manual

- [ ] 4.2 Nagłówek przy 1280 i 1440 px odpowiada kanwie: logo, role, DEMO z opisem, PL/EN, migawka
- [ ] 4.3 Przełączenie na EN zmienia wszystkie teksty interfejsu i `lang`, a odświeżenie zachowuje wybór języka i roli
- [ ] 4.4 Przełącznik ról i język działają z klawiatury i mają czytelne etykiety dla czytnika ekranu

### Phase 5: Ekrany 1P, 1A i 1C

#### Automated

- [ ] 5.1 Kontrole frontu przechodzą: `cd frontend; npm run lint; npm run format:check; npm run typecheck; npm run build`
- [ ] 5.2 Kontrakt pozostaje aktualny (porównanie z indeksem): `git add frontend/app/api/schema.d.ts; cd frontend; npm run api:types; git diff --exit-code app/api/schema.d.ts`

#### Manual

- [ ] 5.3 Pytanie TRAIN_Q000 pokazuje kroki postępu w kolejności zdarzeń, potem odpowiedź z numerami cytatów i cytatem do `swg21996508`
- [ ] 5.4 Panel dowodu pokazuje zaznaczony fragment, rozwija kontekst w górę i w dół i otwiera cały dokument z zaznaczeniem
- [ ] 5.5 Pytanie kontrolne abstencji pokazuje ekran 1C z listą sprawdzonych fragmentów, a każdy otwiera się w panelu
- [ ] 5.6 Odświeżenie `/odpowiedz/:id` przywraca odpowiedź, a otwarcie tego adresu w oknie prywatnym daje stan „Nie znaleziono odpowiedzi w tej sesji”
- [ ] 5.7 Zatrzymany backend lub brak klucza daje stan błędu ze słowem i ikoną oraz działające ponowienie
- [ ] 5.8 Panel dowodu, numery cytatów i kompozytor obsługuje się samą klawiaturą (Tab, Enter, Escape z powrotem fokusu)

### Phase 6: Weryfikacja i dokumentacja

#### Automated

- [ ] 6.1 Pełne kontrole backendu przechodzą: `cd backend; uv run ruff check .; uv run ruff format --check .; uv run mypy .; uv run pytest`
- [ ] 6.2 Pełne kontrole frontu przechodzą: `cd frontend; npm run lint; npm run format:check; npm run typecheck; npm run build`
- [ ] 6.3 CI na gałęzi jest zielone (jobs `backend`, `frontend`, `contract`)

#### Manual

- [ ] 6.4 `uv run pytest -m live` przechodzi na pełnej migawce (TRAIN_Q000 z cytatem do `swg21996508`, pytanie kontrolne kończy się abstencją)
- [ ] 6.5 Ślad TRAIN_Q000 w Langfuse Cloud ma etapy, identyfikatory pobranych fragmentów, wersje promptów i czasy
- [ ] 6.6 Zrzuty 1P, 1A i 1C przy 1280 i 1440 px zestawione z kanwą przechodzą listę kontrolną z „Jak weryfikujemy” i są zaakceptowane przez użytkownika
- [ ] 6.7 `docs/przeplyw-danych.md` i notatki w dokumentach fundamentowych odpowiadają decyzjom z planu
