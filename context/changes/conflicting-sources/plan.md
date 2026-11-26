# S-07: Sprzeczne źródła i różne zalecenia (`conflicting-sources`) Implementation Plan

## Overview

Wdrażamy etap **S-07 (`conflicting-sources`)** z roadmapy MVP (`US-03`, `FR-005`, `FR-019`, `FR-014`, ekran 4 `S4.dc.html`, Sprawdzian 2b). Gdy dokumentacja odpowiada na pytanie konsultanta w sposób wykluczający się, asystent nie wybiera po cichu jednej wersji ani nie chowa konfliktu za zwykłą odpowiedzią — prezentuje obie strony (`A vs B`) z dosłownymi, zweryfikowanymi cytatami, identyfikatorami dokumentów, metadanymi (data, wersja produktu, odbiorca, oznaczenie dokumentu syntetycznego), tabelą porównania kontekstu oraz akcjami doprecyzowania, otwarcia dowodów i skopiowania obu wersji ze źródłami. Stan otrzymuje nazwę **„Sprzeczność” (`✕`)** wyłącznie wtedy, gdy oba dokumenty dotyczą tego samego zakresu (produkt, wersja, kontekst); w pozostałych przypadkach jest prezentowany neutralnie jako **„Źródła podają różne zalecenia — Nierozstrzygnięte”**. Całość jest mierzona deterministycznie w Sprawdzianie 2b na 24-przypadkowym zestawie syntetycznym z zapisem eksperymentu w Langfuse Cloud.

## Current State Analysis

- **Binarny graf odpowiedzi i brak porównania między dokumentami:** `build_answer_graph()` (`backend/app/answering/graph.py:56-73`) realizuje łańcuch `retrieve -> draft -> quote_check -> verify -> compose | abstain`, a `AnswerResult = AnsweredResult | AbstainedResult` (`backend/app/answering/schemas.py:95`). Węzeł `verify` (`backend/app/answering/nodes.py:226-237`) ocenia wyłącznie pojedynczą tezę względem jej własnego fragmentu; werdykt `contradicted` oznacza sprzeczność tezy z jej własnym cytatem i jest odrzucany na równi z `insufficient` (`nodes.py:134-145`).
- **Schemat bazy i niezmienność czystej migawki TechQA:** tabela `documents` (`backend/migrations/0001_techqa_schema.sql:15-25`) nie posiada kolumn `is_synthetic`, `doc_date`, `product_version` ani `audience`, a tabela `answers` (`0002_answers.sql:8`) ma ograniczenie `CHECK (outcome IN ('answered', 'abstained', 'failed'))`. Importer TechQA (`backend/app/techqa/importer.py:246-294, 328-339`) wymusza `expected_documents = 28481`, wylicza `state_sha256` po całej migawce `techqa@<rev>` i kasuje ją transakcyjnie przy reimporcie. Z kolei endpoint `GET /api/documents` (`backend/app/api/evidence.py:76-86`) przekazuje na sztywno bazowe `settings.effective_chunk_set_id()`, co uniemożliwiłoby pobranie granic fragmentów dla dokumentu z osobnej migawki.
- **Sprzężenie runnera ewaluacji S-06:** `execute_item()` w `backend/app/evals/runner.py:343-357` zakłada `assert isinstance(result, AnsweredResult)` dla każdego wyniku niebędącego `AbstainedResult`, a `metrics.py:19` dopuszcza wyłącznie `Literal["answered", "abstained", "failed"]`. Dopisanie dokumentów syntetycznych bezpośrednio do domyślnego zestawu `techqa@<rev>/sections-v1` zaburzyłoby też statystyki BM25 i odtwarzalność S-06 (`runner.py:455`).
- **Stan frontendu Asystenta:** `AnswerScreen` (`frontend/app/routes/answer.tsx:78-80, 284-327`), `PreparationDetails.tsx:72-75`, `stages.ts:8-12` oraz `formatAnswerForCopy` (`frontend/app/lib/copy-answer.ts:10-37`) obsługują wyłącznie `answered` i `abstained`. `EvidencePanel.tsx:325` wyświetla na stałe `evidence.unknownDate`. W `app.css:4-32` brakuje tokenów kolorystycznych dla pigułki `✕ Sprzeczność` (zdefiniowanych na kanwie w `design/mockups/canvas/S5.dc.html:26`), a układ z `S4.dc.html:26` wymaga adaptacji responsywnej do `390 px` bez poziomego przewijania.
- **Porównanie z materiałami AI Devs 4 (`01_01_grounding`):** kursowy moduł `01_01_grounding` w TypeScript/Node.js wykonuje ekstrakcję pojęć, wyszukiwanie `web_search` i adnotację tekstu tooltipami HTML — nie posiada weryfikacji wsparcia tez, porównania źródeł ani klasyfikacji zakresu. W naszym stosie (Python, FastAPI, ParadeDB, LangGraph, Langfuse) zachowujemy z niego jedynie zasadę ścisłych schematów strukturalnych (`strict=True`) i dosłownych cytatów, budując dwustronne ugruntowanie (`quote_check` + `verify` dla każdej ze stron) oraz osobny warunkowy krok analizy konfliktu `detect_conflict` z deterministycznym strażnikiem zakresu w Pythonie.

## Desired End State

Po wdrożeniu planu:
1. **Warstwa danych i izolacja:** migracja `0003_synthetic_and_conflicts.sql` rozszerza `documents` o metadane (`is_synthetic`, `doc_date`, `product_version`, `audience`) oraz `answers.outcome` o `'conflicting'`. Idempotentne polecenie `python -m app.cli import-synthetic-conflicts` buduje osobną migawkę `synthetic@v1` i zestaw `synthetic@v1/sections-v1` (z całym zestawem S-07, w tym `SYN-KB-0007`), nie dotykając `importer.py` ani `state_sha256` czystej migawki TechQA. Wyszukiwanie BM25 obsługuje listę zestawów `chunk_set_id = ANY(%(chunk_set_ids)s)` — włączoną domyślnie w demo UI i w `eval-conflicts`, a wyłączoną w `eval-abstention` (S-06).
2. **Graf LangGraph i kontrakt API:** pytania oparte na jednym dokumencie wykonują nadal dokładnie 2 wywołania LLM (`draft`, `verify`) i trafiają do `compose`. Gdy po `quote_check` i `verify` wsparte tezy (`supported`) pochodzą z `>= 2` różnych `doc_id`, graf uruchamia węzeł `detect_conflict`. Jeśli źródła się uzupełniają — przechodzi do `compose` (`AnsweredResult`). Jeśli podają wykluczające się zalecenia — przechodzi do `compose_conflict` i zwraca `ConflictingResult` (`outcome="conflicting"`) dla głównej pary `A vs B` (dwa najwyżej ocenione w rankingu dokumenty ze wspartymi cytatami) wraz z licznikiem `extra_conflicting_docs` dla ewentualnych dalszych źródeł. Deterministyczny strażnik w Pythonie gwarantuje, że dokumenty o różnej wersji produktu lub odbiorcy nigdy nie dostają `conflict_type="contradiction"`.
3. **Ekran 4 (`ConflictView`), `FR-019` i `390 px`:** trasa `/odpowiedz/:id` renderuje widok `A vs B` zgodny z `S4.dc.html` i `S5.dc.html` w obu wariantach stanu (`Źródła podają różne zalecenia` + pigułka `Nierozstrzygnięte` vs `✕ Sprzeczność` przy tym samym zakresie), z tabelą porównania kontekstu, badge'em `DOKUMENT SYNTETYCZNY`, rozwijanym kontekstem kart, akcją `Doprecyzuj…` (przeniesienie pytania ze wskazówką do `Composer`), `Otwórz oba dokumenty` (`EvidencePanel` w `PanelFrame` z przełączaniem `A ↔ B` i prawdziwymi metadanymi daty/wersji) oraz `Skopiuj obie wersje z cytatami` (`formatConflictForCopy`). Widok działa w PL i EN oraz w oknie `390 px` bez przewijania w poziomie.
4. **Sprawdzian 2b (`eval-conflicts`):** zamrożony zbiór `backend/evals/conflicts-dataset.json` (24 przypadki = `8 contradiction` + `8 different_recommendations` + `8 answered` kontrolnych, bez surowych tekstów TechQA w gicie) jest uruchamiany poleceniem `python -m app.cli eval-conflicts`, synchronizowany z datasetem `knowledgeops/conflicts-eval` w Langfuse Cloud i opisany rzeczywistymi wynikami w `context/changes/conflicting-sources/eval-report.md` oraz `docs/przeplyw-danych.md`.

