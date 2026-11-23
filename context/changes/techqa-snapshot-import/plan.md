# Import migawki TechQA i indeks BM25 (S-01) — plan implementacji

## Overview

S-01 z roadmapy (`context/foundation/roadmap.md`), FR-012 i NFR Odtwarzalność z PRD. Po zmianie operator uruchamia w kontenerze backendu jedno polecenie CLI. Polecenie importuje niezmienną migawkę NVIDIA TechQA-RAG-Eval z `data/raw/techqa/` do ParadeDB i:

- zapisuje rewizję źródła i hashe plików;
- normalizuje tekst sześcioma regułami wynikającymi z profilu danych;
- deduplikuje dokładne kopie z mapowaniem każdego identyfikatora;
- dzieli dokumenty na fragmenty z pochodzeniem (dokument, kolejność, offsety, wariant chunkera, hash);
- buduje indeks BM25 (pg_search) i wyszukiwanie tekstowe PostgreSQL (tsvector) jako dodatkowy punkt odniesienia.

Ponowny import tej samej migawki daje ten sam hash stanu. Każdy przepływ i każdy sprawdzian (S-02, S-04, S-06, S-08) korzysta z tych fragmentów i identyfikatorów.

## Current State Analysis

- Backend ma tylko `/api/health` (`backend/app/main.py:39-54`), pulę async psycopg (`backend/app/db.py:9-18`) i ustawienia z jednym polem `database_url` (`backend/app/settings.py:4-9`). Nie ma schematu, mechanizmu migracji ani poleceń CLI.
- Rozszerzenia `vector` i `pg_search` tworzy `db/init/01-extensions.sql`. Działa tylko na pustym wolumenie (README, uwaga z przeglądu F-01, F8). CI wykonuje ten plik przez `psql` (`.github/workflows/ci.yml`, krok „Rozszerzenia bazy”).
- Kontener backendu nie widzi `data/`. Obraz kopiuje tylko `app/` (`backend/Dockerfile:12`) i działa jako uid 10001.
- Dane leżą w `data/raw/techqa/`: `corpus.zip`, rozpakowany `corpus/`, `train.json`, `README.md` i `revision.txt`. Katalog jest poza Gitem (`.gitignore: /data/`), a `docs/` też (`.gitignore: /docs/`). CI nie ma dostępu do danych.
- Testy bazodanowe są oznaczone `@pytest.mark.db` i pomijane bez `DATABASE_URL` (`backend/tests/test_database.py:6-9`). Użytkownik bazy w Compose i CI jest superużytkownikiem, więc testy mogą tworzyć tymczasowe bazy.

### Key Discoveries

**Profil danych** (sprawdzony ponownie 2026-11-23, zgodny z `docs/raport-techqa.md`)
- Hashe `README.md`, `train.json` i `corpus.zip` oraz rewizja `0b5bbc84b7f07d6d09d063130e90b716d8d4a32a` są zgodne z raportem.
- `corpus.zip` ma 28 481 plików `.txt` i jeden wpis katalogu `corpus/`, bez zagnieżdżeń.
- Każdy dokument ma kopertę: `Title: IBM <tytuł> - United States`, pusta linia, `Text:`, potem treść. W 133 dokumentach tytuł zajmuje kilka linii, dlatego dzielimy po pierwszym `\n\nText:\n`.
- Nagłówki sekcji są wielkimi literami. Wyrażenie `^(?=[^a-z]*[A-Z]{3})[A-Z0-9][A-Z0-9 ()/&,\-:'.]{2,79}$` (na linii po `strip`, poprzedzonej pustą linią albo na początku treści) trafia w 28 332 z 28 481 dokumentów; mediana to 6 nagłówków, p90 to 11. Najczęstsze: PROBLEM(ABSTRACT), CAUSE, RESOLVING THE PROBLEM oraz szablon APAR. Nagłówki pisane zwykłą wielkością liter (np. „Problem Description” w `swg21996508`) nie są wykrywane.
- Rozmiary w znakach: mediana 3 182, p90 6 696, p99 9 643, maks. 178 392 (`swg27048240`). Ponad 8 000 znaków ma 1 364 dokumenty.
- Szum:
  - puste punktory: 27 077 linii w 2 165 dokumentach; w `swg21675316` to 67 z 99 linii;
  - ciągi co najmniej trzech pustych linii: 119 808 w 21 413 dokumentach;
  - białe znaki na końcu linii: 869 tys. linii;
  - encje HTML w 1 607 dokumentach (`&amp;` 4 968, `&#160;` 216, `&gt;`, `&lt;`, `&apos;`, `&#13;`). Jeden dokument (`swg1HE12470`) ma podwójnie zakodowane `&amp;#27` bez końcowego średnika. W 13 dokumentach są ciągi podobne do encji bez średnika, będące częścią URL-i i kodu (`&param_providerVersion=` w `swg1IV78320`, `"&amp"` w `swg1IV47904`); `html.unescape` zamieniłoby `&para` na `¶`. Encji zagnieżdżonych ze średnikiem (np. `&amp;lt;`) w korpusie nie ma;
  - NBSP: 822 wystąpienia w 100 dokumentach;
  - jeden luźny CR w `swg1PI91734`.
  
  Wszędzie są końce linii LF i nie ma BOM.
- Dokładne duplikaty (SHA-256 surowych bajtów) tworzą dwie grupy: `ssg1S1010476`, `ssg1S1010477`, `ssg1S1010478` oraz `swg21448977`, `swg21454120`. Daje to 3 nadmiarowe kopie. Żaden rekord `train.json` nie odwołuje się do nich.
- `train.json` ma 910 rekordów z kluczami `id`, `question`, `answer`, `is_impossible`, `contexts`. 610 rekordów ma jeden kontekst `{filename: "swg….txt", text}`, a `text` jest bajt w bajt taki sam jak plik w korpusie. Odwołania wskazują 496 różnych dokumentów.
- 176 dokumentów jest w co najmniej 5% po japońsku lub w innym piśmie CJK. Żaden z nich nie występuje w `train.json`.

