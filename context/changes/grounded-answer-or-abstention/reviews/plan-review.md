<!-- PLAN-REVIEW-REPORT -->

# Plan Review: Odpowiedź z cytatami albo abstencja (S-02)

- **Plan**: context/changes/grounded-answer-or-abstention/plan.md
- **Mode**: Deep
- **Date**: 2026-11-23
- **Verdict**: REVISE → SOUND po poprawkach
- **Findings**: 0 critical, 3 warnings, 2 observations

## Verdicts

| Dimension             | Verdict |
| --------------------- | ------- |
| End-State Alignment   | WARNING |
| Lean Execution        | PASS    |
| Architectural Fitness | PASS    |
| Blind Spots           | WARNING |
| Plan Completeness     | WARNING |

## Grounding

12/12 paths ✓, 5/5 symbols ✓, brief↔plan ✓.

Potwierdzone w kodzie:
- FastAPI dokleja nagłówki z zależności (ciasteczko) do odpowiedzi SSE (`fastapi/routing.py:702`).
- `load_manifest()` czyta `app/techqa/manifest.json` z pakietu, więc działa bez danych.
- Job `backend` w CI ma ParadeDB i stosuje migracje.

## Findings

### F1 — Plan nie mówi, jak uruchamiać testy asynchroniczne i testy API na bazie

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Blind Spots
- **Location**: Faza 1 (#5), Faza 2 (#5), Faza 3 (#5)
- **Detail**: Fazy 1–3 każą testować na `imported_conn`, ale ta fikstura nie nadaje się do nowych testów:
  - jest zdefiniowana w `tests/techqa/conftest.py:21`, więc nowe katalogi testów jej nie widzą;
  - zwraca synchroniczne połączenie;
  - nie ma konfiguracji testów async.
  Testy API potrzebują puli aplikacji wskazującej na bazę tymczasową. Obecny `test_health` omija lifespan, bo tworzy `TestClient` bez `with`.
- **Fix**: przenieść `conn` i `imported_conn` do `tests/conftest.py` i dodać:
  - `anyio_backend` i `async_imported_conn` (`@pytest.mark.anyio`);
  - `api_client` z `DATABASE_URL` wskazującym bazę tymczasową i `with TestClient(app)`;
  - osobną fiksturę testu `live`, która korzysta z `DATABASE_URL`.
- **Decision**: FIXED (Fix in plan)

### F2 — Model cytatu jest niespójny z kanwą: jeden numer, jeden cytat, całe zaznaczenie

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: End-State Alignment
- **Location**: Faza 2 (#3), Faza 5 (#3, #4), Testing Strategy
- **Detail**: Dwie tezy z jednego fragmentu dzielą numer, ale `citations[]` ma tylko jedno pole `quote`. S1A zaznacza cytowane zdanie, a plan zaznaczał cały fragment (do 1500 znaków).
- **Fix**:
  - `quote_check` zapisuje offsety cytatu;
  - `citations[].claims` zawiera `[{claim_index, quote, quote_start, quote_end}]`;
  - panel zaznacza cytaty w `<mark>` i pokazuje wszystkie tezy z danym numerem;
  - w abstencji zaznaczony jest cały fragment.
- **Decision**: FIXED (Fix in plan)

### F3 — Zapasowe pytanie kontrolne abstencji też nie jest sprawdzone w korpusie

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Faza 1 (#4)
- **Detail**: Plan nie sprawdza w korpusie pytania o Streams i DB2 z makiety 1C, a TechQA ma technoty o Streams.
- **Fix**: sprawdzić oba pytania tą samą procedurą. Gdy oba mają odpowiedź w korpusie, zatrzymać się i ustalić z użytkownikiem inne pytanie.
- **Decision**: FIXED (Fix in plan)

### F4 — Limity czasu nie pasują do budżetu p95 < 10 s

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Faza 2 (#1), Faza 3 (#3), Performance Considerations
- **Detail**: `chat_timeout_s=20` dotyczy każdego z dwóch wywołań i nie ma limitu na całe zapytanie, więc błąd może przyjść dopiero po ~40 s.
- **Fix**: `answer_deadline_s=25` jako `asyncio.timeout` wokół grafu i `chat_timeout_s=12`.
- **Decision**: FIXED (Fix in plan)

### F5 — Kontrola kontraktu w 3.4 i 5.2 nie przejdzie przed commitem

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Faza 3 (3.4), Faza 5 (5.2), Progress
- **Detail**: `git diff --exit-code` porównuje z HEAD, więc niezacommitowany nowy kontrakt zawsze daje różnicę.
- **Fix**: najpierw `git add` plików kontraktu, potem regeneracja i `git diff --exit-code` (porównanie z indeksem).
- **Decision**: FIXED (Fix in plan)