### Key Discoveries:

- `backend/migrations/0001_techqa_schema.sql:50, 60-64` i test `EXPLAIN` na ParadeDB `0.27.0`: warunek `chunk_set_id = ANY(%(chunk_set_ids)s) AND text ||| %(query)s` używa natywnie `TopKScanExecState` na `chunks_search_idx` z `Bitmap Index Scan` po `chunk_set_id` (natomiast operator `===` serializuje listę do tekstu `"{a,b}"` i nie zwraca wyników).
- `backend/app/api/evidence.py:76-86`: `GET /api/documents` przekazuje dziś bazowy `effective_chunk_set_id()`, więc dla `snapshot_id="synthetic@v1"` trzeba rozwiązywać `chunk_set_id` należący do żądanej migawki, aby `DocumentView` (`EvidencePanel.tsx:258`) podświetlał cytowany fragment w pełnym dokumencie syntetycznym.
- `backend/app/evals/runner.py:343-357`: `execute_item()` w S-06 robi `assert isinstance(result, AnsweredResult)` dla każdego wyniku niebędącego `AbstainedResult`; wymaga jawnej gałęzi na `ConflictingResult` oraz wymuszenia czystego zestawu TechQA bez nakładki syntetycznej.
- `design/mockups/canvas/S5.dc.html:26`: kanwa Claude Design definiuje już dokładne kolory i kształt ikony dla pigułki `✕ Sprzeczność` (`background: #fbe9e7`, `color: #a3231a`, kreska ikony `#b3261e`).
- `docs/pilotaz-audytu-techqa.md:89`: dokument `swg21648497` (`TRAIN_Q012`, WAS Linux `nproc = 131072`) jest jedynym plikiem w całym korpusie TechQA pasującym do `131072.*nproc|nproc.*131072`, co czyni go jednoznaczną kotwicą dla `SYN-KB-0007` (`1024`).

## What We're NOT Doing

- Nie modyfikujemy logiki ani transakcyjnego reimportu czystej migawki TechQA w `backend/app/techqa/importer.py` (`expected_documents = 28481` i `state_sha256` pozostają nienaruszone).
- Nie renderujemy dynamicznej tabeli 3+ kolumn (`A vs B vs C`) — zgodnie z decyzją projektową kontrakt prezentuje główną parę `A vs B` (dwa najwyżej ocenione w rankingu wyszukiwania dokumenty ze wspartymi, wykluczającymi się cytatami), a dalsze wykluczające się źródła odnotowuje licznikiem `extra_conflicting_docs` i na liście `checked_chunks`.
- Nie budujemy osobnego podwójnego panelu bocznego renderującego dwa pełne dokumenty jednocześnie — „Otwórz oba dokumenty” reużywa `EvidencePanel` w `PanelFrame` z przełączaniem `A (1/2) ↔ B (2/2)`.
- Nie używamy sędziego LLM w Sprawdzianie 2b — wszystkie wymagane miary (klasyfikacja stanu, macierz pomyłek, obecność cytatów obu stron, inwarianty cytatów, opóźnienie i zużycie tokenów) są w 100% deterministyczne.
- Nie commitujemy surowych tekstów dokumentów ani pytań z korpusu TechQA w `backend/evals/` ani w raportach śledzonych przez git (w gicie leżą wyłącznie nasze autorskie teksty dokumentów syntetycznych, pytania syntetyczne/identyfikatory, etykiety, hashe i zagregowane metryki).
- Nie dodajemy Playwrighta (wchodzi w osobnym kroku `/10x-e2e-setup`), logowania, edycji dokumentacji ani audytu rozwiązanych spraw (`S-08`).

## Implementation Approach

Stosujemy architekturę nakładkową i warunkową:
1. **Izolacja danych przez osobną migawkę `synthetic@v1`:** dokumenty syntetyczne korzystają z tych samych tabel relacyjnych (`snapshots`, `documents`, `chunk_sets`, `chunks`) i tego samego indeksu BM25 ParadeDB (`chunks_search_idx`), ale pod własnym `snapshot_id="synthetic@v1"` i `chunk_set_id="synthetic@v1/sections-v1"`. Dzięki temu `import-techqa` i ewaluacja S-06 pozostają hermetyczne, a warstwa zapytań włącza nakładkę przekazywaniem listy aktywnych `chunk_set_ids` do SQL (`ANY(%(chunk_set_ids)s)`).
2. **Dwuetapowe ugruntowanie przed analizą konfliktu:** zamiast analizować surowe fragmenty po `retrieve` (co uruchamiałoby dodatkowe wywołanie LLM dla niemal każdego pytania z `k=8`), aktualizujemy `draft.md`, by przy rozbieżnych zaleceniach w pobranych fragmentach wyodrębniał osobne tezy z dosłownymi cytatami dla każdej strony. Dopiero gdy po `quote_check` i `verify` istnieją wsparte tezy (`supported`) z co najmniej 2 różnych `doc_id`, graf wchodzi do węzła `detect_conflict`. Takie ustawienie chroni budżet `p95 < 10 s` (zero narzutu dla pytań jednodokumentowych) i gwarantuje, że obie strony `ConflictingResult` mają zweryfikowane, dosłowne cytaty z offsetami `[quote_start, quote_end)`.
3. **Obrona w głąb dla reguły zakresu (`US-03`):** prompt `detect_conflict.md` klasyfikuje zakres jako ten sam wyłącznie wtedy, gdy produkt, wersja i kontekst obu źródeł pokrywają się wprost, a funkcja Pythona `resolve_conflict_type()` dodatkowo wymusza degradację `"contradiction"` → `"different_recommendations"`, gdy metadane dokumentów (`product_version`, `audience`) są jawnie różne lub gdy po jednej stronie zakres wersji jest nieustalony przy zawężonej drugiej stronie.

## Critical Implementation Details

- **ParadeDB `pg_search` 0.27.0 i filtrowanie wielu zestawów:** w zapytaniu BM25 używaj wyłącznie `chunk_set_id = ANY(%(chunk_set_ids)s) AND text ||| %(query)s` z parametrem `list[str]`. Nie używaj operatora `chunk_set_id === %(chunk_set_ids)s` dla listy — `pg_search` traktuje wtedy parametr jako pojedynczy literał tekstowy `"{a,b}"` i zwraca 0 wierszy. Gdy nakładka `synthetic@v1/sections-v1` nie została jeszcze zaimportowana do bazy (np. w istniejących testach integracyjnych S-02), funkcja rozwiązująca aktywne zestawy musi bezpiecznie zwracać sam zestaw bazowy `[effective_chunk_set_id()]`, zamiast zgłaszać błąd `404`/`500`.
- **Spójność `snapshot_id` między stronami A i B:** w `ConflictingResult` strona A może pochodzić z `techqa@0b5bbc8...`, a strona B z `synthetic@v1`. Zarówno `ConflictSide`, jak i `Citation` muszą zawierać własne `snapshot_id` (oraz metadane dokumentu), a `AnswerScreen` musi przekazywać do `EvidenceTarget` `side.snapshot_id` / `citation.snapshot_id` zamiast globalnego `record.snapshot_id`, aby `GET /api/documents` trafiał we właściwą migawkę.
- **Kolejność regeneracji kontraktu i niezmienność migracji:** istniejących plików `0001_techqa_schema.sql` i `0002_answers.sql` nie wolno edytować (runner migracji weryfikuje ich SHA-256). Po każdej zmianie modeli Pydantic w `answering/schemas.py`, `retrieval.py` lub `api/answers.py` należy wyeksportować `backend/openapi.json` przed uruchomieniem `npm run api:types` i `npm run typecheck`.