**pg_search 0.27** (dokumentacja z tagu `v0.27.0`)
- Metoda dostępu nazywa się `paradedb`, a `bm25` to alias. `key_field` jest ignorowane.
- Na tabelę może być tylko jeden indeks ParadeDB. Indeks jest pokrywający, więc zmiana listy kolumn wymaga `REINDEX`.
- Tokenizer ustawia się rzutowaniem pola, np. `text::pdb.simple('stemmer=english')`. Zapytania: `|||` (dowolny token), `&&&` (wszystkie tokeny), ranking przez `pdb.score(id)`. Dla optymalizacji Top-K kolumna rozstrzygająca remisy musi być w indeksie.
- Zapisy są transakcyjne, a indeks aktualizuje się przy INSERT, UPDATE i DELETE. Każda instrukcja zapisu potrzebuje co najmniej 15 MB `work_mem`.
- Niepotwierdzone: czy `stemmer` i `stopwords_language` działają razem w jednym rzutowaniu. Sprawdza to faza 1.

**Wzorce AI Devs 4**
- `02_02_chunking/src/strategies/separators.js:8-58`: rekurencyjne separatory `["\n## ", "\n### ", "\n\n", "\n", ". ", " "]`, 1 000 znaków i nakładanie 200. Bierzemy zasadę rekurencji i łączenia do limitu.
  - Zmieniamy:
    - nagłówki markdown zastępujemy nagłówkami TechQA;
    - rezygnujemy z `". "`, bo psuje numery wersji;
    - zapisujemy offsety; kurs ich nie ma i szuka fragmentu przez `indexOf` (`src/utils.js:46-62`).
- `02_02_hybrid_rag/src/db/indexer.js:46-60`: hash treści i usuwanie danych dokumentu przed ponownym zapisem, bez transakcji. My przebudowujemy całość w jednej transakcji.

## Desired End State

- `docker compose run --rm backend python -m app.cli migrate` zakłada schemat. Drugie uruchomienie nic nie zmienia.
- `docker compose run --rm backend python -m app.cli import-techqa`:
  - sprawdza manifest migawki, czyta `corpus.zip`, normalizuje, deduplikuje i dzieli dokumenty;
  - zapisuje wszystko w jednej transakcji i wypisuje raport: liczby, grupy duplikatów, kontrolę `train.json` i hash stanu z porównaniem do poprzedniego importu.
- W bazie są:
  - 28 481 dokumentów, w tym 28 478 kanonicznych i 3 zmapowane na kopię kanoniczną;
  - fragmenty wariantu `sections-v1` tylko dla dokumentów kanonicznych;
  - indeks BM25 i kolumna `tsvector` z indeksem GIN.
- Dwa kolejne importy dają ten sam hash stanu.
- `python -m app.cli search "<zapytanie>" --method bm25|fts` zwraca ranking fragmentów. Zapytanie z pytania `TRAIN_Q000` zwraca `swg21996508` w pierwszej dziesiątce wyników BM25.
- CI uruchamia migracje i testy na syntetycznej mini-migawce.

## What We're NOT Doing

- Importu pytań z `train.json` do bazy, podziału na zbiory, wykrywania przecieku TRAIN/DEV i konfliktów etykiet. To S-04 i S-06. Tu `train.json` jest tylko hashowany i sprawdzamy, że każde odwołanie wskazuje istniejący dokument.
- Indeksu wektorowego i embeddingów (S-04).
- Porównania metod wyszukiwania, Recall@k i hybrydy RRF (S-04). Polecenie `search` służy wyłącznie do kontroli przez operatora. FTS używa `websearch_to_tsquery`, które łączy słowa przez AND; uczciwe porównanie z BM25 ustala S-04.
- Eksperymentów z chunkingiem i strategii opartych na LLM (S-12).
- Deduplikacji po tekście znormalizowanym i wykrywania podobnych dokumentów. Duplikat to identyczny SHA-256 surowego pliku.
- Usuwania powtórzonych bloków kodu (`swg21675316`, `TRAIN_Q001`) i jakiejkolwiek normalizacji poza sześcioma regułami z fazy 2.
- Wykrywania języka i specjalnej obsługi dokumentów po japońsku. Importujemy je razem z resztą i tokenizujemy tak samo.
- Metadanych spoza koperty (typ dokumentu z linii słów kluczowych, URL dokumentu).
- Obsługi wielu wersji dokumentów i przyrostowych aktualizacji. Jest jedna niezmienna migawka.
- Endpointów HTTP i zmian w `openapi.json`. Import działa tylko przez CLI.
- Downgrade migracji. Wycofanie zmiany schematu to nowa migracja.
- Nowych zależności. Używamy `argparse`, `zipfile`, `html` i `hashlib` z biblioteki standardowej oraz synchronicznego psycopg 3, który już jest w zależnościach.

## Implementation Approach

Od dołu do góry: schemat → czyste funkcje tekstu → import → kontrola wyszukiwania na pełnym korpusie.

- **Migracje:** własny runner z numerowanymi plikami `backend/migrations/NNNN_<nazwa>.sql` i tabelą `schema_migrations` (wersja, SHA-256 pliku, czas). Każdy plik wykonuje się w osobnej transakcji, pod blokadą doradczą. Runner odmawia działania, gdy zmieniła się treść już zastosowanego pliku.
- **Źródło prawdy:** import czyta `corpus.zip`, a nie rozpakowany katalog, bo zip jest objęty sprawdzonym hashem. Oczekiwane hashe, rewizja i liczba dokumentów leżą w commitowanym manifeście, bo `docs/` jest poza Gitem.
- **Deterministyczne identyfikatory:**
  - migawka: `techqa@<rewizja>`;
  - zestaw fragmentów: `<migawka>/sections-v1`;
  - fragment: `<zestaw>/<doc_id>/<ordinal>`.
