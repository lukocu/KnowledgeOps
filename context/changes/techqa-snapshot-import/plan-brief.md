# Import migawki TechQA i indeks BM25 (S-01) — Plan Brief

> Full plan: `context/changes/techqa-snapshot-import/plan.md`

## What & Why

Operator ma zaimportować niezmienną migawkę NVIDIA TechQA-RAG-Eval jednym poleceniem CLI w kontenerze backendu. Polecenie zapisuje rewizję i hashe plików, deduplikuje dokładne kopie i dzieli dokumenty na fragmenty z pochodzeniem. Na fragmentach powstaje indeks BM25 (pg_search) i bazowy tsvector. Każdy kolejny etap (odpowiedź z cytatami, ewaluacje, audyt) korzysta z tych samych fragmentów i identyfikatorów, a NFR Odtwarzalność wymaga, żeby ponowny import dawał identyczny stan (FR-012).

## Starting Point

F-01 dało ParadeDB w Compose z pg_search i pgvector, backend FastAPI z `/api/health` i CI. Nie ma schematu, migracji ani poleceń CLI. Dane leżą w `data/raw/techqa/`, poza Gitem, a ich hashe zgadzają się z `docs/raport-techqa.md`.

## Desired End State

`migrate` zakłada schemat, a `import-techqa` buduje w jednej transakcji:

- 28 481 dokumentów, z czego 28 478 kanonicznych; 3 kopie są zmapowane na kanoniczny dokument;
- fragmenty wariantu `sections-v1` z offsetami;
- oba indeksy.

Dwa kolejne importy dają ten sam hash stanu. Polecenie `search` zwraca ranking BM25 albo FTS, a dla pytania `TRAIN_Q000` znajduje `swg21996508`.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) |
| --- | --- | --- |
| Migracje schematu | Własny runner: `backend/migrations/NNNN_*.sql`, tabela `schema_migrations` z SHA-256 | Bez nowych zależności, a wyszukiwanie i tak piszemy w czystym SQL. |
| Zakres importu | Korpus; `train.json` tylko hashowany i sprawdzany pod kątem odwołań | Podział pytań na zbiory (przeciek TRAIN/DEV, konflikty etykiet) jest decyzją S-04. |
| Normalizacja | Encje HTML (tylko ze średnikiem, jeden poziom), CR, NBSP, białe znaki na końcu linii, puste punktory, ciągi ≥3 pustych linii → 1 | Obejmuje wszystkie problemy z profilu; kod, URL-e z `&param` i powtórzenia zostają, a normalizacja jest idempotentna na całym korpusie. |
| Chunking | Sekcje TechQA łączone do 1 500 znaków; duże sekcje dzielone po akapitach i liniach z nakładaniem 150 | Typowy dokument daje 2–3 fragmenty, a cytat jest precyzyjny. |
| Duplikat | Identyczny SHA-256 surowego pliku; kanoniczny = najmniejszy `doc_id` | Zgodne z profilem (3 kopie), a każdy identyfikator TechQA się rozwiązuje. |
| Ponowny import | Pełna przebudowa w jednej transakcji i porównanie hasha stanu | Każde uruchomienie dowodzi determinizmu, a błąd nie zostawia stanu częściowego. |
| Źródło treści | `corpus.zip` sprawdzany względem commitowanego manifestu | Zip jest objęty hashem, a `docs/` jest poza Gitem. |
| Offsety | W znakach znormalizowanej treści; surowy plik zapisany osobno | Cytat wskazuje dokładne miejsce, a kurs (`indexOf`) myli się przy powtórzeniach. |
| Testy | Tymczasowa baza na test, syntetyczna mini-migawka; test pełnego korpusu tylko lokalnie | CI nie ma danych, a dane deweloperskie się nie mieszają. |

## Scope

**In scope:**
- runner migracji i schemat z indeksami BM25 i tsvector;
- montowanie `data/raw/techqa` tylko do odczytu w kontenerze;
- parsowanie, normalizacja i chunking z testami;
- `import-techqa` z manifestem, deduplikacją, kontrolą `train.json` i hashem stanu;
- `search` do kontroli przez operatora;
- README i raport z pełnego przebiegu.

**Out of scope:**
- pytania z `train.json` w bazie i podział na zbiory;
- embeddingi i indeks wektorowy;
- Recall@k i RRF;
- eksperymenty z chunkingiem;
- deduplikacja po tekście znormalizowanym;
- usuwanie powtórzonego kodu;
- wykrywanie języka;
- endpointy HTTP;
- downgrade migracji.

## Architecture / Approach

Polecenia są w `python -m app.cli` (`argparse`, synchroniczny psycopg 3). Przepływ: manifest i hashe → odczyt `corpus.zip` → `parse_document` → `normalize_body` (`norm-v1`) → deduplikacja → `chunk_document` (`sections-v1`) → jedna transakcja: usunięcie poprzedniego stanu (fragmenty → zestaw → dokumenty → migawka), zapis migawki, `COPY` dokumentów, zapis zestawu bez hasha, `COPY` fragmentów, hash stanu z bazy, uzupełnienie zestawu.

Identyfikatory są deterministyczne:
- migawka: `techqa@<rewizja>`;
- zestaw: `<migawka>/sections-v1`;
- fragment: `<zestaw>/<doc_id>/<ordinal>`.

Na `chunks` jest jeden indeks ParadeDB (`id`, `chunk_set_id`, `text` ze stemmerem angielskim) i kolumna generowana `tsvector` z GIN.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Schemat i runner migracji | `migrate`, tabele, oba indeksy, montowanie danych, krok w CI | Składnia tokenizera pg_search 0.27 (stemmer ze stopwords) niepotwierdzona |
| 2. Parsowanie, normalizacja, chunking | Czyste funkcje z niezmiennikami offsetów, test na pełnym korpusie | Przypadki brzegowe offsetów przy nakładaniu i twardym cięciu |
| 3. Polecenie importu | `import-techqa`: atomowy zapis, deduplikacja, hash stanu, raport | Czas `COPY` do tabeli z indeksem ParadeDB |
| 4. Wyszukiwanie i pełny przebieg | `search`, dwa pełne importy, raport z zapytań, README | Wynik BM25 dla pytań kontrolnych może wskazać słabość chunkingu |

**Prerequisites:** F-01 zamknięte; dane w `data/raw/techqa/` (sprawdzone 2026-11-23); Docker Compose działa.
**Estimated effort:** około 3–4 sesji, po jednej na fazę; faza 2 jest największa.

## Open Risks & Assumptions

- Jeśli `stemmer` i `stopwords_language` nie łączą się w jednym rzutowaniu, zostaje sam stemmer. Faza 1 to rozstrzyga testem.
- Pełny import do tabeli z istniejącym indeksem BM25 może trwać długo. Pomiar trafi do raportu, a ewentualna optymalizacja będzie osobną decyzją.
- Odczyt z bind mounta jako uid 10001 zakłada uprawnienia Docker Desktop na Windows. Faza 1 to sprawdza.
- Nagłówki pisane zwykłą wielkością liter nie są wykrywane. Takie sekcje łączą się z poprzednimi, co jest akceptowalne dla wersji bazowej.

## Success Criteria (Summary)

- Operator importuje pełną migawkę jednym poleceniem i dostaje raport z liczbami zgodnymi z profilem danych.
- Dwa kolejne importy dają ten sam `state_sha256`.
- BM25 i FTS zwracają sensowne fragmenty dla pytań z pilotażu, z dokładnymi offsetami do cytowania.