---

## Faza 1: Schemat `0003`, migawka `synthetic@v1` i wyszukiwanie nakładkowe

### Overview

Dodajemy migrację schematu `0003` z metadanymi dokumentów i rozszerzonym ograniczeniem `CHECK` tabeli `answers`, wdrażamy moduł i idempotentne polecenie CLI `import-synthetic-conflicts` dla migawki `synthetic@v1` (startując z dokumentem `SYN-KB-0007` z ekranu 4) oraz rozszerzamy `retrieval.py` i `/api/evidence` + `/api/documents` o wyszukiwanie nakładkowe `ANY(chunk_set_ids)` i zwracanie metadanych dokumentów.

### Changes Required:

#### 1. Migracja schematu bazy danych

**File**: `backend/migrations/0003_synthetic_and_conflicts.sql`

**Intent**: Rozszerza tabelę `documents` o oznaczenie dokumentu syntetycznego i opcjonalne metadane zakresu (data, wersja produktu, odbiorca) oraz dopuszcza `outcome = 'conflicting'` w tabeli `answers`.

**Contract**: Nowa migracja SQL dodająca do `documents` kolumny `is_synthetic boolean NOT NULL DEFAULT false`, `doc_date text`, `product_version text`, `audience text` oraz zastępująca ograniczenie `answers_outcome_check` na `answers` warunkiem `CHECK (outcome IN ('answered', 'abstained', 'conflicting', 'failed'))`.

#### 2. Moduł i manifest migawki syntetycznej `synthetic@v1`

**File**: `backend/app/synthetic/__init__.py`, `backend/app/synthetic/importer.py`, `backend/app/synthetic/documents.json`

**Intent**: Definiuje wersjonowany w repozytorium katalog autorskich dokumentów syntetycznych (w Fazie 1 co najmniej `SYN-KB-0007` zgodny z `S4.dc.html`, rozbudowany do pełnego zestawu S-07 w Fazie 4) oraz transakcyjny, idempotentny importer zapisujący migawkę `synthetic@v1` i zestaw `synthetic@v1/sections-v1` przy użyciu tego samego `normalize_body()` i `chunk_document(..., ChunkerConfig())` co TechQA.

**Contract**: Stałe `SYNTHETIC_SNAPSHOT_ID = "synthetic@v1"`, funkcja `synthetic_chunk_set_id(config: ChunkerConfig) -> str` (`"synthetic@v1/sections-v1"`), dataclass `SyntheticImportReport(snapshot_id, chunk_set_id, documents, chunks, state_sha256, comparison)` oraz `import_synthetic_snapshot(conn: psycopg.Connection, docs_path: Path, config: ChunkerConfig) -> SyntheticImportReport` używający osobnego klucza blokady doradczej (`pg_advisory_xact_lock`) i kasujący wyłącznie wiersze `snapshot_id = 'synthetic@v1'`.

#### 3. Konfiguracja nakładki i polecenie CLI operatora

**File**: `backend/app/settings.py`, `backend/app/cli.py`

**Intent**: Pozwala włączać/wyłączać nakładkę syntetyczną przez konfigurację (`include_synthetic: bool = True`, `synthetic_chunk_set_id: str | None = None`) i udostępnia operatorowi polecenie `python -m app.cli import-synthetic-conflicts` oraz flagę `--include-synthetic` w `python -m app.cli search`.

**Contract**: W `Settings` pola `include_synthetic: bool = True` oraz metoda `effective_synthetic_chunk_set_id() -> str` zwracająca `"synthetic@v1/sections-v1"` (lub nadpisaną wartość z env); w `cli.py` podkomenda `import-synthetic-conflicts [--file PATH]` wypisująca raport z `state_sha256` i statusem porównania (`pierwszy import` / `identyczny` / `różny`).

#### 4. Wyszukiwanie nakładkowe BM25 i metadane dokumentów w `retrieval.py` i `evidence.py`

**File**: `backend/app/techqa/search.py`, `backend/app/retrieval.py`, `backend/app/api/evidence.py`

**Intent**: Umożliwia przeszukiwanie jednym zapytaniem BM25 zestawu bazowego TechQA razem z `synthetic@v1/sections-v1` (gdy nakładka istnieje w bazie i jest włączona), wzbogaca wyniki wyszukiwania oraz endpointy `/api/evidence` i `/api/documents` o metadane dokumentu i naprawia rozwiązywanie `chunk_set_id` dla dokumentów spoza bazowej migawki.

**Contract**:
- `resolve_active_chunk_set_ids(conn: AsyncConnection, base_chunk_set_id: str, *, include_synthetic: bool, synthetic_chunk_set_id: str) -> list[str]` — sprawdza istnienie `synthetic_chunk_set_id` w `chunk_sets` i zwraca `[base_chunk_set_id, synthetic_chunk_set_id]` albo `[base_chunk_set_id]`.
- `search_bm25(conn, query, *, chunk_set_id: str, extra_chunk_set_ids: Sequence[str] = (), k: int) -> list[RetrievedChunk]` z warunkiem SQL `chunk_set_id = ANY(%(chunk_set_ids)s) AND text ||| %(query)s`.
- `RetrievedChunk`, `EvidenceWindow` i `DocumentText` otrzymują pola: `snapshot_id: str` (w `RetrievedChunk`), `is_synthetic: bool = False`, `doc_date: str | None = None`, `product_version: str | None = None`, `audience: str | None = None`.
- W `GET /api/documents` (`evidence.py`): jeśli `snapshot_id != base_snapshot_id`, przekazuje `chunk_set_id=None` (lub zestaw dopasowany do `snapshot_id`), aby `DocumentText.chunks` zawierało poprawne spany dla dokumentów `synthetic@v1`.

#### 5. Testy warstwy danych i wyszukiwania nakładkowego

**File**: `backend/tests/synthetic/test_importer.py`, `backend/tests/test_retrieval_synthetic.py`, `backend/tests/api/test_evidence.py`

**Intent**: Weryfikuje idempotentność importu `synthetic@v1`, brak wpływu na `import-techqa` (`state_sha256`), działanie `search_bm25` z nakładką i bez niej oraz obecność metadanych i spanów w `/api/evidence` i `/api/documents`.

**Contract**: Testy jednostkowe i bazodanowe (`@pytest.mark.db`) dla powyższych kontraktów.

### Success Criteria:

#### Automated Verification:

- Migracja `0003_synthetic_and_conflicts.sql` wykonuje się czysto i idempotentnie: `cd backend; uv run python -m app.cli migrate`
- Import syntetycznej migawki `synthetic@v1` jest idempotentny (`state_sha256` identyczny w dwóch uruchomieniach) i nie zmienia `state_sha256` czystego `import-techqa`: `cd backend; uv run pytest tests/synthetic/ tests/techqa/test_importer.py`
- Testy wyszukiwania nakładkowego `ANY(chunk_set_ids)` oraz metadanych `/api/evidence` i `/api/documents` (w tym podświetlenia fragmentu dla `snapshot_id="synthetic@v1"`) przechodzą: `cd backend; uv run pytest tests/test_retrieval_synthetic.py tests/api/test_evidence.py`
- Kontrole jakości backendu przechodzą bez błędów: `cd backend; uv run ruff check .; uv run ruff format --check .; uv run python -m mypy .`

**Implementation Note**: Po przejściu wszystkich automatycznych weryfikacji Fazy 1 przejdź do Fazy 2 (Faza 1 nie wprowadza zmian w UI).

---

## Faza 2: Wykrywanie konfliktu w grafie LangGraph i kontrakt API

### Overview