- **Hash stanu** liczony jest z bazy po zapisie, z posortowanych wierszy, bez znaczników czasu. Dzięki temu dowodzi tego, co faktycznie jest w bazie, a nie tego, co policzył Python.
- **Testy:** czyste funkcje mają testy jednostkowe. Integracja działa w tymczasowej bazie tworzonej przez fixture, na syntetycznej mini-migawce budowanej w `tmp_path`, więc w repo nie ma binarnego zipa. Test na pełnym korpusie jest oznaczony `corpus` i pomijany, gdy brak danych.

## Critical Implementation Details

- **Jeden indeks ParadeDB na tabelę.** Indeks na `chunks` obejmuje `id`, `chunk_set_id` i `text`. Późniejszy wariant chunkera (S-12) korzysta z tego samego indeksu, filtrując po `chunk_set_id`. Dodanie kolumny do indeksu wymaga nowej migracji z `REINDEX`.
- **Offsety odnoszą się do znormalizowanej treści**, czyli `documents.text`: części po `Text:\n` po normalizacji. Niezmiennik `documents.text[start:end] == chunks.text` musi zachodzić dla każdego fragmentu. Surowy plik zostaje w `documents.raw_text`. Offsety są w znakach Pythona (punkty kodowe), tak samo jak `substring` w PostgreSQL dla UTF-8.
- **Kolejność w transakcji importu** (rodzic zawsze przed dzieckiem; klucze obce nie są `DEFERRABLE`):
  1. odczyt poprzedniego `chunk_sets.state_sha256` dla tego zestawu (brak wiersza oznacza pierwszy import);
  2. `SET LOCAL work_mem = '64MB'`;
  3. usunięcie poprzedniego stanu w kolejności zależności: `chunks` zestawu → `chunk_sets` → `documents` migawki → `snapshots`. Usuwanie jest jawne, kaskada w FK służy tylko ręcznemu wycofaniu;
  4. zapis migawki;
  5. `COPY` dokumentów;
  6. zapis zestawu z `variant`, `config` i `config_sha256`, z `chunk_count` i `state_sha256` równymi NULL;
  7. `COPY` fragmentów;
  8. hash stanu z bazy;
  9. `UPDATE` zestawu: `chunk_count`, `state_sha256`, `built_at`;
  10. commit.
  
  Każdy zapis spełnia klucze obce w chwili wykonania. Wartości NULL w kroku 6 są widoczne tylko wewnątrz transakcji. Błąd na dowolnym etapie wycofuje całość i poprzedni stan zostaje nietknięty.
- **Uprawnienia montowania.** Kontener działa jako uid 10001. Montowanie `./data/raw/techqa:/data/raw/techqa:ro` musi być czytelne dla tego użytkownika; Docker Desktop na Windows udostępnia pliki do odczytu wszystkim. Faza 1 sprawdza to poleceniem w kontenerze.

## Phase 1: Schemat i runner migracji

### Overview

Polecenie `migrate`, pierwsza migracja ze schematem migawki, dokumentów i fragmentów, oba indeksy wyszukiwania, montowanie danych w kontenerze i krok migracji w CI.

### Changes Required

#### 1. Runner migracji

**File**: `backend/app/migrations.py`

**Intent**: Stosuje brakujące pliki SQL po kolei i zapisuje, które zastosowano, żeby schemat dało się rozwijać bez usuwania wolumenu.

**Contract**:
- `apply_migrations(conn: psycopg.Connection, directory: Path) -> list[str]` zwraca wersje zastosowane w tym uruchomieniu.
- Tworzy `schema_migrations(version text PRIMARY KEY, sha256 text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())`, jeśli tabeli nie ma.
- Bierze `pg_advisory_lock` na czas działania.
- Pliki sortuje po nazwie `NNNN_*.sql`. Każdy wykonuje w osobnej transakcji razem z wpisem do `schema_migrations`.
- Zgłasza błąd, gdy SHA-256 zastosowanego pliku różni się od zapisanego albo gdy zapisana wersja nie ma pliku.

#### 2. Pierwsza migracja

**File**: `backend/migrations/0001_techqa_schema.sql`

**Intent**: Zakłada tabele migawki, dokumentów, zestawów fragmentów i fragmentów oraz indeksy BM25 i tsvector. Tworzy też rozszerzenia (`IF NOT EXISTS`), żeby schemat powstawał na bazie, na której nie działał `db/init`.

**Contract**:
- `snapshots`: `id text PK` (`techqa@<rewizja>`), `source text`, `revision text`, `manifest jsonb` (nazwa pliku → SHA-256), `imported_at timestamptz`.
- Wszystkie klucze obce mają `ON DELETE CASCADE` (ręczne wycofanie migawki jednym `DELETE`) i nie są `DEFERRABLE`.
- `documents`: PK `(snapshot_id, doc_id)`, FK do `snapshots`.
  - `doc_id` to nazwa pliku bez `.txt`.
  - `canonical_doc_id text NOT NULL`: równa `doc_id` dla dokumentu kanonicznego.
  - Treść: `title text`, `raw_text text`, `raw_sha256 text`, `text text` (znormalizowana treść), `text_sha256 text`.
- `chunk_sets`: `id text PK`, `snapshot_id` FK, `variant text NOT NULL`, `config jsonb NOT NULL`, `config_sha256 text NOT NULL`, `chunk_count int` (NULL do końca importu), `state_sha256 text` (NULL do końca importu), `built_at timestamptz`.
- `chunks`:
  - klucze: `id text PK`, `chunk_set_id` FK, `snapshot_id`, `doc_id`, FK `(snapshot_id, doc_id)` do `documents`;
  - pochodzenie: `ordinal int`, `headings text[]`, `start_offset int`, `end_offset int`, `text text`, `text_sha256 text`;
  - kolumna `tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED`;
  - `UNIQUE (chunk_set_id, doc_id, ordinal)`;
  - `CHECK (start_offset >= 0 AND end_offset > start_offset)`.
