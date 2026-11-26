# S-07: Sprzeczne źródła i różne zalecenia — Plan Brief

> Full plan: `context/changes/conflicting-sources/plan.md`
> Research: `context/changes/conflicting-sources/research.md`

## What & Why

Wdrażamy etap **S-07 (`conflicting-sources`)**: obsługę sytuacji, w której dokumenty w bazie wiedzy podają wzajemnie wykluczające się wartości lub instrukcje (`US-03`, `FR-005`, `FR-019`, `FR-014`, ekran 4, Sprawdzian 2b). Zamiast po cichu wybierać jedną odpowiedź, system pokazuje konsultantowi obie strony z dosłownymi cytatami i porównaniem zakresu oraz mierzy trafność rozróżnienia stanów na oznaczonym zestawie syntetycznym.

## Starting Point

Graf odpowiedzi (`retrieve -> draft -> quote_check -> verify -> compose | abstain`) i interfejs Asystenta obsługują dziś wyłącznie wynik binarny (`answered` vs `abstained`), a `verify` ocenia pojedynczą tezę z jednym fragmentem bez porównywania dokumentów. Korpus TechQA (`28 481` dokumentów) ma jedną migawkę bez historii wersji i nie zawiera naturalnych sprzeczności, a dopisanie danych syntetycznych wprost do `techqa@<rev>` złamałoby `state_sha256` reimportu S-01 i czystość ewaluacji S-06.

## Desired End State

Konsultant zadający pytanie o sprzeczne lub rozbieżne zalecenia otrzymuje widok `A vs B` (ekran 4) z obiema instrukcjami, dosłownymi cytatami, tabelą porównania kontekstu (wartość, odbiorca, data, wersja), oznaczeniem `DOKUMENT SYNTETYCZNY`, nawigacją `A ↔ B` w panelu dowodu i kopiowaniem obu wersji ze źródłami — także w oknie `390 px`. Stan nazywa się `✕ Sprzeczność` wyłącznie przy tym samym zakresie (produkt, wersja, kontekst); inaczej `Źródła podają różne zalecenia — Nierozstrzygnięte`, co potwierdza eksperyment Sprawdzianu 2b (`n=24`) w Langfuse Cloud.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Izolacja danych syntetycznych | Osobna migawka `synthetic@v1` (`synthetic@v1/sections-v1`) + `ANY(chunk_set_ids)` w BM25 | Zachowuje zero zmian w `importer.py`, nienaruszony `state_sha256` TechQA i czysty S-06 przy wspólnym indeksie ParadeDB. | Plan |
| Zakres danych syntetycznych w demo UI | Pełny zestaw S-07 z badge'em `DOKUMENT SYNTETYCZNY` | Pozwala na żywo zademonstrować w przeglądarce oba stany (`Nierozstrzygnięte` i `✕ Sprzeczność`). | Plan |
| Kontrakt konfliktu i `>= 3` źródła | `ConflictingResult` (`outcome="conflicting"`) z główną parą `A vs B` + `extra_conflicting_docs` | Chroni czytelność układu 2 kolumn i tabeli z `S4.dc.html` (również na `390 px`) bez ukrywania faktu istnienia dalszych źródeł. | Plan |
| Miejsce wykrywania konfliktu | Warunkowy węzeł `detect_conflict` po `verify` (tylko dla `>= 2` różnych `doc_id`) + strażnik zakresu w Pythonie | Pytania jednodokumentowe robią nadal 2 wywołania LLM, a obie strony konfliktu mają gwarantowany `quote_check` i werdykt `supported`. | Plan |
| Akcje ekranu 4 (`PanelFrame`) | `Otwórz oba dokumenty` w `EvidencePanel` (`A ↔ B`) + `Doprecyzuj…` z fokusem w `Composer` | Reużywa przetestowany panel boczny i arkusz `<dialog>` na `390 px` z obsługą klawiatury i `Escape`. | Plan |
| Sprawdzian 2b (`FR-014`) | 24 przypadki (`3 × 8`: `contradiction`, `different_recommendations`, kontrolne `answered`) + miary deterministyczne | Mierzy rozróżnienie zakresu i fałszywe alarmy konfliktu w Langfuse Cloud bez kosztu i wariancji sędziego LLM. | Plan |
| Paleta stanu `✕ Sprzeczność` | Tokeny `#fbe9e7` / `#a3231a` i ikona `#b3261e` z `S5.dc.html` | Bierze kanoniczny styl bezpośrednio z kanwy Claude Design zamiast tworzyć nową paletę. | Research |

## Scope