Rozszerzamy graf odpowiedzi LangGraph o dwustronne wyodrębnianie wykluczających się zaleceń w `draft`, warunkowy węzeł `detect_conflict` uruchamiany po `verify` wyłącznie wtedy, gdy wsparte tezy pochodzą z `>= 2` różnych dokumentów, deterministyczny strażnik zakresu (`US-03`), składanie `ConflictingResult` (`A vs B`), aktualizację endpointów `/api/answers` i kompatybilności runnera S-06 oraz synchronizację `openapi.json` i `schema.d.ts`.

### Changes Required:

#### 1. Schematy Pydantic dla wykrywania i wyniku konfliktu

**File**: `backend/app/answering/schemas.py`

**Intent**: Definiuje ustrukturyzowane wyjście modelu dla węzła `detect_conflict`, rozszerza `Citation` o `snapshot_id` i metadane dokumentu oraz dodaje trzeci dyskryminowany wariant `ConflictingResult` do unii `AnswerResult`.

**Contract**: Fazy 3 i 4 zależą od dokładnego kształtu poniższych modeli w OpenAPI:

```python
ConflictType = Literal["contradiction", "different_recommendations"]
ScopeRelation = Literal["same_scope", "different_scope", "unknown_scope"]

class ConflictComparisonOutput(BaseModel):
    value_label: str
    side_a_value: str
    side_b_value: str

class ConflictCheckOutput(BaseModel):
    reasoning: str
    has_conflict: bool
    scope_relation: ScopeRelation | None
    side_a_claim_indices: list[int]
    side_b_claim_indices: list[int]
    conflicting_doc_ids: list[str]
    summary: str | None
    comparison: ConflictComparisonOutput | None
    refine_hint: str | None

class ConflictSide(BaseModel):
    label: Literal["A", "B"]
    snapshot_id: str
    doc_id: str
    chunk_id: str
    title: str
    headings: list[str]
    is_synthetic: bool
    doc_date: str | None
    product_version: str | None
    audience: str | None
    claim_text: str
    code: str | None
    quote: str
    quote_start: int
    quote_end: int

class ConflictComparisonRow(BaseModel):
    kind: Literal["recommendation", "audience", "doc_date", "product_version"]
    label: str | None = None
    side_a: str | None
    side_b: str | None

class ConflictingResult(BaseModel):
    outcome: Literal["conflicting"] = "conflicting"
    conflict_type: ConflictType
    summary: str
    refine_hint: str | None
    comparison_rows: list[ConflictComparisonRow]
    sides: tuple[ConflictSide, ConflictSide]
    extra_conflicting_docs: int = 0
    checked_chunks: list[CheckedChunk]
    omitted_claims: int

AnswerResult = AnsweredResult | AbstainedResult | ConflictingResult
```

`Citation` otrzymuje również pola `snapshot_id: str | None = None` (z fallbackiem odczytu na `record.snapshot_id` dla historycznych odpowiedzi sprzed S-07), `is_synthetic: bool = False`, `doc_date: str | None = None`, `product_version: str | None = None`, aby `EvidencePanel` miał spójne metadane w obu widokach (`1A` i `4`).

#### 2. Prompty `draft.md` i `detect_conflict.md`

**File**: `backend/app/answering/prompts/__init__.py`, `backend/app/answering/prompts/draft.md`, `backend/app/answering/prompts/detect_conflict.md`

**Intent**: W `draft.md` dodajemy regułę zakazującą cichego wybierania jednego źródła, gdy pobrane fragmenty z różnych dokumentów podają wykluczające się wartości lub instrukcje (model tworzy osobne `DraftClaim` dla każdego takiego dokumentu); w nowym `detect_conflict.md` definiujemy ocenę, czy wsparte tezy z różnych `doc_id` są wzajemnie wykluczające się czy komplementarne, oraz ocenę relacji zakresu (`same_scope` wyłącznie gdy produkt, wersja i kontekst zastosowania są jawnie te same).

**Contract**: `PROMPT_NAMES = ("draft", "verify", "detect_conflict")` w `prompts/__init__.py`; wszystkie 3 wersje SHA-256 automatycznie trafiają do `answers.config["prompt_versions"]` i metadanych ewaluacji.

#### 3. Węzły `detect_conflict`, `compose_conflict`, strażnik zakresu i topologia grafu

**File**: `backend/app/answering/nodes.py`, `backend/app/answering/graph.py`

**Intent**: Wzbogaca `retrieve` o opcjonalną nakładkę `synthetic@v1/sections-v1` (sterowaną flagą w `AnswerState`), kieruje przepływ po `verify` do `detect_conflict` wyłącznie dla `>= 2` różnych `doc_id` wśród wspartych tez, wymusza deterministyczną regułę zakresu i składa `ConflictingResult` (wybierając jako `A` i `B` dwa najwyżej ocenione w rankingu wyszukiwania dokumenty ze wspartymi cytatami w konflikcie oraz zliczając dalsze w `extra_conflicting_docs`).

**Contract**:
- `Stage` rozszerzony o `"detect_conflict"` (a składanie konfliktu emituje etap `"compose"` lub wraca do `compose`, dzięki czemu 3 kroki wizualne UI zachowują ciągłość).
- `initial_state(question, settings, *, chunk_set_id=None, include_synthetic=None) -> AnswerState`.
- `_after_verify(state)`: `0` wspartych tez → `"abstain"`; wsparte tezy z `1` unikalnego `doc_id` → `"compose"` (dokładnie 2 wywołania LLM); wsparte tezy z `>= 2` unikalnych `doc_id` → `"detect_conflict"`.
- `resolve_conflict_type(scope_relation, side_a_doc, side_b_doc) -> ConflictType`: czysta funkcja zwracająca `"contradiction"` tylko wtedy, gdy `scope_relation == "same_scope"` **oraz** żaden z jawnych atrybutów `product_version` / `audience` obu dokumentów nie różni się między sobą (ani nie zestawia konkretnej wersji po jednej stronie z inną wersją po drugiej); w każdym innym przypadku zwraca `"different_recommendations"`.
- `_after_detect_conflict(state)`: gdy `has_conflict=True` i wyznaczone indeksy wskazują wsparte tezy z `>= 2` różnych `doc_id` → `"compose_conflict"` (`outcome="conflicting"`); w przeciwnym razie fallback do `"compose"` (`outcome="answered"`).

#### 4. Endpointy `/api/answers`, kompatybilność S-06 i generowanie OpenAPI

**File**: `backend/app/api/answers.py`, `backend/app/evals/runner.py`, `backend/app/evals/metrics.py`, `backend/openapi.json`, `frontend/app/api/schema.d.ts`, `frontend/app/api/answers.ts`

**Intent**: Dopisuje `"detect_conflict"` do `StageEvent.stage` oraz `"conflicting"` do `ResultEvent.outcome` i `AnswerRecord.outcome`, zapisuje w `answers.config` listę przeszukanych `chunk_set_ids`, zabezpiecza runner S-06 przed nakładką syntetyczną i przed `AssertionError` na `ConflictingResult` oraz aktualizuje kontrakt OpenAPI i typy TypeScript.

**Contract**:
- `StageEvent.stage`: dodane `"detect_conflict"`; `ResultEvent.outcome`: `Literal["answered", "abstained", "conflicting"]`; `AnswerRecord.outcome`: `Literal["answered", "abstained", "conflicting", "failed"]`.
- W `evals/runner.py` (S-06): `initial_state(..., include_synthetic=False)` gwarantuje czysty zestaw TechQA w Sprawdzianie 1b/2a, a `execute_item()` obsługuje ewentualny `ConflictingResult` bez `AssertionError` (`ExecutionOutcome` w `metrics.py` rozszerzone o `"conflicting"`).
- W `frontend/app/api/answers.ts`: eksport typów `ConflictingResult`, `ConflictSide`, `ConflictType`, `ConflictComparisonRow`.

#### 5. Testy grafu, strażnika zakresu, API i S-06