- Indeksy: GIN na `chunks.tsv`; `CREATE INDEX chunks_search_idx ON chunks USING paradedb (id, chunk_set_id, (text::pdb.simple('stemmer=english', 'stopwords_language=english')))`.
  - Jeśli test tokenizera pokaże, że obu opcji nie da się połączyć, zostaje sam `stemmer=english`, a decyzja trafia do komentarza w migracji.

#### 3. Polecenia CLI

**File**: `backend/app/cli.py`

**Intent**: Jeden punkt wejścia dla poleceń operatora. W tej fazie tylko `migrate`.

**Contract**:
- `python -m app.cli <polecenie>` przez `argparse`.
- `migrate` łączy się synchronicznym `psycopg.connect(Settings().database_url)`, stosuje migracje z katalogu `migrations/` obok pakietu `app` i wypisuje zastosowane wersje albo „Schemat aktualny”.
- Kod wyjścia 0 przy sukcesie, 1 przy błędzie, z komunikatem po polsku.

#### 4. Ustawienia i kontener

**Files**: `backend/app/settings.py`, `backend/Dockerfile`, `docker-compose.yml`, `.env.example`

**Intent**: Kontener ma migracje i widzi dane tylko do odczytu, a ścieżkę do danych da się nadpisać przy uruchomieniu na hoście.

**Contract**:
- `Settings.techqa_dir: Path = Path("/data/raw/techqa")` (zmienna `TECHQA_DIR`).
- `COPY migrations ./migrations` w Dockerfile.
- W usłudze `backend` wolumen `./data/raw/techqa:/data/raw/techqa:ro`.
- W `.env.example` zakomentowany `TECHQA_DIR=./data/raw/techqa` dla uruchomień z hosta.

#### 5. CI

**File**: `.github/workflows/ci.yml`

**Intent**: CI sprawdza, że migracje stosują się na czystej bazie.

**Contract**: W jobie `backend`, przed `uv run pytest`, krok `uv run python -m app.cli migrate`. Krok `psql` z `db/init` zostaje.

#### 6. Testy

**Files**: `backend/tests/conftest.py`, `backend/tests/test_migrations.py`, `backend/pyproject.toml`

**Intent**: Testy bazodanowe działają w tymczasowej bazie, więc nie mieszają danych z lokalną bazą deweloperską.

**Contract**:
- Fixture `temp_database` tworzy bazę `kops_test_<losowy sufiks>` przez połączenie z `DATABASE_URL` (autocommit), zwraca jej URL i usuwa ją po teście (`DROP DATABASE … WITH (FORCE)`).
- Testy:
  - pierwsze `apply_migrations` stosuje `0001`, a drugie zwraca pustą listę;
  - zmieniona treść zastosowanego pliku (kopia katalogu w `tmp_path`) daje błąd;
  - po migracji istnieją tabele, indeks `chunks_search_idx` i indeks GIN;
  - `SELECT 'Running the servers'::pdb.simple('stemmer=english','stopwords_language=english')::text[]` zwraca rdzenie słów bez stopwords.
- Nowy marker `corpus` w `pyproject.toml` (używany od fazy 2).

### Success Criteria

#### Automated Verification

- ruff check, ruff format --check i mypy przechodzą: `cd backend; uv run ruff check .; uv run ruff format --check .; uv run mypy .`
- Testy migracji przechodzą z `DATABASE_URL`: `cd backend; uv run python -m pytest tests/test_migrations.py`
- `docker compose run --rm backend python -m app.cli migrate` kończy się kodem 0 dwa razy z rzędu, a drugie uruchomienie wypisuje „Schemat aktualny”
- Kontener widzi dane: `docker compose run --rm backend ls -l /data/raw/techqa/corpus.zip`
- CI jest zielone z krokiem `migrate`

#### Manual Verification

- Użytkownik akceptuje nazwy tabel i kolumn w `0001_techqa_schema.sql`

---

## Phase 2: Parsowanie, normalizacja i chunking

### Overview

Czyste, deterministyczne funkcje bez bazy: koperta dokumentu, sześć reguł normalizacji, wykrywanie nagłówków i chunker `sections-v1` z offsetami. Funkcje są w pełni pokryte testami jednostkowymi.

### Changes Required

#### 1. Koperta dokumentu

**File**: `backend/app/techqa/parse.py`

**Intent**: Wydziela tytuł i treść z pliku TechQA.

**Contract**:
- `parse_document(raw: str) -> ParsedDocument(title: str, body: str)`.
- Dzieli po pierwszym `\n\nText:\n`. Tytuł to tekst po `Title: `, z liniami połączonymi spacją i usuniętym końcowym ` - United States`.
- Brak koperty daje `ValueError` z opisem.

#### 2. Normalizacja

**File**: `backend/app/techqa/normalize.py`

**Intent**: Usuwa tylko szum zaobserwowany w profilu i zachowuje kod, listy, linki `tekst [http://…]` i powtórzenia.

**Contract**: `normalize_body(body: str) -> str` oraz stała `NORMALIZER_VERSION = "norm-v1"`. Reguły w tej kolejności:
1. jednoprzebiegowe dekodowanie encji HTML zakończonych średnikiem: `&nazwa;`, jeśli `nazwa;` jest kluczem w `html.entities.html5`, oraz `&#NNN;` i `&#xHH;` (zamiana jak w `html.unescape`). Ciągi bez średnika (`&param_…`, `&amp"`, `&#27`) i nieznane nazwy zostają bez zmian. Dekodowany jest jeden poziom: `&amp;lt;` daje `&lt;`. Nie używamy `html.unescape` na całym tekście, bo dekoduje też encje bez średnika;
2. usunięcie znaków CR;
3. NBSP (U+00A0) na spację;
4. usunięcie białych znaków na końcu każdej linii;
5. usunięcie linii, które po `strip` są jednym znakiem z zestawu `* • - o · +`;
6. ciągi trzech i więcej pustych linii zamienione na jedną pustą linię oraz usunięte puste linie na początku i końcu.

