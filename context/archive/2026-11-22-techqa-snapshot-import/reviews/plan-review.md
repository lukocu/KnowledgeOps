<!-- PLAN-REVIEW-REPORT -->

# Plan Review: Import migawki TechQA i indeks BM25 (S-01)

- **Plan**: context/changes/techqa-snapshot-import/plan.md
- **Mode**: Deep (twierdzenia sprawdzone bezpośrednio na `corpus.zip`, bez sub-agenta)
- **Date**: 2026-11-23
- **Verdict**: REVISE → SOUND po poprawkach
- **Findings**: 2 critical, 1 warning, 1 observation

## Verdicts

| Dimension             | Verdict |
| --------------------- | ------- |
| End-State Alignment   | PASS    |
| Lean Execution        | PASS    |
| Architectural Fitness | PASS    |
| Blind Spots           | FAIL    |
| Plan Completeness     | WARNING |

## Grounding

Grounding: 6/6 paths ✓ (`backend/app/settings.py`, `db.py`, `main.py`, `backend/Dockerfile`, `.github/workflows/ci.yml`, `backend/tests/test_database.py`), 2/2 symbols ✓ (`database_url`, `DATABASE_URL` w CI), brief↔plan ✓.

## Findings

### F1 — Fragmenty zapisywane przed zestawem, do którego wskazuje FK

- **Severity**: ❌ CRITICAL
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Blind Spots
- **Location**: Critical Implementation Details (kolejność w transakcji), Phase 1 §2 (schemat)
- **Detail**: `chunks.chunk_set_id` ma FK do `chunk_sets`, a kolejność importu robi `COPY` fragmentów w kroku 6 i zapis zestawu dopiero w kroku 8. Pierwszy import kończy się naruszeniem klucza obcego. Ponowny import ma dwa kolejne problemy. Po pierwsze, krok 3 usuwa tylko fragmenty i dokumenty, więc wstawienie `snapshots` i `chunk_sets` trafia na istniejący klucz główny. Po drugie, Migration Notes zakładają kaskadowe `DELETE`, a schemat nie definiuje `ON DELETE CASCADE`.
- **Fix A ⭐ Recommended**: Zestaw wstawiany przed fragmentami z `state_sha256`/`chunk_count` = NULL, a na końcu `UPDATE`; jawne usuwanie w kolejności zależności; `ON DELETE CASCADE` w FK
  - Strength: Każdy zapis spełnia FK w chwili wykonania, kolejność jest czytelna w kodzie i nie wymaga odroczonych ograniczeń.
  - Tradeoff: Dwie kolumny `chunk_sets` są chwilowo NULL wewnątrz transakcji (niewidoczne na zewnątrz).
  - Confidence: HIGH — standardowy wzorzec rodzic→dziecko w jednej transakcji.
  - Blind spot: None significant.
- **Fix B**: FK `DEFERRABLE INITIALLY DEFERRED`, kolejność bez zmian
  - Strength: Najmniejsza zmiana w planie.
  - Tradeoff: Błąd spójności wychodzi dopiero przy commicie, a kolejność zapisu dalej sugeruje coś, co bez odroczenia nie działa.
  - Confidence: MEDIUM — działa, ale ukrywa zależność.
  - Blind spot: Wpływ odroczonych FK na `COPY` z indeksem ParadeDB niesprawdzony.
- **Decision**: FIXED (Fix A)

### F2 — Normalizacja nie jest idempotentna na korpusie i psuje adresy URL

- **Severity**: ❌ CRITICAL
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Blind Spots
- **Location**: Phase 2 §2 (reguła 1, kontrakt idempotencji), `test_corpus.py`
- **Detail**: Sprawdzone na `corpus.zip`. Po pierwsze, `swg1HE12470` zawiera `&amp;#27`: jedno `html.unescape` daje `&#27`, a drugie zamienia to na znak ESC (U+001B), więc `normalize_body(normalize_body(x)) != normalize_body(x)` i test pełnego korpusu nie przejdzie. Po drugie, `html.unescape` dekoduje encje bez średnika: w 13 dokumentach są `&param…`, `&amp`, `&gt`, `&quot`, `&current`, `&macro`, np. `&param_providerVersion=` w `swg1IV78320` staje się `¶m_providerVersion=`. Normalizacja psułaby tu adresy URL i kod. Encji zagnieżdżonych ze średnikiem (`&amp;lt;`) w korpusie nie ma. Dekodowanie jednego poziomu nie może być idempotentne dla takich danych, to wynika z definicji, więc kontrakt trzeba doprecyzować.
- **Fix A ⭐ Recommended**: Jednoprzebiegowe dekodowanie tylko encji ze średnikiem (dokładna nazwa z `html.entities.html5` albo odwołanie numeryczne); idempotencja na korpusie sprawdzana ściśle; `&amp;lt;` → `&lt;` udokumentowane testem jako jeden poziom
  - Strength: Nie psuje URL-i ani kodu, a na pełnym korpusie idempotencja zachodzi (0 encji zagnieżdżonych ze średnikiem).
  - Tradeoff: Własne wyrażenie zamiast jednego wywołania `html.unescape`.
  - Confidence: HIGH — sprawdzone na wszystkich 28 481 plikach.
  - Blind spot: Przyszłe migawki z `&amp;lt;` naruszyłyby idempotencję; test korpusu to wykryje.
- **Fix B**: Dekodowanie do punktu stałego
  - Strength: Idempotencja z konstrukcji.
  - Tradeoff: Zamienia celowo pokazany zapis `&lt;tag&gt;` na `<tag>` i dalej psuje `&param`, jeśli zostanie `html.unescape`.
  - Confidence: MEDIUM — zmienia znaczenie dokumentów o XML.
  - Blind spot: None significant.
- **Decision**: FIXED (Fix A)

### F3 — Przegląd ręczny nie obejmuje kodu, wersji ani nietypowych nagłówków

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 2 Manual Verification (2.4), fikstury fazy 2
- **Detail**: Kryterium 2.4 obejmuje dwa dokumenty. Profil pokazuje trzy dodatkowe ryzyka chunkera. (1) Długie bloki kodu i logów: `swg21681142` ma 129 linii bez pustej linii (~8,9 tys. znaków), co wymusza dzielenie po `\n`. (2) Numery wersji: `swg27038676` ma 235 numerów typu `8.5.5.1`. (3) Nietypowe nagłówki: numery części (`CI62KML`) w `swg24033234` i linia logu `APPHDL  : 0-270 APPID:` w `swg1IT14613` są wykrywane jako nagłówki, a `Problem Description:` w `swg21996508` nie jest.
- **Fix**: Rozszerzyć 2.4 o te cztery dokumenty z konkretnymi pytaniami do przeglądu i dodać syntetyczną fiksturę z długim blokiem kodu oraz numerami wersji.
- **Decision**: FIXED

### F4 — Twarde cięcie może rozciąć numer wersji

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 2 §3 (dzielenie dużych sekcji)
- **Detail**: Nakładanie jest przesuwane do białego znaku, ale „twarde cięcie” nie ma takiej reguły. Linia dłuższa niż 1 500 znaków może zostać przecięta w środku `9.0.0.7` albo identyfikatora.
- **Fix**: Twarde cięcie cofa się do ostatniego białego znaku w limicie; w środku tokenu tnie tylko wtedy, gdy białego znaku nie ma. Test: każdy numer wersji z fikstury występuje w całości w co najmniej jednym fragmencie.
- **Decision**: FIXED