**File**: `backend/tests/answering/test_graph.py`, `backend/tests/answering/test_conflict_nodes.py`, `backend/tests/api/test_answers.py`, `backend/tests/evals/test_runner.py`

**Intent**: Pokrywa testami wszystkie ścieżki rozgałęzień po `verify`, niezmienność liczby wywołań modelu (2 wywołania) dla pytań jednodokumentowych, regułę różnych wersji produktu (`US-03`), przypadek `>= 3` sprzecznych dokumentów, strumień SSE + zapis `outcome="conflicting"` w `answers` oraz kompatybilność `eval-abstention`.

**Contract**: Testy jednostkowe i integracyjne (`@pytest.mark.db`) z deterministycznymi modelami testowymi.

### Success Criteria:

#### Automated Verification:

- Testy jednostkowe węzłów i topologii grafu (`detect_conflict` tylko dla `>= 2` `doc_id`, 2 wywołania modelu dla 1 dokumentu, deterministyczny strażnik zakresu dla różnych wersji, obsługa `>= 3` sprzecznych źródeł) przechodzą: `cd backend; uv run pytest tests/answering/`
- Testy API (`POST /api/answers` SSE i `GET /api/answers/{id}` dla `outcome="conflicting"`) oraz kompatybilności runnera S-06 (`include_synthetic=False`, obsługa `ConflictingResult` bez `AssertionError`) przechodzą: `cd backend; uv run pytest tests/api/test_answers.py tests/evals/`
- Kontrakt OpenAPI i wygenerowane typy frontendu są zsynchronizowane i przechodzą kontrolę typów: `cd backend; uv run python scripts/export_openapi.py` oraz `cd frontend; npm run api:types; npm run typecheck`
- Pełny zestaw kontroli i testów backendu przechodzi: `cd backend; uv run ruff check .; uv run ruff format --check .; uv run python -m mypy .; uv run pytest`

**Implementation Note**: Po przejściu wszystkich automatycznych weryfikacji Fazy 2 przejdź do Fazy 3, w której nowy kontrakt `ConflictingResult` zostanie podłączony w interfejsie użytkownika.

---

## Faza 3: Ekran 4 (`ConflictView`), kopiowanie obu wersji i okno `390 px`

### Overview

Budujemy widok ekranu 4 (`ConflictView`) zgodnie z makietami `S4.dc.html` i `S5.dc.html`, obsługując oba stany (`Źródła podają różne zalecenia` / `Nierozstrzygnięte` oraz `✕ Sprzeczność`), tabelę porównania kontekstu, karty `A` i `B` z oznaczeniem `DOKUMENT SYNTETYCZNY`, kopiowanie obu wersji z cytatami (`FR-019`), nawigację `A ↔ B` i metadane daty/wersji w `EvidencePanel`, komplet tłumaczeń PL/EN oraz pełną używalność przy `390 px` bez poziomego przewijania.

### Macierz stanów ekranu 4 (zgodnie z `roadmap.md` §„Jak weryfikujemy”):

- **Ładowanie / postęp (`1P`):** `QuestionBubble` + `ProgressCard` z rzeczywistymi etapami SSE (`retrieve` → `draft`/`quote_check`/`verify`/`detect_conflict` → `compose`).
- **Wynik — różne zalecenia (`Nierozstrzygnięte`, `S4.dc.html`):** badge `A vs B`, nagłówek `Źródła podają różne zalecenia`, neutralna szara pigułka z ikoną i słowem `Nierozstrzygnięte`, podsumowanie po angielsku, tabela porównawcza `A` vs `B`, pasek „Co możesz zrobić” i dwie karty źródeł z cytatami.
- **Wynik — sprzeczność tego samego zakresu (`✕ Sprzeczność`, `S5.dc.html`):** badge `A vs B`, nagłówek `Sprzeczne zalecenia w dokumentacji`, pigułka z ikoną `✕` (`#b3261e`) i słowem `Sprzeczność` na tle `#fbe9e7` (`#a3231a`), podsumowanie, tabela porównawcza, akcje i karty `A` vs `B`.
- **Przypadek `>= 3` sprzecznych źródeł:** widoczna notatka informacyjna nad/pod kartami wskazująca liczbę dodatkowych wykluczających się dokumentów (`extra_conflicting_docs`) dostępnych w sprawdzonych źródłach.
- **Abstencja (`1C`) / Zwykła odpowiedź (`1A`):** istniejące widoki `AbstentionView` i `AnswerView` bez regresji.
- **Błąd (`ErrorState` / `AnswerNotFound`):** istniejący stan błędu z przyciskiem ponowienia (`onRetry`) przy awarii modelu, bazy lub `404` spoza sesji.

### Changes Required:

#### 1. Tokeny kolorystyczne i ikona stanu „Sprzeczność”

**File**: `frontend/app/app.css`, `frontend/app/components/assistant/Icon.tsx`

**Intent**: Dodaje tokeny kanwy Claude Design z `S5.dc.html` dla stanu sprzeczności oraz reużywalną dekoracyjną ikonę `ContradictionIcon` (`✕`), zachowując regułę prezentacji statusu zawsze słowem i ikoną.

**Contract**: W `@theme` w `app.css`: `--color-conflict-bg: #fbe9e7`, `--color-conflict-text: #a3231a`, `--color-conflict-icon: #b3261e`; w `Icon.tsx`: komponent `ContradictionIcon` (`viewBox="0 0 16 16"`, ścieżka `M3.5 3.5l9 9M12.5 3.5l-9 9`).

#### 2. Mapowanie etapu SSE i formatowanie kopiowania obu wersji (`FR-019`)

**File**: `frontend/app/lib/stages.ts`, `frontend/app/lib/stages.test.ts`, `frontend/app/lib/copy-answer.ts`, `frontend/app/lib/copy-answer.test.ts`

**Intent**: Uwzględnia etap `"detect_conflict"` w kroku `"check"` karty postępu oraz dodaje czystą funkcję `formatConflictForCopy` generującą czytelny tekst `text/plain` z obiema instrukcjami (`[A]`, `[B]`), opcjonalnymi blokami kodu, sekcją źródeł zawierającą `doc_id`, tytuł i metadane (syntetyczny/data/wersja) oraz skróconą migawką.

**Contract**:
- `STEP_STAGES.check = ["draft", "quote_check", "verify", "detect_conflict"]` w `stages.ts`.
- `formatConflictForCopy(result: ConflictingResult, recordSnapshotId: string, labels: ConflictCopyLabels): string` w `copy-answer.ts`, zachowująca przy każdej wersji oznaczenie `[A]` / `[B]` i `doc_id` zgodnie z `FR-019` i `US-03`.

#### 3. Komponent `ConflictView` (ekran 4, `1280/1440 px` i `390 px`)

**File**: `frontend/app/components/assistant/ConflictView.tsx`

**Intent**: Odwzorowuje układ ekranu 4 z `S4.dc.html` wraz z wariantem `✕ Sprzeczność` z `S5.dc.html`: nagłówek stanu (zawsze ikona + słowo), wyjaśnienie `summary`, responsywną tabelę porównania kontekstu (`A · <doc_id>` vs `B · <doc_id>`: zalecana wartość, odbiorca, data dokumentu, wersja produktu), pasek akcji „Co możesz zrobić” (`Doprecyzuj…`, `Otwórz oba dokumenty`, `Skopiuj obie wersje z cytatami` z `useCopy` i `role="status"`), dwie karty źródeł `A` i `B` (`TechQA` vs `DOKUMENT SYNTETYCZNY` z tooltipem, dosłowny cytat z `<mark>` i opcjonalnym kodem, rozwijany kontekst z `/api/evidence` lub otwarcie w `EvidencePanel`), ewentualną wzmiankę o `extra_conflicting_docs > 0` oraz `PreparationDetails`.