Idempotencja: `normalize_body(normalize_body(x)) == normalize_body(x)` zachodzi dla każdego tekstu bez encji zagnieżdżonych ze średnikiem, w tym dla całego korpusu. Dla `&amp;lt;` drugi przebieg zdekodowałby kolejny poziom. To świadoma granica: importer stosuje normalizację raz do surowego tekstu, a test korpusu wykryje taką encję w przyszłej migawce.

#### 3. Chunker `sections-v1`

**File**: `backend/app/techqa/chunking.py`

**Intent**: Dzieli znormalizowaną treść na fragmenty do 1 500 znaków wzdłuż sekcji TechQA i zapisuje dokładne offsety.

**Contract**:
- `chunk_document(text: str, config: ChunkerConfig) -> list[Chunk(ordinal, headings, start, end, text)]`.
- `ChunkerConfig`: `variant="sections-v1"`, `max_chars=1500`, `overlap_chars=150`, `heading_pattern` (wyrażenie z Key Discoveries), `normalizer=NORMALIZER_VERSION`.
- Metoda `config_sha256()` liczy SHA-256 kanonicznego JSON (`sort_keys`, bez spacji).

Reguły:
- **Sekcje.** Sekcja zaczyna się od linii nagłówka: dopasowanie wyrażenia, linia na początku treści albo po pustej linii. Tekst przed pierwszym nagłówkiem to sekcja bez nagłówka.
- **Łączenie.** Kolejne sekcje łączą się zachłannie, dopóki rozpiętość od początku pierwszej do końca ostatniej nie przekroczy `max_chars`. `headings` to lista nagłówków połączonych sekcji.
- **Dzielenie dużych sekcji.** Sekcja dłuższa niż `max_chars` dzieli się rekurencyjnie po `\n\n`, potem po `\n`, a w ostateczności twardym cięciem. Twarde cięcie cofa się do ostatniego białego znaku w limicie; w środku tokenu tnie tylko wtedy, gdy w limicie nie ma białego znaku. Dzięki temu numer wersji (`8.5.5.1`) ani identyfikator nie są rozcinane. Części łączą się zachłannie do limitu.
- **Nakładanie.** Każdy kolejny fragment dzielonej sekcji zaczyna się do `overlap_chars` przed końcem poprzedniego, przesunięty w przód do najbliższego białego znaku. Długość z nakładaniem nadal mieści się w `max_chars`.
- **Granice.** Fragment nie zaczyna się ani nie kończy białym znakiem; offsety są po przycięciu.

Niezmienniki:
- `text[start:end] == chunk.text`;
- `len(chunk.text) <= max_chars`;
- `ordinal` rośnie od 0;
- fragmenty pokrywają każdy niebiały znak treści;
- ten sam wejściowy tekst daje identyczny wynik.

#### 4. Podgląd dla operatora

**File**: `backend/app/techqa/chunking.py` (blok `__main__`)

**Intent**: Pozwala obejrzeć fragmenty jednego pliku bez bazy, do przeglądu ręcznego.

**Contract**: `python -m app.techqa.chunking <ścieżka.txt>` wypisuje tytuł i dla każdego fragmentu: ordinal, nagłówki, offsety, długość i treść.

#### 5. Testy

**Files**: `backend/tests/techqa/test_parse.py`, `test_normalize.py`, `test_chunking.py`, `test_corpus.py`, `backend/tests/fixtures/techqa/*.txt`

**Intent**: Dowodzi reguł i niezmienników na syntetycznych dokumentach w kształcie TechQA, a lokalnie także na całym korpusie.

**Contract**:
- Fikstury to 8–10 syntetycznych plików pisanych przez nas, nie kopii z korpusu:
  - wieloliniowy tytuł;
  - szablon APAR z krótkimi sekcjami;
  - sekcja dłuższa niż 4 000 znaków;
  - puste punktory i powtórzony kod;
  - encje i NBSP;
  - encje zagnieżdżone i ciągi bez średnika: `&amp;lt;`, `&amp;#27`, `&amp;amp;`, URL z `&param=1&amp=2`;
  - brak nagłówków;
  - linia dłuższa niż 1 500 znaków z numerami wersji (`8.5.5.1`, `V9.0.0.7`) bez białych znaków w pobliżu limitu;
  - blok kodu lub logu dłuższy niż 1 500 znaków bez pustych linii;
  - nietypowe nagłówki: numer części wielkimi literami (`CI62KML`), linia logu wielkimi literami i nagłówek zwykłą wielkością liter (`Problem Description:`).
- Testy normalizacji encji:
  - `&amp;lt;` daje `&lt;` (jeden poziom), a `&amp;amp;` daje `&amp;`;
  - `&amp;#27` daje `&#27`, a drugi przebieg go nie zmienia;
  - `&param=1&amp=2` i `"&amp"` zostają bez zmian;
  - idempotencja na fiksturach bez encji zagnieżdżonych ze średnikiem;
  - test, który pokazuje granicę: dla `&amp;lt;` drugi przebieg daje `<`.
- Testy chunkera dla nowych fikstur:
  - każdy numer wersji z fikstury występuje w całości w co najmniej jednym fragmencie;
  - blok kodu dzieli się po `\n`, a nie twardym cięciem;
  - numer części i linia logu są wykrywane jako nagłówki zgodnie z wyrażeniem, a `Problem Description:` nie jest. Test utrwala zachowanie `sections-v1`; jego ocenę zostawiamy S-04.
