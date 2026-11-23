<!-- IMPL-REVIEW-REPORT -->

# Implementation Review: Import migawki TechQA i indeks BM25 (S-01)

- **Plan**: context/changes/techqa-snapshot-import/plan.md
- **Scope**: Full plan
- **Reviewed phases**: 1, 2, 3, 4
- **Date**: 2026-11-23
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 3 warnings, 4 observations

## Verdicts

| Dimension           | Verdict |
| ------------------- | ------- |
| Plan Adherence      | PASS    |
| Scope Discipline    | PASS    |
| Safety & Quality    | WARNING |
| Architecture        | WARNING |
| Pattern Consistency | WARNING |
| Success Criteria    | PASS    |

Success Criteria: ruff check, ruff format i CI (dcc31b1) zielone; mypy i testy z bazą przeszły lokalnie przy commitach faz (91 passed). Podczas przeglądu Windows zablokował lokalnie `mypy.exe` i bibliotekę libpq (zasady kontroli aplikacji), więc nie powtórzono ich w tym przeglądzie.

## Findings

### F1 — Import usuwa wszystkie zestawy fragmentów migawki, nie tylko własny

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Architecture
- **Location**: backend/app/techqa/importer.py:309-320
- **Detail**: Usuwanie jest po `snapshot_id`: kasuje wszystkie `chunk_sets` migawki, dokumenty i samą migawkę. Plan opisuje jeden wariant (`sections-v1`), więc dziś jest zgodne z planem. Gdy S-12 doda drugi wariant chunkera, import jednego wariantu skasuje drugi, a raport powie „pierwszy import". Kasowanie migawki kaskaduje też do przyszłych tabel odwołujących się do `documents` i `chunks` (ewaluacje, decyzje).
- **Fix**: Zostawić jak jest do S-12 i dopisać to ograniczenie w README i w komentarzu importera, albo teraz zawęzić usuwanie do `chunk_set_id`.
  - Strength: Dopisanie notatki jest tanie i zgodne z planem; zawężenie chroni przyszłe dane.
  - Tradeoff: Zawężenie wymaga rozstrzygnięcia, co z dokumentami i migawką przy przebudowie (zmiana kontraktu z planu).
  - Confidence: MED — zależy od tego, jak S-12 będzie wersjonować zestawy.
  - Blind spot: Nie sprawdzono, czy S-02 doda tabele z FK do `chunks`.
- **Decision**: FIXED (Fix A: udokumentowane ograniczenie w komentarzu importera)

### F2 — Brak `.gitattributes`: hash migracji zależy od końców linii

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: backend/app/migrations.py:56-61 (brak `.gitattributes` w repo)
- **Detail**: SHA-256 migracji liczony jest z surowych bajtów. Na maszynie z `core.autocrlf=true` pliki `.sql` wyjdą z CRLF i `MigrationError` zgłosi „zmieniono treść" dla bazy zastosowanej z innego checkoutu. Fikstury `.txt` są objęte tym samym ryzykiem (`raw_sha256` wchodzi do `state_sha256`). Tu `core.autocrlf=input`, więc lokalnie nie występuje.
- **Fix**: Dodać `.gitattributes` z `*.sql text eol=lf` i `backend/tests/fixtures/techqa/*.txt text eol=lf`.
- **Decision**: FIXED (.gitattributes: *.sql i fikstury *.txt z eol=lf)

### F3 — Brak blokady współbieżnego importu

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: backend/app/techqa/importer.py:299-383
- **Detail**: Dwa równoległe importy czytają nieaktualny `previous`, a drugi może skończyć błędem unikalności przy wstawianiu migawki. Transakcja się wycofa, więc nie ma uszkodzenia danych, tylko mylący błąd.
- **Fix**: `SELECT pg_advisory_xact_lock(...)` na początku transakcji importu.
- **Decision**: FIXED (pg_advisory_xact_lock na początku transakcji importu, test przez pg_locks)

### F4 — Błędy wejścia z zipa i train.json nie są opakowane w `ImportFailure`

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: backend/app/techqa/importer.py:131-155
- **Detail**: `BadZipFile`, `JSONDecodeError` i `KeyError` na `context["filename"]` trafiają do CLI jako goły `Błąd: 'filename'`. Wzorzec nazwy wpisu zipa używa `.match` z `$`, które przyjmuje końcowy `\n`; lepszy jest `fullmatch`. Odczyt wpisu nie ma limitu rozmiaru, ale zip jest wcześniej sprawdzany hashem z manifestu.
- **Fix**: Opakować te wyjątki w `ImportFailure` z nazwą pliku i użyć `fullmatch`.
- **Decision**: FIXED (BadZipFile, JSON i brak filename opakowane w ImportFailure, fullmatch, raise zamiast assert)

### F5 — Brak walidacji konfiguracji chunkera i parametru `--k`; kolacja remisów w search

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: backend/app/techqa/chunking.py:20-25, backend/app/techqa/search.py
- **Detail**: Przy `overlap_chars >= max_chars` twarde cięcie dostaje limit <= 0. Konfiguracja jest dziś stała, więc ryzyko jest teoretyczne. `ORDER BY ..., id` w search używa domyślnej kolacji bazy, a hash stanu `COLLATE "C"`, więc kolejność remisów może różnić się między środowiskami. Ujemne `--k` daje błąd Postgresa.
- **Fix**: `__post_init__` w `ChunkerConfig`, `COLLATE "C"` przy tie-breaku i walidacja `k >= 1`.
- **Decision**: FIXED (ChunkerConfig.__post_init__, walidacja k, COLLATE "C" w tie-breaku)

### F6 — Powielone elementy testów

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: backend/tests/techqa/test_search.py, test_importer.py, test_corpus.py
- **Detail**: `test_search.py` importuje `build_snapshot` i stałe z innego modułu testowego; fixture `conn` jest zduplikowany i inaczej typowany; `test_corpus.py` ma na sztywno 28 481 zamiast `load_manifest().expected_documents`. Brakuje testów: izolacji migawek (F1), ścieżek błędów importera (zły wpis zipa, zły UTF-8, uszkodzona koperta) i zapytań wyszukiwania ze znakami specjalnymi.
- **Fix**: Przenieść budowę mini-migawki i fixture `conn` do `helpers.py`/`conftest.py` i dopisać wymienione testy.
- **Decision**: FIXED (wspólne helpery i fixture, manifest zamiast 28481, nowe testy)

### F7 — Kolejność nagłówków i uwagi operacyjne

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: backend/app/cli.py, .github/workflows/ci.yml, import-report.md
- **Detail**: `reconfigure(encoding="utf-8")` w CLI wykonuje się po `parse_args`, więc `-h` i błędy argparse mogą wyświetlić krzaczki. Połączenie CLI nie ma `connect_timeout` (db.py ma 5 s). Testy `corpus` nie biegną w CI, więc niezmienniki pełnego korpusu sprawdza się tylko lokalnie. `import-report.md` przypisuje Recall@k do S-02, a plan do S-04.
- **Fix**: Przenieść `reconfigure` przed parsowanie, dodać `connect_timeout` i poprawić etykietę etapu w raporcie.
- **Decision**: FIXED (reconfigure przed parse_args, connect_timeout=5, etykieta S-04 w raporcie)