**Contract**: `ConflictView({ record, result, activeSide, onOpenSide, onOpenBoth, onRefine })`; układ kart `flex-col lg:flex-row` (lub `md:flex-row`, z bezpiecznym przełamaniem przy otwartym panelu bocznym) oraz tabela porównawcza łamiąca wiersze bez `white-space: nowrap` na wąskich ekranach, gwarantująca brak poziomego przewijania przy `390 px`.

#### 4. Integracja w `AnswerScreen`, `EvidencePanel`, `PreparationDetails` i słownikach PL/EN

**File**: `frontend/app/routes/answer.tsx`, `frontend/app/components/assistant/EvidencePanel.tsx`, `frontend/app/components/assistant/PreparationDetails.tsx`, `frontend/app/i18n/pl.ts`, `frontend/app/i18n/en.ts`

**Intent**: Podłącza `ConflictingResult` w `AnswerScreen` (obsługa `activeSide: "A" | "B" | null`, nawigacja `A ↔ B` w `EvidencePanel` przy kliknięciu karty lub `Otwórz oba dokumenty`, fokus i wypełnienie `Composer` z `refine_hint` przy `Doprecyzuj…`, powrót fokusu po `Escape`, przekazywanie właściwego `snapshotId` per cytat/strona), zastępuje sztywne `evidence.unknownDate` w `EvidencePanel` rzeczywistymi metadanymi z API (`doc_date`, `product_version`, badge `DOKUMENT SYNTETYCZNY`), dodaje obsługę `outcome === "conflicting"` w `PreparationDetails` oraz uzupełnia komplet kluczy PL i EN.

**Contract**: Rozszerzenie `EvidenceTarget` o opcjonalne metadane dokumentu (`isSynthetic?: boolean`, `docDate?: string | null`, `productVersion?: string | null`, `sideLabel?: "A" | "B"`) uzupełniane także z odpowiedzi `GET /api/evidence`; pełna zgodność typów `pl.ts` i `en.ts`.

### Success Criteria:

#### Automated Verification:

- Testy jednostkowe `formatConflictForCopy` (oba stany konfliktu, bloki kodu, identyfikatory dokumentów `A`/`B`, metadane syntetyczne i migawka) oraz etapów postępu `deriveSteps` (`detect_conflict`) przechodzą: `cd frontend; npm test`
- Kompletność słowników PL/EN (`Record<TranslationKey, string>`), lint, formatowanie, typecheck i produkcyjny build SPA przechodzą: `cd frontend; npm run lint; npm run format:check; npm run typecheck; npm run build`

#### Manual Verification:

- W przeglądarce przy `1280 px` i `1440 px` pytanie o `nproc` dla WebSphere Application Server na Linuksie wyświetla widok `A vs B` (`swg21648497` vs `SYN-KB-0007`) ze stanem `Źródła podają różne zalecenia` / `Nierozstrzygnięte`, tabelą kontekstu, badge'em `DOKUMENT SYNTETYCZNY` i działającymi akcjami (`Doprecyzuj…`, `Otwórz oba dokumenty` z nawigacją `A ↔ B` i metadanymi daty w `EvidencePanel`, `Skopiuj obie wersje z cytatami`)
- Pytanie testowe o ten sam zakres (produkt, wersja, kontekst) wyświetla stan `✕ Sprzeczność` (ikona + słowo + kolory z `S5.dc.html`), a przełącznik PL/EN tłumaczy cały interfejs bez tłumaczenia dosłownych cytatów
- W oknie o szerokości `390 px` widok konfliktu, tabela porównawcza oraz arkusz od dołu (`PanelFrame` `<dialog>`) dla `Otwórz oba dokumenty` działają z klawiatury (`Tab`, `Escape`) i nie powodują przewijania w poziomie (`scrollWidth <= innerWidth`)

**Implementation Note**: Po przejściu automatycznych weryfikacji Fazy 3 zatrzymaj się na ręczne potwierdzenie widoku ekranu 4 (`1280/1440 px` i `390 px`) przed przejściem do Fazy 4 (lub kontynuuj automatycznie w trybie `/goal`, pozostawiając kroki Manual do końcowej listy kontrolnej).

---

## Faza 4: Zestaw syntetyczny (24 przypadki), Sprawdzian 2b w Langfuse i raport

### Overview

Rozbudowujemy migawkę `synthetic@v1` o komplet dokumentów syntetycznych zakotwiczonych w prawdziwych dokumentach TechQA, tworzymy zamrożony zbiór 24 przypadków Sprawdzianu 2b (`3 × 8`), wdrażamy deterministyczny runner ewaluacyjny `eval-conflicts` z synchronizacją do Langfuse Cloud (`knowledgeops/conflicts-eval`), uruchamiamy pełny eksperyment i zapisujemy rzeczywiste wyniki w `eval-report.md` oraz aktualizujemy `docs/przeplyw-danych.md`.

### Changes Required:

#### 1. Pełny korpus syntetyczny `synthetic@v1` i zamrożony zbiór 24 przypadków

**File**: `backend/app/synthetic/documents.json`, `backend/evals/conflicts-dataset.json`

**Intent**: Dostarcza komplet autorskich dokumentów syntetycznych (w tym warianty o tym samym zakresie — produkt, wersja, kontekst — oraz warianty o różnej wersji produktu, innym odbiorcy lub nieznanej dacie, w tym `SYN-KB-0007`) oraz zamrożony zbiór 24 oznaczonych zapytań w 3 zbalansowanych klasach (`8 contradiction`, `8 different_recommendations`, `8 answered` kontrolnych na pokrewnych tematach bez konfliktu), bez kopiowania surowych tekstów TechQA do plików śledzonych przez git.

**Contract**: `conflicts-dataset.json` zawiera metadane zbioru (`schema_version`, `snapshot_id`, `synthetic_snapshot_id`) i 24 rekordy `ConflictEvalItem(id, question, expected_outcome, expected_conflict_type, anchor_techqa_doc_id, synthetic_doc_id, scope_note)`. Dla przypadków kontrolnych `answered` zestaw mierzy odsetek fałszywych alarmów konfliktu; dla przypadków o różnych wersjach produktu weryfikuje brak etykiety `"contradiction"`.

#### 2. Deterministyczne metryki Sprawdzianu 2b, runner i adapter Langfuse 5.2.0

**File**: `backend/app/evals/conflicts.py`, `backend/app/cli.py`

**Intent**: Wykonuje graf odpowiedzi (z włączoną nakładką `synthetic@v1/sections-v1`) na 24 przypadkach, liczy komplet deterministycznych miar jakości, opóźnienia i zużycia tokenów, synchronizuje dataset `knowledgeops/conflicts-eval` i zapisuje przebieg eksperymentu przez `client._run_experiment_async(...)` w Langfuse 5.2.0 oraz generuje surowy artefakt JSON (w `data/evals/`, poza gitem) i raport Markdown (bez surowych tekstów TechQA).

**Contract**:
- Miary deterministyczne per-item i run-level:
  - 4-klasowa macierz pomyłek dla `("contradiction", "different_recommendations", "answered", "abstained")`,
  - `overall_state_accuracy` (`n=24`),
  - `scope_distinction_accuracy` na parach konfliktowych (`n=16`: poprawne rozróżnienie `contradiction` vs `different_recommendations`) oraz osobny licznik `different_version_misclassified_as_contradiction` (cel: `0`),
  - `false_conflict_rate` na grupie kontrolnej `answered` (`n=8`),
  - `both_sides_cited_rate` oraz `citation_invariants_pass_rate` (sprawdzenie dosłowności `quote` i offsetów `[quote_start, quote_end)` dla obu stron `A` i `B` w `ConflictingResult` oraz dla `AnsweredResult`),
  - `latency_p50_ms`, `latency_p95_ms`, `within_latency_budget_rate` (`< 10 s`) i łączne `TokenUsage`.
- Podkomenda CLI: `python -m app.cli eval-conflicts [--dataset evals/conflicts-dataset.json] [--limit N] [--concurrency 2] [--out-dir ../data/evals] [--report-out PATH] [--no-langfuse] [--yes]` z bramką potwierdzenia kosztu analogiczną do `eval-abstention`.