- `test_corpus.py` z markerem `corpus` jest pomijany, gdy nie istnieje `Settings().techqa_dir / "corpus.zip"`. Dla wszystkich 28 481 dokumentów sprawdza parsowanie, ścisłą idempotencję normalizacji i niezmienniki chunkera oraz wypisuje łączną liczbę fragmentów i liczbę dokumentów z niezdekodowanymi ciągami `&…` bez średnika.

### Success Criteria

#### Automated Verification

- ruff check, ruff format --check i mypy przechodzą
- Testy jednostkowe przechodzą: `cd backend; uv run python -m pytest tests/techqa -m "not corpus"`
- Niezmienniki na pełnym korpusie przechodzą lokalnie: `cd backend; $env:TECHQA_DIR="../data/raw/techqa"; uv run python -m pytest tests/techqa/test_corpus.py -m corpus`

#### Manual Verification

- Przegląd fragmentów sześciu dokumentów kontrolnych przez `python -m app.techqa.chunking`:
  - `swg21675316`: szum punktorów usunięty, powtórzony kod zachowany;
  - `swg21996508`: sekcje i nagłówki; `Problem Description` nie jest nagłówkiem, więc sekcja łączy się z poprzednią;
  - `swg21681142`: długi blok kodu i logów (129 linii bez pustej linii) dzielony po liniach, a nakładanie zaczyna się od pełnej linii;
  - `swg27038676`: 235 numerów wersji, żaden nie jest rozcięty na granicy fragmentu;
  - `swg24033234`: numery części (`CI62KML`) wykryte jako nagłówki; sprawdzić, czy lista `headings` nie zaciemnia pochodzenia;
  - `swg1IT14613`: linia logu `APPHDL  : 0-270 APPID:` wykryta jako nagłówek.
  
  Wynik przeglądu to notatka w `change.md`. Fałszywe nagłówki nie blokują fazy, bo wpływ na jakość wyszukiwania ocenia S-04.

---

## Phase 3: Polecenie importu

### Overview

`import-techqa`: weryfikacja manifestu, odczyt zipa, deduplikacja z mapowaniem, kontrola `train.json`, zapis w jednej transakcji, hash stanu i raport.

### Changes Required

#### 1. Manifest migawki

**File**: `backend/app/techqa/manifest.json`

**Intent**: Commitowane źródło oczekiwanych wartości, bo `docs/raport-techqa.md` jest poza Gitem.

**Contract**:
- `source: "nvidia/TechQA-RAG-Eval"`, `revision: "0b5bbc84b7f07d6d09d063130e90b716d8d4a32a"`.
- `files`: SHA-256 dla `README.md`, `train.json`, `corpus.zip` (wartości z raportu).
- `expected_documents: 28481`.

#### 2. Importer

**File**: `backend/app/techqa/importer.py`

**Intent**: Buduje deterministyczny stan migawki i zestawu fragmentów i zastępuje poprzedni stan atomowo.

**Contract**: `import_snapshot(conn, data_dir: Path, manifest: Manifest, config: ChunkerConfig) -> ImportReport`.

Weryfikacja (przed jakimkolwiek zapisem, każdy błąd kończy import bez zmian w bazie):
- `revision.txt` musi być równy `manifest.revision`, a SHA-256 każdego pliku z manifestu musi się zgadzać.
- Wpisy zipa są sortowane po nazwie, a katalogi pomijane. Wpis, który nie jest `corpus/<nazwa>.txt`, to błąd.
- Dekodowanie jest ścisłe UTF-8; błąd podaje nazwę pliku. Liczba dokumentów musi być równa `expected_documents`.
- Każdy `contexts[].filename` z `train.json` musi wskazywać istniejący dokument. Raport podaje liczbę rekordów, odwołań i różnych dokumentów.

Deduplikacja: grupy po `raw_sha256`. Dokument kanoniczny to najmniejszy `doc_id` w grupie. Wszystkie dokumenty dostają wiersz w `documents` z `canonical_doc_id`, a fragmenty powstają tylko dla kanonicznych.

Zapis: jedna transakcja w kolejności z Critical Implementation Details. `COPY` przez `cursor.copy()`.

Hash stanu:
- SHA-256 strumienia z bazy: manifest i konfiguracja (kanoniczny JSON), dokumenty posortowane po `doc_id` i fragmenty posortowane po `id`.
- Pola dokumentów: `doc_id`, `canonical_doc_id`, `title`, `raw_sha256`, `text_sha256`.
- Pola fragmentów: `id`, `doc_id`, `ordinal`, `headings`, `start_offset`, `end_offset`, `text_sha256`.
- Bez znaczników czasu.

`ImportReport`:
- liczba plików, dokumentów i kanonicznych;
- grupy duplikatów z identyfikatorami;
- liczba fragmentów, mediana i maksimum na dokument;
- dokumenty bez fragmentów;
- kontrola `train.json`;
- czasy etapów;
- `state_sha256` i porównanie z poprzednim: „pierwszy import”, „identyczny” albo „różny”.

#### 3. Polecenie CLI

**File**: `backend/app/cli.py`

**Intent**: Uruchamia import z ustawień i wypisuje raport.

**Contract**:
- `import-techqa [--data-dir PATH]`; domyślnie `Settings().techqa_dir`, z manifestem z pakietu i konfiguracją `sections-v1`.
- Kody wyjścia: 0 sukces, 1 błąd weryfikacji lub zapisu (bez zmian w bazie).
- Wynik „różny” przy ponownym imporcie jest wypisywany jako ostrzeżenie, ale kończy się kodem 0, bo zmiana kodu chunkera jest uzasadnioną przyczyną.

#### 4. Testy

**File**: `backend/tests/techqa/test_importer.py`

**Intent**: Dowodzi deduplikacji, atomowości i determinizmu na mini-migawce w tymczasowej bazie.