**In scope:** migracja `0003` i CLI `import-synthetic-conflicts` (`synthetic@v1`); wyszukiwanie nakładkowe BM25 i metadane dokumentów w `/api/evidence` i `/api/documents`; warunkowy węzeł `detect_conflict` ze strażnikiem zakresu i `ConflictingResult`; widok `ConflictView` (oba stany, PL/EN, `390 px`), `formatConflictForCopy` (`FR-019`) i kompatybilność S-06; zbiór `24` przypadków, CLI `eval-conflicts`, przebieg w Langfuse Cloud, `eval-report.md` i aktualizacja `docs/przeplyw-danych.md`.

**Out of scope:** modyfikacja `techqa/importer.py`; wielokolumnowa tabela `A vs B vs C`; podwójny panel boczny dowodów; sędzia LLM w Sprawdzianie 2b; surowe teksty TechQA w gicie; konfiguracja Playwrighta (`/10x-e2e-setup`) i audyt spraw (`S-08`).

## Architecture / Approach

`import-synthetic-conflicts` zapisuje autorskie dokumenty z `backend/app/synthetic/documents.json` jako `synthetic@v1/sections-v1`. W trybie pytań `retrieve` przeszukuje `[techqa@<rev>/sections-v1, synthetic@v1/sections-v1]` przez `chunk_set_id = ANY(...)` na indeksie `chunks_search_idx`. Zaktualizowany `draft` wyodrębnia osobne tezy z dosłownymi cytatami dla rozbieżnych źródeł; po przejściu `quote_check` i `verify` graf uruchamia `detect_conflict` tylko przy `>= 2` różnych `doc_id`, po czym Python wymusza regułę zakresu (`resolve_conflict_type`) i składa `ConflictingResult` prezentowany w `ConflictView`.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Schemat `0003`, migawka `synthetic@v1` i wyszukiwanie nakładkowe | Migracja SQL, CLI `import-synthetic-conflicts`, `ANY(chunk_set_ids)` w BM25, metadane w `/api/evidence` i `/api/documents` | Dopasowanie `chunk_set_id` do `snapshot_id` przy podglądzie pełnego dokumentu syntetycznego |
| 2. Wykrywanie konfliktu w grafie LangGraph i kontrakt API | Węzeł `detect_conflict`, strażnik zakresu, `ConflictingResult`, kompatybilność S-06, OpenAPI + `schema.d.ts` | Prompt `draft` musi konsekwentnie wyodrębniać tezy obu stron zamiast wybierać jedną |
| 3. Ekran 4 (`ConflictView`), kopiowanie obu wersji i okno `390 px` | Widok obu stanów `A vs B`, `formatConflictForCopy`, `EvidencePanel` `A ↔ B`, słowniki PL/EN, układ `390 px` | Brak poziomego przewijania tabeli porównawczej przy `390 px` i kompatybilność wsteczna starych wierszy `answers` |
| 4. Zestaw syntetyczny (24 przypadki), Sprawdzian 2b w Langfuse i raport | Pełny zbiór `3 × 8`, CLI `eval-conflicts`, eksperyment w Langfuse Cloud, `eval-report.md`, `przeplyw-danych.md` | Dobór kotwic TechQA tak, by BM25 top-8 stabilnie zwracał oba dokumenty pary bez przecieku tekstów TechQA do gita |

**Prerequisites:** działający kontener ParadeDB z zaimportowaną migawką TechQA (`S-01`), skonfigurowane klucze `OPENAI_API_KEY` oraz `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` w `.env`.
**Estimated effort:** ~3–4 sesje implementacyjne w 4 fazach.

## Open Risks & Assumptions

- Wykrycie konfliktu zależy od tego, że zarówno dokument TechQA, jak i sparowany dokument `synthetic@v1` zmieszczą się w `top-k` (`k=8`) BM25 i zostaną wyodrębnione w `draft` — podczas budowy 24 przypadków w Fazie 4 zweryfikujemy zapytania względem `top-8` BM25.
- Dokumenty syntetyczne są aktywne w demo UI dla wybranych tematów IBM; badge `DOKUMENT SYNTETYCZNY` jednoznacznie odróżnia je od oryginalnego korpusu TechQA.

## Success Criteria (Summary)

- Konsultant widzi obie strony rozbieżnych zaleceń z dosłownymi cytatami, metadanymi i kopią do schowka (`FR-019`), przy czym stan `✕ Sprzeczność` pojawia się wyłącznie dla tego samego zakresu, a `Nierozstrzygnięte` dla różnego lub nieznanego zakresu (także w oknie `390 px`).
- Czysty `import-techqa` oraz ewaluacja S-06 (`eval-abstention`) zachowują 100% dotychczasowej idempotentności i kompatybilności.
- Sprawdzian 2b (`eval-conflicts`, `n=24`) kończy się z `0` błędnych klasyfikacji różnych wersji jako `contradiction`, `100%` inwariantów cytatów obu stron i opublikowanym przebiegiem w Langfuse Cloud.