#### 3. Testy ewaluacji konfliktu i czystości danych w gicie

**File**: `backend/tests/evals/test_conflicts.py`

**Intent**: Sprawdza walidację zbioru `conflicts-dataset.json` (dokładnie `24` rekordy = `3 × 8`, unikalne ID, istnienie powiązanych dokumentów w `documents.json`, brak wycieku surowych tekstów TechQA), wyliczanie macierzy pomyłek, inwariantów cytatów dla obu stron `A` i `B`, obsługę błędów/timeoutów oraz kontrakt wywołania Langfuse `_run_experiment_async`.

**Contract**: Testy jednostkowe i integracyjne pokrywające wszystkie miary deterministyczne i strażnik czystości repozytorium.

#### 4. Raport Sprawdzianu 2b i aktualizacja dokumentacji przepływu danych

**File**: `context/changes/conflicting-sources/eval-report.md`, `docs/przeplyw-danych.md`

**Intent**: Publikuje zmierzone wyniki Sprawdzianu 2b (z liczebnością próby `n`, hashami `config_sha256`, `state_sha256` obu migawek, czasem `p50`/`p95`, zużyciem tokenów, odniesieniem do przebiegu w Langfuse Cloud i jawnym opisem ograniczeń danych syntetycznych) oraz aktualizuje lokalny opis przepływu danych o krok `detect_conflict` i dataset `knowledgeops/conflicts-eval`.

**Contract**: Raport `eval-report.md` bez wymyślonych wartości i bez surowych wycinków dokumentów TechQA; w `docs/przeplyw-danych.md` (plik lokalny ignorowany przez git — nie wymuszać `git add -f`) dopisany wiersz wejścia kroku `detect_conflict` oraz sekcja `eval-conflicts`.

### Success Criteria:

#### Automated Verification:

- Testy walidacji zbioru `backend/evals/conflicts-dataset.json` (`24` przypadki = `3 × 8`, brak surowych tekstów TechQA w plikach śledzonych przez git), deterministycznych metryk Sprawdzianu 2b, macierzy pomyłek i adaptera Langfuse 5.2.0 przechodzą: `cd backend; uv run pytest tests/evals/test_conflicts.py`
- Import pełnej migawki `synthetic@v1` i przebieg `eval-conflicts --yes` kończą się kodem `0` (`n_evaluated=24`, `n_failed=0`, `citation_invariants_pass_rate=1.0`, dokumenty o różnych wersjach nie otrzymują etykiety `contradiction`), zapisując eksperyment w `knowledgeops/conflicts-eval` i generując `context/changes/conflicting-sources/eval-report.md`
- Wszystkie kontrole repozytorium (backend + frontend) przechodzą na czysto: `cd backend; uv run ruff check .; uv run ruff format --check .; uv run python -m mypy .; uv run pytest` oraz `cd frontend; npm run lint; npm run format:check; npm run typecheck; npm test; npm run build`

#### Manual Verification:

- Operator weryfikuje w Langfuse Cloud eksperyment w datasecie `knowledgeops/conflicts-eval` (24 elementy, ślady z węzłem `detect_conflict`, oceny per-item i run-level) oraz zatwierdza raport `context/changes/conflicting-sources/eval-report.md` i zaktualizowany `docs/przeplyw-danych.md`

**Implementation Note**: Po przejściu automatycznych kontroli i wygenerowaniu rzeczywistego raportu z przebiegu Langfuse Cloud przedstaw podsumowanie metryk i link do runu do akceptacji użytkownika.

---

## Testing Strategy

### Unit Tests:

- **Strażnik zakresu (`resolve_conflict_type`):** macierz kombinacji `(scope_relation, product_version_a, product_version_b, audience_a, audience_b)` potwierdzająca, że różne wersje produktu (np. `WAS 8.5` vs `WAS 9.0`) i nieznane wersje nigdy nie dają `"contradiction"`.
- **Składanie `ConflictingResult` i inwarianty cytatów:** weryfikacja deterministycznego wyboru pary `A vs B` według kolejności rankingu wyszukiwania, poprawnego wyliczenia `extra_conflicting_docs` przy `>= 3` sprzecznych źródłach oraz dosłownej zgodności `chunk.text[quote_start:quote_end] == quote` po obu stronach.
- **Kopiowanie i postęp we frontendzie (Vitest):** `formatConflictForCopy` dla obu stanów (`contradiction` i `different_recommendations`), z kodem i bez kodu, oraz `deriveSteps` dla strumienia zawierającego `detect_conflict`.
- **Metryki Sprawdzianu 2b:** macierz pomyłek 4×4, `scope_distinction_accuracy`, `false_conflict_rate` oraz walidator braku surowych tekstów TechQA w `conflicts-dataset.json`.

### Integration Tests:

- **ParadeDB + nakładka `synthetic@v1` (`@pytest.mark.db`):** dwukrotny `import-synthetic-conflicts` daje ten sam `state_sha256`; ponowny `import-techqa` zachowuje identyczny `state_sha256` i nie usuwa `synthetic@v1`; `search_bm25` z nakładką zwraca zarówno `swg21648497`, jak i `SYN-KB-0007`, a bez nakładki zwraca wyłącznie dokumenty TechQA.
- **API `/api/answers`, `/api/evidence`, `/api/documents`:** pełny przebieg SSE dla wyniku `conflicting`, odczyt `GET /api/answers/{id}`, poprawne metadane i spany fragmentów dla dokumentu z `synthetic@v1`.

### Manual Testing Steps:

1. Uruchom migracje i import syntetyczny (`uv run python -m app.cli migrate` oraz `uv run python -m app.cli import-synthetic-conflicts`), a następnie otwórz Asystenta przy szerokości `1440 px` i `1280 px`.
2. Zadaj pytanie z ekranu 4: `A customer runs WebSphere Application Server on Linux and gets a native OutOfMemory "Failed to create a thread". What value should nproc be set to for the WAS user?` — sprawdź stan `Źródła podają różne zalecenia` / `Nierozstrzygnięte`, tabelę kontekstu, badge `DOKUMENT SYNTETYCZNY`, działanie `Otwórz oba dokumenty` (`A ↔ B` w `EvidencePanel`), `Doprecyzuj…` i `Skopiuj obie wersje z cytatami`.
3. Zadaj pytanie z pary o tym samym zakresie (np. jawnie ta sama wersja i kontekst produktu) — sprawdź pigułkę `✕ Sprzeczność` oraz przełączenie języka PL ↔ EN.
4. Przełącz okno przeglądarki na `390 px` — zweryfikuj brak poziomego przewijania tabeli i kart oraz działanie arkusza dowodu z klawiatury (`Tab`, `Escape`).
5. Otwórz link eksperymentu w Langfuse Cloud z wyjścia `eval-conflicts` i potwierdź zgodność liczb w `eval-report.md`.

## Performance Considerations

- **Zero narzutu dla pytań jednodokumentowych:** węzeł `detect_conflict` uruchamia się wyłącznie wtedy, gdy po `verify` wsparte tezy pochodzą z co najmniej 2 różnych `doc_id`. Pytania oparte na jednym dokumencie wykonują nadal 2 wywołania modelu (zmierzony w S-06 baseline na `test`: `p50 = 1670 ms`, `p95 = 2303 ms`).
- **Budżet `p95 < 10 s` dla pytań wielodokumentowych:** pojedyncze dodatkowe wywołanie `detect_conflict` operuje wyłącznie na krótkiej liście już zweryfikowanych tez i metadanych dokumentów (znacznie mniejszy kontekst wejściowy niż `draft` z 8 pełnymi fragmentami), co mieści się z dużym zapasem w budżecie `10 s` i limicie `chat_timeout_s = 12 s` / `answer_deadline_s = 25 s`.
- **Wydajność indeksu ParadeDB:** `chunk_set_id = ANY(%(chunk_set_ids)s)` wykonuje `TopKScanExecState` na istniejącym indeksie `chunks_search_idx` bez pełnego skanu tabeli.