**Contract**:
- Fixture buduje w `tmp_path` mini-migawkę:
  - `corpus.zip` z fikstur fazy 2 plus dwie identyczne kopie jednego pliku;
  - `train.json` z odwołaniami;
  - `README.md` i `revision.txt`;
  - manifest z policzonymi hashami.
- Testy:
  - liczby dokumentów, kanonicznych i fragmentów, mapowanie kopii na najmniejszy `doc_id`, brak fragmentów dla kopii;
  - dwa importy dają ten sam `state_sha256`, a drugi raport mówi „identyczny”. Drugi import przechodzi przez jawne usuwanie poprzedniego stanu bez naruszenia kluczy;
  - po imporcie `chunk_sets.chunk_count` i `state_sha256` nie są NULL, a `chunk_count` równa się liczbie wierszy `chunks` zestawu;
  - zły hash pliku lub zła rewizja kończą import błędem bez wierszy w bazie;
  - brak dokumentu z `train.json` kończy import błędem;
  - błąd wstrzyknięty po zapisie dokumentów (monkeypatch) wycofuje całą transakcję, a poprzedni import zostaje nietknięty;
  - `documents.text[start:end]` (przez `substring` w SQL) równa się `chunks.text` dla wszystkich fragmentów.

### Success Criteria

#### Automated Verification

- ruff check, ruff format --check i mypy przechodzą
- Testy importera przechodzą z `DATABASE_URL`: `cd backend; uv run python -m pytest tests/techqa/test_importer.py`
- Pełny zestaw testów przechodzi: `cd backend; uv run python -m pytest -m "not corpus"`

#### Manual Verification

- Pierwszy pełny import w Compose (`docker compose run --rm backend python -m app.cli import-techqa`) kończy się sukcesem. Raport pokazuje:
  - 28 481 dokumentów, 28 478 kanonicznych i dwie grupy duplikatów z Key Discoveries;
  - 910 rekordów `train.json`, 610 odwołań, 496 dokumentów i 0 braków;
  - czas importu.

---

## Phase 4: Wyszukiwanie kontrolne i pełny przebieg

### Overview

Polecenie `search` do kontroli BM25 i tsvector, dowód idempotencji na pełnym korpusie, zapytania z pilotażu i opis w README.

### Changes Required

#### 1. Zapytania wyszukiwania

**File**: `backend/app/techqa/search.py`

**Intent**: Dwa zapytania SQL zwracające ranking fragmentów jednego zestawu. Pisane bezpośrednio w SQL, zgodnie z AGENTS.md.

**Contract**:
- `search_chunks(conn, query: str, *, method: Literal["bm25", "fts"], chunk_set_id: str, k: int = 10) -> list[SearchHit(rank, score, chunk_id, doc_id, headings, snippet)]`.
- BM25: `WHERE chunk_set_id = %s AND text ||| %s ORDER BY pdb.score(id) DESC, id LIMIT %s`.
- FTS: `websearch_to_tsquery('english', %s)` z `ts_rank_cd(tsv, q)`, sortowanie po wyniku malejąco, potem po `id`.
- `snippet` to pierwsze 200 znaków fragmentu.

#### 2. Polecenie CLI

**File**: `backend/app/cli.py`

**Intent**: Pozwala operatorowi sprawdzić indeksy bez interfejsu.

**Contract**: `search QUERY [--method bm25|fts] [--k 10] [--chunk-set ID]`. Domyślny zestaw to `techqa@<rewizja z manifestu>/sections-v1`. Wypisuje tabelę wyników.

#### 3. Testy

**File**: `backend/tests/techqa/test_search.py`

**Intent**: Dowodzi, że oba indeksy działają po imporcie mini-migawki.

**Contract**:
- Zapytanie z odmianą słowa (np. „restarting” dla dokumentu z „restart”) zwraca właściwy dokument w BM25 i FTS.
- Wyniki są posortowane malejąco po wyniku.
- Fragmenty innego `chunk_set_id` nie są zwracane.

#### 4. Dokumentacja

**Files**: `README.md`, `backend/README.md`

**Intent**: Opisuje, jak operator przygotowuje dane i uruchamia migracje, import i kontrolę wyszukiwania.

**Contract**: Sekcja „Import TechQA” z:
- poleceniami `migrate`, `import-techqa` i `search` w Compose;
- wymaganym układem `data/raw/techqa/` i informacją, że manifest sprawdza hashe;
- wynikiem pełnego importu: liczby, liczba fragmentów, czas i `state_sha256`.

#### 5. Raport z pełnego przebiegu

**File**: `context/changes/techqa-snapshot-import/import-report.md`

**Intent**: Zapisuje faktyczne wyniki pełnego importu i zapytań kontrolnych jako dowód dla S-02 i S-04.

**Contract**:
- Dwa raporty importu z tym samym `state_sha256`.
- Wyniki BM25 i FTS (top 10) dla pytań `TRAIN_Q000`, `TRAIN_Q001` i `TRAIN_Q003` z pozycją dokumentu oczekiwanego według `train.json`.
- Środowisko: obraz bazy i data.

### Success Criteria

#### Automated Verification

- ruff check, ruff format --check i mypy przechodzą
- Testy wyszukiwania przechodzą z `DATABASE_URL`: `cd backend; uv run python -m pytest tests/techqa/test_search.py`
- CI jest zielone dla wszystkich jobów

#### Manual Verification

- Drugi pełny import w Compose daje ten sam `state_sha256` co pierwszy, a raport mówi „identyczny”
- `search` z pytaniem `TRAIN_Q000` (BM25) zwraca `swg21996508` w top 10; wyniki trzech pytań są zapisane w `import-report.md`
- README pozwala przejść import od zera według opisu

---

## Testing Strategy

### Unit Tests

- Koperta: wieloliniowy tytuł, brak ` - United States`, brak `Text:`.
- Normalizacja:
  - każda reguła osobno i idempotencja;
  - encje: tylko ze średnikiem, jeden poziom (`&amp;lt;` → `&lt;`), ciągi bez średnika bez zmian;
  - kod i powtórzone linie zostają;
  - linie z tekstem po punktorze zostają;
  - dokładnie dwie puste linie zostają;
  - `&#13;` i luźny CR znikają.
- Chunker:
  - wszystkie niezmienniki;
  - łączenie krótkich sekcji APAR;
  - dzielenie sekcji dłuższej niż limit z nakładaniem;
  - linia dłuższa niż limit (twarde cięcie cofane do białego znaku, numery wersji w całości);
  - blok kodu bez pustych linii dzielony po `\n`;
  - nietypowe nagłówki (numer części, linia logu, zwykła wielkość liter);
  - dokument bez nagłówków;
  - determinizm (dwa wywołania dają równe listy).

### Integration Tests

Wszystkie działają w tymczasowej bazie na mini-migawce:
- migracje: idempotencja i wykrycie zmienionego pliku;
- import: liczby, deduplikacja, hash stanu, atomowość, weryfikacja manifestu i `train.json`, zgodność offsetów w SQL;
- wyszukiwanie: BM25 i FTS z odmianą słowa oraz izolacja zestawów.

### Manual Testing Steps

1. `docker compose up -d db` i `docker compose run --rm backend python -m app.cli migrate`, dwa razy.
2. `docker compose run --rm backend python -m app.cli import-techqa`. Sprawdzić liczby z raportu.
3. Powtórzyć import i porównać `state_sha256`.
4. `docker compose run --rm backend python -m app.cli search "<pytanie TRAIN_Q000>"` oraz `--method fts`.
5. Obejrzeć fragmenty sześciu dokumentów kontrolnych z kryterium 2.4.

## Performance Considerations

- Wejście ma około 105 mln znaków. Baza przechowa surowy tekst, znormalizowany tekst i fragmenty, rzędu 300–400 MB. To akceptowalne lokalnie.
- Import ładuje dane przez `COPY` do tabeli z istniejącym indeksem ParadeDB. Każdy zapis aktualizuje indeks transakcyjnie. Jeśli czas pełnego importu przekroczy około 15 minut, faza 4 zapisuje pomiar. Optymalizacja, np. przebudowa indeksu po załadowaniu, to osobna decyzja, a nie część tej zmiany.
- Hash stanu czyta posortowane wiersze strumieniowo (kursor serwerowy), bez ładowania całości do pamięci.

## Migration Notes

- Istniejące wolumeny z F-01 mają już rozszerzenia. `0001` używa `CREATE EXTENSION IF NOT EXISTS`, więc działa i na nich, i na czystej bazie CI.
- `db/init/01-extensions.sql` zostaje bez zmian. Kolejne zmiany schematu idą wyłącznie przez `backend/migrations/`.
- Wycofanie importu: `DELETE FROM snapshots WHERE id = …` (FK z `ON DELETE CASCADE` usuwają dokumenty, zestawy i fragmenty) albo `docker compose down -v`, co usuwa całą bazę.

## References

- Roadmapa S-01: `context/foundation/roadmap.md` (sekcja `### S-01`)
- PRD: FR-012, NFR Odtwarzalność (`context/foundation/prd.md:199`, `:217`)
- Profil danych: `docs/raport-techqa.md`; pilotaż: `docs/pilotaz-audytu-techqa.md`
- Architektura: `context/foundation/architecture-notes.md` (Baza i wyszukiwanie)
- Założenia importu i chunkingu: `docs/zalozenia-projektu.md` (sekcje 2–4)
- AI Devs 4: `02_02_chunking/src/strategies/separators.js:8-58`, `02_02_hybrid_rag/src/db/indexer.js:46-60`
- pg_search 0.27: `docs/reference/indexing/create-index.mdx` (tag `v0.27.0`), concepts/limitations, concepts/guarantees
- Poprzednia zmiana: `context/archive/2026-11-22-local-dev-stack/`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Schemat i runner migracji

#### Automated

- [x] 1.1 ruff check, ruff format --check i mypy przechodzą — 7714906
- [x] 1.2 Testy migracji przechodzą z DATABASE_URL — 7714906
- [x] 1.3 migrate w Compose kończy się kodem 0 dwa razy z rzędu — 7714906
- [x] 1.4 Kontener widzi /data/raw/techqa/corpus.zip — 7714906
- [ ] 1.5 CI jest zielone z krokiem migrate

#### Manual

- [x] 1.6 Użytkownik akceptuje nazwy tabel i kolumn — 7714906

### Phase 2: Parsowanie, normalizacja i chunking

#### Automated

- [x] 2.1 ruff check, ruff format --check i mypy przechodzą
- [x] 2.2 Testy jednostkowe przechodzą
- [x] 2.3 Niezmienniki na pełnym korpusie przechodzą lokalnie

#### Manual

- [x] 2.4 Przegląd fragmentów sześciu dokumentów kontrolnych

### Phase 3: Polecenie importu

#### Automated

- [ ] 3.1 ruff check, ruff format --check i mypy przechodzą
- [ ] 3.2 Testy importera przechodzą z DATABASE_URL
- [ ] 3.3 Pełny zestaw testów przechodzi

#### Manual

- [ ] 3.4 Pierwszy pełny import w Compose z poprawnymi liczbami

### Phase 4: Wyszukiwanie kontrolne i pełny przebieg

#### Automated

- [ ] 4.1 ruff check, ruff format --check i mypy przechodzą
- [ ] 4.2 Testy wyszukiwania przechodzą z DATABASE_URL
- [ ] 4.3 CI jest zielone dla wszystkich jobów

#### Manual

- [ ] 4.4 Drugi pełny import daje ten sam state_sha256
- [ ] 4.5 search zwraca swg21996508 w top 10 dla TRAIN_Q000
- [ ] 4.6 README pozwala przejść import od zera