## Migration Notes

- Migracja `0003_synthetic_and_conflicts.sql` jest w pełni wstecznie kompatybilna: nowe kolumny w `documents` mają wartości domyślne (`is_synthetic = false`, pozostałe `NULL`), więc istniejąca migawka TechQA (`28 481` dokumentów) nie wymaga ponownego importu.
- Zapisane wcześniej wiersze w tabeli `answers` (`answered`, `abstained`, `failed`) pozostają w 100% ważne po rozszerzeniu `CHECK` o `'conflicting'` i dodaniu pól z domyślnymi wartościami (`is_synthetic = False`, `doc_date = None`, `product_version = None`) lub migracji odczytu `Citation`. Uwaga kompatybilności odczytu: w `Citation` pole `snapshot_id: str | None = None` (z fallbackiem w UI na `record.snapshot_id`) pozwala bezbłędnie zwalidować historyczne wiersze `answered` zapisane w `answers.result` przed S-07!

## References

- Related research: `context/changes/conflicting-sources/research.md`
- Product requirements & roadmap: `context/foundation/prd.md:116-130, 164-166, 187, 203, 220-231`, `context/foundation/roadmap.md:289-310, 495-535`
- Mockups (Claude Design local copy): `design/mockups/README.md:44-56, 66`, `design/mockups/canvas/S4.dc.html:26`, `design/mockups/canvas/S5.dc.html:26`
- Real TechQA anchor analysis: `docs/pilotaz-audytu-techqa.md:25-28, 54-57, 89`
- Existing answering & eval patterns: `backend/app/answering/graph.py:41-73`, `backend/app/answering/nodes.py:55-339`, `backend/app/evals/runner.py:265-579`, `backend/app/evals/langfuse_eval.py:165-293`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles.

### Phase 1: Schemat `0003`, migawka `synthetic@v1` i wyszukiwanie nakładkowe

#### Automated

- [x] 1.1 Migracja `0003_synthetic_and_conflicts.sql` wykonuje się czysto i idempotentnie: `cd backend; uv run python -m app.cli migrate`
- [x] 1.2 Import syntetycznej migawki `synthetic@v1` jest idempotentny (`state_sha256` identyczny w dwóch uruchomieniach) i nie zmienia `state_sha256` czystego `import-techqa`: `cd backend; uv run pytest tests/synthetic/ tests/techqa/test_importer.py`
- [x] 1.3 Testy wyszukiwania nakładkowego `ANY(chunk_set_ids)` oraz metadanych `/api/evidence` i `/api/documents` (w tym podświetlenia fragmentu dla `snapshot_id="synthetic@v1"`) przechodzą: `cd backend; uv run pytest tests/test_retrieval_synthetic.py tests/api/test_evidence.py`
- [x] 1.4 Kontrole jakości backendu przechodzą bez błędów: `cd backend; uv run ruff check .; uv run ruff format --check .; uv run python -m mypy .`

### Phase 2: Wykrywanie konfliktu w grafie LangGraph i kontrakt API

#### Automated

- [ ] 2.1 Testy jednostkowe węzłów i topologii grafu (`detect_conflict` tylko dla `>= 2` `doc_id`, 2 wywołania modelu dla 1 dokumentu, deterministyczny strażnik zakresu dla różnych wersji, obsługa `>= 3` sprzecznych źródeł) przechodzą: `cd backend; uv run pytest tests/answering/`
- [ ] 2.2 Testy API (`POST /api/answers` SSE i `GET /api/answers/{id}` dla `outcome="conflicting"`) oraz kompatybilności runnera S-06 (`include_synthetic=False`, obsługa `ConflictingResult` bez `AssertionError`) przechodzą: `cd backend; uv run pytest tests/api/test_answers.py tests/evals/`
- [ ] 2.3 Kontrakt OpenAPI i wygenerowane typy frontendu są zsynchronizowane i przechodzą kontrolę typów: `cd backend; uv run python scripts/export_openapi.py` oraz `cd frontend; npm run api:types; npm run typecheck`
- [ ] 2.4 Pełny zestaw kontroli i testów backendu przechodzi: `cd backend; uv run ruff check .; uv run ruff format --check .; uv run python -m mypy .; uv run pytest`

### Phase 3: Ekran 4 (`ConflictView`), kopiowanie obu wersji i okno `390 px`

#### Automated

- [ ] 3.1 Testy jednostkowe `formatConflictForCopy` (oba stany konfliktu, bloki kodu, identyfikatory dokumentów `A`/`B`, metadane syntetyczne i migawka) oraz etapów postępu `deriveSteps` (`detect_conflict`) przechodzą: `cd frontend; npm test`
- [ ] 3.2 Kompletność słowników PL/EN (`Record<TranslationKey, string>`), lint, formatowanie, typecheck i produkcyjny build SPA przechodzą: `cd frontend; npm run lint; npm run format:check; npm run typecheck; npm run build`

#### Manual

- [ ] 3.3 W przeglądarce przy `1280 px` i `1440 px` pytanie o `nproc` dla WebSphere Application Server na Linuksie wyświetla widok `A vs B` (`swg21648497` vs `SYN-KB-0007`) ze stanem `Źródła podają różne zalecenia` / `Nierozstrzygnięte`, tabelą kontekstu, badge'em `DOKUMENT SYNTETYCZNY` i działającymi akcjami (`Doprecyzuj…`, `Otwórz oba dokumenty` z nawigacją `A ↔ B` i metadanymi daty w `EvidencePanel`, `Skopiuj obie wersje z cytatami`)
- [ ] 3.4 Pytanie testowe o ten sam zakres (produkt, wersja, kontekst) wyświetla stan `✕ Sprzeczność` (ikona + słowo + kolory z `S5.dc.html`), a przełącznik PL/EN tłumaczy cały interfejs bez tłumaczenia dosłownych cytatów
- [ ] 3.5 W oknie o szerokości `390 px` widok konfliktu, tabela porównawcza oraz arkusz od dołu (`PanelFrame` `<dialog>`) dla `Otwórz oba dokumenty` działają z klawiatury (`Tab`, `Escape`) i nie powodują przewijania w poziomie (`scrollWidth <= innerWidth`)

### Phase 4: Zestaw syntetyczny (24 przypadki), Sprawdzian 2b w Langfuse i raport

#### Automated

- [ ] 4.1 Testy walidacji zbioru `backend/evals/conflicts-dataset.json` (`24` przypadki = `3 × 8`, brak surowych tekstów TechQA w plikach śledzonych przez git), deterministycznych metryk Sprawdzianu 2b, macierzy pomyłek i adaptera Langfuse 5.2.0 przechodzą: `cd backend; uv run pytest tests/evals/test_conflicts.py`
- [ ] 4.2 Import pełnej migawki `synthetic@v1` i przebieg `eval-conflicts --yes` kończą się kodem `0` (`n_evaluated=24`, `n_failed=0`, `citation_invariants_pass_rate=1.0`, dokumenty o różnych wersjach nie otrzymują etykiety `contradiction`), zapisując eksperyment w `knowledgeops/conflicts-eval` i generując `context/changes/conflicting-sources/eval-report.md`
- [ ] 4.3 Wszystkie kontrole repozytorium (backend + frontend) przechodzą na czysto: `cd backend; uv run ruff check .; uv run ruff format --check .; uv run python -m mypy .; uv run pytest` oraz `cd frontend; npm run lint; npm run format:check; npm run typecheck; npm test; npm run build`

#### Manual

- [ ] 4.4 Operator weryfikuje w Langfuse Cloud eksperyment w datasecie `knowledgeops/conflicts-eval` (24 elementy, ślady z węzłem `detect_conflict`, oceny per-item i run-level) oraz zatwierdza raport `context/changes/conflicting-sources/eval-report.md` i zaktualizowany `docs/przeplyw-danych.md`
