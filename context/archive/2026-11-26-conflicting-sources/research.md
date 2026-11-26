---
date: 2026-11-26T17:39:24+01:00
researcher: Antigravity
git_commit: 134f6e53d06594d882d6abf1e0922ac84aa98dcf
branch: main
repository: KnowledgeOps
topic: "S-07: Sprzeczne źródła i różne zalecenia (conflicting-sources)"
tags: [research, codebase, answering, retrieval, evals, frontend, conflicting-sources, S-07]
status: complete
last_updated: 2026-11-26
last_updated_by: Antigravity
---

# Research: S-07 — Sprzeczne źródła i różne zalecenia (`conflicting-sources`)

**Date**: 2026-11-26T17:39:24+01:00
**Researcher**: Antigravity
**Git Commit**: 134f6e53d06594d882d6abf1e0922ac84aa98dcf
**Branch**: main
**Repository**: KnowledgeOps

## Research Question

Jak obecny stan bazy kodu (backendowy graf odpowiedzi i schemat ParadeDB, frontend Asystenta i kopiowanie z cytatami, infrastruktura ewaluacji i Langfuse oraz wzorce z AI Devs 4 i archiwum decyzji) wspiera realizację etapu **S-07 (`conflicting-sources`)** z `context/foundation/roadmap.md:289-310` (PRD: `US-03`, `FR-005`, `FR-019`, `FR-014`, Sprawdzian 2b, ekran 4 `S4.dc.html`), jakie kontrakty trzeba rozszerzyć i jakie decyzje projektowe pozostają otwarte przed `/10x-plan`?

## Summary

1. **Graf odpowiedzi (`backend/app/answering/`) jest dziś ściśle binarny (`answered` vs `abstained`) i nie porównuje źródeł między sobą.** Węzeł `verify` widzi wyłącznie pojedynczą tezę i jej własny fragment (`backend/app/answering/nodes.py:226-237`), więc werdykt `contradicted` oznacza wyłącznie sprzeczność tezy z jej własnym cytatem, a nie konflikt między dwoma dokumentami. Tezy `contradicted` są odrzucane na równi z `insufficient` (`nodes.py:134-145`).
2. **Schemat bazy danych (`0001_techqa_schema.sql`) i importer TechQA (`backend/app/techqa/importer.py`) nie obsługują dokumentów syntetycznych ani metadanych daty/wersji.** `documents` nie ma pól `is_synthetic`, `doc_date` ani `product_version` (`0001_techqa_schema.sql:15-25`). Dopisanie syntetycznego dokumentu (np. `SYN-KB-0007`) bezpośrednio do domyślnej migawki/`chunk_set_id` koliduje z trzema mechanizmami: walidacją `expected_documents = 28481` i destrukcyjnym reimportem w `import_snapshot()` (`importer.py:290-294, 328-339`), wyliczaniem `chunk_sets.state_sha256` (`importer.py:246-275`) oraz czystością wyszukiwania BM25 podczas powtórzeń ewaluacji S-06 (`backend/app/evals/runner.py:455`).
3. **Frontend Asystenta (`frontend/app/`) obsługuje tylko dwa stany wyniku (`answered`, `abstained`), ma wpisane na stałe `evidence.unknownDate` i brakuje mu widoku ekranu 4 oraz tokenu kolorystycznego dla „sprzeczności”.** Istniejące komponenty (`AssistantFrame`, `PanelFrame` z arkuszem `<dialog>` poniżej `768 px`, `EvidencePanel`, `PreparationDetails`, `useCopy`, `formatAnswerForCopy`, i18n PL/EN z kontrolą typów `Record<TranslationKey, string>`) stanowią solidną bazę do rozszerzenia, ale `routes/answer.tsx:284-327`, `PreparationDetails.tsx:72-74`, `lib/copy-answer.ts:10-37` i `lib/stages.ts:8-43` wymagają obsługi nowego stanu.
4. **Infrastruktura ewaluacji (`backend/app/evals/`) dostarcza gotowe wzorce odtwarzalności, raportowania i Langfuse 5.2.0, ale `runner.py` i `langfuse_eval.py` są silnie sprzężone z binarnym kontraktem S-06.** `execute_item()` zakłada `assert isinstance(result, AnsweredResult)` dla każdego wyniku niebędącego `AbstainedResult` (`backend/app/evals/runner.py:343-357`), więc dodanie nowego `outcome` w grafie bez aktualizacji S-06 złamie runner S-06. Główne metryki Sprawdzianu 2b (rozróżnienie „sprzeczność” vs „różne zalecenia — nierozstrzygnięte” oraz obecność cytatów po obu stronach) są w pełni deterministyczne.
5. **Moduł AI Devs 4 `01_01_grounding` nie zawiera mechanizmu fact-checkingu ani wykrywania sprzeczności** (wykonuje wyłącznie adnotację HTML wynikami `web_search`), co potwierdza wcześniejsze ustalenia z planu S-02 (`context/archive/2026-11-23-grounded-answer-or-abstention/plan.md:31`).

---

## Detailed Findings

### 1. Backend: graf odpowiedzi, modele Pydantic i API (`backend/app/answering/`, `backend/app/api/`)

- **Topologia i stan grafu:** `build_answer_graph()` definiuje 6 węzłów (`retrieve`, `draft`, `quote_check`, `verify`, `compose`, `abstain`) w łańcuchu `START -> retrieve -> (draft | abstain) -> (quote_check | abstain) -> (verify | abstain) -> (compose | abstain) -> END` (`backend/app/answering/graph.py:56-73`). `AnswerState` dopuszcza wyłącznie `outcome: Literal["answered", "abstained"]` (`backend/app/answering/nodes.py:55-66`).
- **Kontrakt promptów i brak porównania przekrojowego:**
  - `PROMPT_NAMES` zawiera obecnie 2 prompty: `("draft", "verify")`, wersjonowane 12-znakowym prefiksem SHA-256 (`backend/app/answering/prompts/__init__.py:12, 31-37`).
  - `backend/app/answering/prompts/draft.md:1-10` nakazuje budować każdą tezę z jednego fragmentu (`chunk_id`, `quote`) i nie zawiera instrukcji dotyczących rozbieżnych zaleceń między dokumentami.
  - `backend/app/answering/prompts/verify.md:1-9` oraz `verify_message()` (`backend/app/answering/nodes.py:226-237`) celowo przekazują weryfikatorowi wyłącznie tekst tezy i tekst jej jednego fragmentu (bez pytania i bez pozostałych pobranych fragmentów).
- **Obsługa `contradicted` w `verify`:**
  - W tej ścieżce `Verdict = Literal["supported", "contradicted", "insufficient"]` (`backend/app/answering/schemas.py:11`), przy czym `supported_claims()` zwraca wyłącznie tezy z `verdict == "supported"` (`backend/app/answering/nodes.py:134-145`).
  - W `_after_verify()` (`backend/app/answering/graph.py:41-44`), jeśli co najmniej 1 teza jest `supported`, węzeł `compose` buduje `AnsweredResult`, a tezy `contradicted` zwiększają wyłącznie `omitted_claims` (`nodes.py:162-209`). Jeśli 0 tez jest `supported`, węzeł `abstain` zwraca `AbstainedResult(reason="none_supported")` (`nodes.py:320-339`).
- **Kontrakt wyniku i API:**
  - `AnswerResult = AnsweredResult | AbstainedResult` (`backend/app/answering/schemas.py:80-95`).
  - `POST /api/answers` (`backend/app/api/answers.py:165-322`) emituje zdarzenia SSE `StageEvent` (6 dozwolonych wartości `stage`: `"retrieve" | "draft" | "quote_check" | "verify" | "compose" | "abstain"`, `answers.py:81-86`), `ResultEvent(answer_id, outcome)` (`outcome: Literal["answered", "abstained"]`, `answers.py:89-93`) oraz `ErrorEvent` (`answers.py:96-101`).
  - `GET /api/answers/{answer_id}` zwraca `AnswerRecord` z `outcome: Literal["answered", "abstained", "failed"]` i dyskryminowaną unią `result: Annotated[AnswerResult, Field(discriminator="outcome")] | None` (`backend/app/api/answers.py:104-114`).
  - Tabela `answers` ma ograniczenie `CHECK (outcome IN ('answered', 'abstained', 'failed'))` i kolumnę `result jsonb`, bez kluczy obcych do `snapshots`/`documents`/`chunks` (`backend/migrations/0002_answers.sql:1-19`).
- **Metadane dokumentów w API:** we wszystkich bieżących schematach (`Citation` `answering/schemas.py:60-68`, `CheckedChunk` `:71-77`, `EvidenceWindow` `retrieval.py:95-110`, `DocumentText` `retrieval.py:119-125`) dokument identyfikowany jest przez `doc_id` i `title` (plus `headings` dla fragmentu). Brak pól na oznaczenie dokumentu syntetycznego, datę dokumentu czy wersję produktu.
- **Budżet czasu i testy:** `Settings` definiuje `chat_timeout_s = 12` i `answer_deadline_s = 25` (`backend/app/settings.py:32-33`), a test `test_full_answer` weryfikuje dokładnie 2 wywołania modelu (`DraftOutput`, `VerifyOutput`) dla standardowej ścieżki odpowiedzi (`backend/tests/answering/test_graph.py:114-117`).

### 2. Baza danych, import TechQA i izolacja dokumentów syntetycznych (`backend/migrations/`, `backend/app/techqa/`, `backend/app/retrieval.py`)

- **Schemat tabel i migracje:**
  - `0001_techqa_schema.sql:6-64` tworzy tabele `snapshots`, `documents`, `chunk_sets`, `chunks` (z indeksem BM25 ParadeDB `chunks_search_idx` na `(id, chunk_set_id, text)`).
  - Runner migracji sprawdza SHA-256 zastosowanych plików SQL (`backend/app/migrations.py:56-61`), więc istniejących plików `0001_techqa_schema.sql` i `0002_answers.sql` nie wolno modyfikować; wszelkie zmiany schematu wymagają nowej migracji `0003_*.sql`.
- **Brak metadanych daty/wersji w TechQA:**
  - `parse_document()` (`backend/app/techqa/parse.py:16-28`) wyciąga z plików TXT wyłącznie `Title:` i treść po `\n\nText:\n`.
  - Potwierdzają to dokumenty źródłowe: TechQA ma jedną migawkę bez historii wersji (`docs/raport-techqa.md:7-12, 51`), a datę/wersję należy zapisywać wyłącznie wtedy, gdy są znane, bez wymyślania wersji dla dokumentów TechQA (`docs/zalozenia-projektu.md:38, 43`).
- **Kolizje przy dopisywaniu dokumentów syntetycznych do migawki TechQA:**
  1. `import_snapshot()` sprawdza `revision.txt`, SHA-256 archiwów z `manifest.json` i dokładną liczbę `expected_documents = 28481` (`backend/app/techqa/importer.py:112-130, 290-294`).
  2. Ponowny `import_snapshot()` wykonuje w jednej transakcji `DELETE` na wszystkich `chunks`, `chunk_sets`, `documents` i `snapshots` dla `manifest.snapshot_id` (`importer.py:328-339`) — każdy dokument syntetyczny dopisany do tego samego `snapshot_id` zostanie usunięty przy reimporcie.
  3. `_state_hash()` (`importer.py:246-275`) haszuje wszystkie wiersze `documents` dla `snapshot_id` i `chunks` dla `chunk_set_id`. Dopisanie dokumentu syntetycznego do tego samego `chunk_set_id` albo unieważni zapisane `state_sha256`/`chunk_count`, albo spowoduje zgłoszenie `comparison = "różny"` przy kolejnym `import-techqa` (naruszenie idempotentności w `backend/tests/techqa/test_importer.py:70-82`).
  4. `BM25_WHERE` (`backend/app/techqa/search.py:13`) filtruje wyłącznie po `chunk_set_id`, a `get_corpus_info()` (`backend/app/retrieval.py:67-74`) zlicza wszystkie dokumenty i fragmenty w migawce/zestawie.
  5. **Wpływ na S-06:** ewaluacja S-06 (`backend/app/evals/runner.py:455, 516-529`) używa domyślnego `settings.effective_chunk_set_id()` (`techqa@<rev>/sections-v1`). Jeśli dokumenty syntetyczne znajdą się w tym samym `chunk_set_id` bez filtra lub osobnego zestawu, mogą wpływać na statystyki BM25 (IDF) i trafiać do wyników wyszukiwania S-06.

### 3. Frontend: Asystent, ekran 4 (`S4.dc.html`), kopiowanie (`FR-019`) i responsywność (`390 px`)

- **Komponenty i routing Asystenta:**
  - Trasy: `/` (`frontend/app/routes/assistant.tsx:20-65`) i `/odpowiedz/:id` (`frontend/app/routes/answer.tsx:44-349`) osadzone w `AppLayout` (`routes/_layout.tsx:13-50`) i `AssistantFrame` (`components/assistant/AssistantFrame.tsx:9-48`).
  - `AnswerScreen` (`routes/answer.tsx:78-80, 284-327`) rozróżnia obecnie wyłącznie `answered` (`AnswerView`) i `abstained` (`AbstentionView`), z fallbackiem `ErrorState` dla `failed`.
  - `PanelFrame` (`components/assistant/PanelFrame.tsx:25-115`) renderuje panel boczny `<aside>` od `768 px` (`WIDE_QUERY` z `lib/use-media-query.ts:4`) oraz modalny arkusz od dołu `<dialog>` poniżej `768 px`. Obsługuje obecnie jeden otwarty `EvidencePanel` naraz, z nawigacją poprz./nast. między cytatami (`routes/answer.tsx:152-190`).
  - `EvidencePanel.tsx:325` wyświetla na stałe klucz `evidence.unknownDate` zamiast danych z API.
  - `PreparationDetails.tsx:72-74` ma binarny warunek wyboru tytułu (`answered` vs `abstained`).
  - `lib/stages.ts:8-43` mapuje 6 obecnych etapów SSE na 3 kroki wizualne `ProgressCard` (`search`, `check`, `compose`); nowy etap grafu z backendu musiałby zostać dopisany do `STEP_STAGES`, aby nie był ignorowany.
- **Analiza makiety ekranu 4 (`design/mockups/canvas/S4.dc.html:26`):**
  - Pokazuje wariant neutralny: badge `A vs B`, nagłówek `Źródła podają różne zalecenia`, badge `Nierozstrzygnięte`, krótkie wyjaśnienie po angielsku, 3-kolumnową tabelę porównawczą (`A · SWG21648497` vs `B · SYN-KB-0007`: zalecana wartość, odbiorca dokumentu, data dokumentu, wersja produktu), pasek „Co możesz zrobić” (3 przyciski: `Doprecyzuj wersję WAS lub RHEL`, `Otwórz oba dokumenty`, `Skopiuj obie wersje z cytatami`) oraz 2 karty obok siebie (`A`: badge `TechQA`, `swg21648497`, cytat z `<mark>` i rozwijanym `<details>Kontekst powyżej</details>`; `B`: badge `DOKUMENT SYNTETYCZNY` z ikoną info i tooltipem, `SYN-KB-0007`, `data: 2019-03 (metadane syntetyczne)`, cytat i rozwijany kontekst).
  - **Różnica wobec wymagań PRD/roadmapy:** makieta `S4.dc.html` ilustruje tylko jeden z dwóch wymaganych stanów („różne zalecenia — nierozstrzygnięte”). PRD (`US-03`, `context/foundation/prd.md:126`) i `design/mockups/README.md:45, 54` wymagają dodatkowo stanu **„sprzeczność”** (wyłącznie przy tym samym zakresie: produkt, wersja, kontekst), prezentowanego zawsze słowem i ikoną (`✕`).
  - **Tokeny CSS (`frontend/app/app.css:4-32`):** wszystkie bieżące tokeny są neutralne lub akcentowe (`--color-accent: #c98a2c`, `--color-mark: #f7e2b5`, `--color-primary: #2f5fc4`, `--color-success: #1a6b36`). Brakuje tokenu dla stanu „sprzeczność” (np. ostrzegawczego/czerwonego tła i tekstu) oraz ikony sprzeczności w `Icon.tsx:3-94`.
  - **Responsywność `390 px`:** dla ekranu 4 nie ma osobnej makiety `4N` (`design/mockups/README.md:56`), ale PRD (`prd.md:222`) wymaga czytelności i użyteczności przy `390 px` bez poziomego przewijania. Układ z `S4.dc.html` (karty obok siebie + 3-kolumnowa tabela z `white-space:nowrap`) wymaga przestawienia kart na kolumnę (`flex-col md:flex-row`) i responsywnego układu tabeli porównawczej.
- **Kopiowanie z cytatami (`FR-019`) i testy:**
  - `frontend/app/lib/copy-answer.ts:10-37` (`formatAnswerForCopy`) przyjmuje wyłącznie `AnsweredResult` i generuje `text/plain` z `[n]` przy tezach, sekcją źródeł `[n] doc_id — title` i linią migawki. Pokryte przez 6 testów jednostkowych w `frontend/app/lib/copy-answer.test.ts:1-106` (Vitest, `environment: "node"`).
  - Hook `useCopy` (`components/assistant/useCopy.ts:6-30`) i wzorzec `role="status"` (`AnswerView.tsx:161-167`) są gotowe do bezpośredniego reużycia w widoku konfliktu.
- **i18n i Playwright:**
  - `frontend/app/i18n/pl.ts:2-163` (`as const`) + `frontend/app/i18n/en.ts:4-161` (`Record<TranslationKey, string>`) gwarantują kompletność tłumaczeń podczas `npm run typecheck`.
  - W repozytorium nie ma skonfigurowanego Playwrighta (`frontend/package.json:1-40` nie zawiera `@playwright/test`, brak `playwright.config.ts` i `frontend/e2e/`).

### 4. Infrastruktura ewaluacji i Langfuse (`backend/app/evals/`, `backend/app/cli.py`, `docs/przeplyw-danych.md`)

- **Gotowe klocki do reużycia w Sprawdzianie 2b:**
  - Reprodukowalność: `get_chunk_set_repro_info()` (`backend/app/retrieval.py:279-295`), wzorzec kanonicznego hasha `compute_config_sha256()` (`backend/app/evals/runner.py:86-119`), wersjonowanie promptów 12-znakowym SHA-256 (`backend/app/evals/prompts/__init__.py:31-37`).
  - Obserwowalność i Langfuse 5.2.0: `ensure_langfuse_ready()` (`runner.py:220-240`), `flush_traces()`, `run_config()` (`observability.py:31-93`), wywołanie `client._run_experiment_async(...)` z `RUN_EXPERIMENT_ASYNC_KWARGS` (`langfuse_eval.py:21-32, 274-285`) i `asyncio.run(..., loop_factory=asyncio.SelectorEventLoop)` na Windows (`cli.py:295`).
  - Metryki i raport: `check_citation_invariants()` (`metrics.py:129-206`, baza do sprawdzenia inwariantów cytatów po obu stronach), `_percentile()` (`metrics.py:310-323`), `TokenUsage` i `_extract_token_usage()` (`metrics.py:56-63`, `runner.py:243-262`), `_build_confusion_matrix()` (`agreement.py:54-66`), `write_raw_run()` i układ raportu Markdown (`report.py:38-41, 271-473`) oraz bramka kosztu `--yes` / `--no-langfuse` (`cli.py:462-513`).
- **Sprzężenia wymagające uwagi:**
  - `backend/app/evals/runner.py:343-357` i `backend/app/evals/metrics.py:19, 259, 340-362` obsługują wyłącznie `Literal["answered", "abstained", "failed"]` i robią `assert isinstance(result, AnsweredResult)`. Jeśli graf S-07 wprowadzi nowy wariant wyniku, `runner.py` (S-06) musi go jawnie obsłużyć.
  - `backend/app/evals/langfuse_eval.py:12-18, 44-102, 165-272` jest otypowany bezpośrednio pod `EvalItem` / `EvalItemExecution` / `RunSummary` z S-06 — dla Sprawdzianu 2b wymaga albo uogólnienia (generyczne callbacki ewaluatorów), albo dedykowanego adaptera dla nowego datasetu w Langfuse Cloud.
- **Zasady danych i `docs/przeplyw-danych.md`:**
  - `docs/przeplyw-danych.md:39` i ustalenie F1 z przeglądu S-06 zakazują commitowania surowych tekstów TechQA w plikach ewaluacyjnych i raportach w gicie (w gicie tylko ID, etykiety, notatki, hashe i zagregowane metryki). Własne, napisane na potrzeby projektu dokumenty syntetyczne (jak `SYN-KB-0007`) nie są tekstami TechQA, natomiast pary z `swg21648497` nadal muszą cytować TechQA wyłącznie przez ID lub na lokalnym dysku/bazie.
  - Nowe kroki/prompty LLM w grafie i nowy dataset ewaluacyjny w Langfuse Cloud trzeba będzie dopisać do `docs/przeplyw-danych.md`.

### 5. Wzorce z AI Devs 4 (`01_01_grounding`) i dane referencyjne (`swg21648497`)

- **`01_01_grounding` (`D:\Firma\second-brain\super-brain\AI_DEVS_4\4th-devs\01_01_grounding\`):**
  - 4-etapowy potok CLI w Node.js (`EXTRACT -> DEDUPE -> SEARCH -> GROUND`, `app.js:27-61`) używający `web_search` (`src/pipeline/search.js:14-58`) do adnotacji tekstu Markdown tooltipami HTML (`src/pipeline/ground.js:21-87`).
  - Nie zawiera porównania tezy z dowodem, werdyktów ani wykrywania sprzeczności między źródłami (`src/schemas/search.js:9-40`, `src/schemas/ground.js:8-15`). Do przeniesienia nadają się jedynie ogólne wzorce już stosowane w S-02: ścisłe schematy wyjścia (`strict: true`) i wymóg dosłownych cytatów ze źródła.
- **Prawdziwy dokument bazowy `swg21648497`:**
  - Zbadany w `docs/pilotaz-audytu-techqa.md:25-28, 54-57, 89`: `swg21648497.txt` (`TRAIN_Q012`) zaleca `ulimit -u` / `nproc` = `131072` dla WebSphere Application Server na Linuksie. W całym korpusie TechQA wzorzec `131072.*nproc|nproc.*131072` występuje wyłącznie w tym jednym pliku (`pilotaz-audytu-techqa.md:89`), co czyni go czystym punktem odniesienia dla syntetycznej pary z `SYN-KB-0007` (`1024`).

---

## Code References

- `backend/app/answering/graph.py:41-73` — topologia grafu odpowiedzi i binarne rozgałęzienie `_after_verify` (`compose` vs `abstain`).
- `backend/app/answering/nodes.py:55-66, 134-145, 226-237` — `AnswerState`, odrzucanie `contradicted` w `supported_claims()`, izolacja pojedynczej tezy w `verify_message()`.
- `backend/app/answering/schemas.py:11-95` — `Verdict`, `DraftOutput`, `VerifyOutput`, `Citation`, `AnsweredResult`, `AbstainedResult`, `AnswerResult`.
- `backend/app/api/answers.py:81-114, 165-349` — kontrakty SSE (`StageEvent`, `ResultEvent`), `AnswerRecord` i zapis w tabeli `answers`.
- `backend/migrations/0001_techqa_schema.sql:6-64` — schemat tabel `snapshots`, `documents`, `chunk_sets`, `chunks` i indeksu BM25.
- `backend/migrations/0002_answers.sql:4-19` — tabela `answers` z `CHECK (outcome IN ('answered', 'abstained', 'failed'))`.
- `backend/app/techqa/importer.py:246-275, 290-294, 328-339` — `_state_hash()`, walidacja `expected_documents = 28481`, destrukcyjny reimport migawki.
- `backend/app/techqa/search.py:13` — filtr `BM25_WHERE` po `chunk_set_id`.
- `backend/app/retrieval.py:67-135, 279-295` — `CorpusInfo`, `EvidenceWindow`, `DocumentText`, `get_chunk_set_repro_info()`.
- `backend/app/evals/runner.py:86-119, 343-357, 455` — `compute_config_sha256()`, `assert isinstance(result, AnsweredResult)`, użycie domyślnego `chunk_set_id`.
- `backend/app/evals/langfuse_eval.py:21-32, 109-293` — integracja Langfuse 5.2.0 (`_run_experiment_async`, synchronizacja datasetu).
- `backend/app/evals/metrics.py:19, 129-206` — `ExecutionOutcome`, `check_citation_invariants()`.
- `frontend/app/routes/answer.tsx:78-80, 152-190, 284-327` — obsługa `answered`/`abstained` i nawigacja w `EvidencePanel`.
- `frontend/app/components/assistant/EvidencePanel.tsx:325` — wpisany na stałe klucz `evidence.unknownDate`.
- `frontend/app/components/assistant/PreparationDetails.tsx:72-74` — binarny tytuł dla `answered` vs `abstained`.
- `frontend/app/components/assistant/PanelFrame.tsx:25-115` — panel boczny (`>= 768 px`) i arkusz `<dialog>` (`< 768 px`).
- `frontend/app/lib/copy-answer.ts:10-37` i `frontend/app/lib/copy-answer.test.ts:1-106` — formatowanie odpowiedzi do schowka i 6 testów Vitest.
- `frontend/app/lib/stages.ts:8-43` — mapowanie zdarzeń SSE na 3 kroki `ProgressCard`.
- `frontend/app/app.css:4-32` — tokeny kolorystyczne Tailwind v4.
- `design/mockups/canvas/S4.dc.html:26` — makieta ekranu 4 (`4 Sprzeczne źródła`).

---

## Architecture Insights

1. **Dwa poziomy weryfikacji w S-02 pozostają wartością do zachowania:** deterministyczny `quote_check` (gwarantujący dosłowny cytat i poprawne offsety w oryginalnym fragmencie) oraz `verify` z `reasoning` przed werdyktem (`strict=True`) sprawdziły się w S-06 (`citation_invariants_pass_rate = 100.0%`, `citation_support_claim_rate = 97.4%` na `test`, `n=114`, `2026-11-25-abstention-evaluation/eval-report.md:20-25`). Rozszerzenie o S-07 powinno chronić ten inwariant dla **obu** stron konfliktu (każda strona musi przejść przez dosłowny `quote_check` i weryfikację wsparcia).
2. **Wykrywanie konfliktu wymaga widoku między dokumentami:** w przeciwieństwie do obecnego `verify` (1 teza vs 1 fragment), porównanie zaleceń i zakresu (produkt, wersja, kontekst) między dwoma dokumentami musi mieć dostęp do pytania oraz co najmniej kandydatów/tez z różnych `doc_id` (oraz metadanych dokumentu, jeśli są znane).
3. **Naruszenie czystego `chunk_set_id` TechQA byłoby kosztowne:** cały potok S-01 (idempotentny import z `state_sha256`) i S-06 (baseline abstencji na `techqa@<rev>/sections-v1`) opiera się na niezmienności migawki TechQA. Warstwa dokumentów syntetycznych powinna być zaprojektowana tak, aby dało się ją włączać/wyłączać deterministycznie i bez niszczenia `state_sha256` czystego importu TechQA (np. osobna tabela/kolumna `is_synthetic` + jawny tryb/filtr lub osobny nakładkowy `chunk_set` dla demo i Sprawdzianu 2b).
4. **Spójność kontraktu OpenAPI i i18n:** każda zmiana schematów Pydantic w `backend/app/answering/schemas.py`, `backend/app/retrieval.py` lub `backend/app/api/answers.py` wymaga regeneracji `backend/openapi.json` (`scripts/export_openapi.py`) i `frontend/app/api/schema.d.ts` (`npm run api:types`), a nowe teksty UI muszą trafić jednocześnie do `pl.ts` i `en.ts`.

---

## Historical Context (from prior changes)

- `context/archive/2026-11-23-grounded-answer-or-abstention/plan.md:71` — **Supported:** plan S-02 celowo odłożył obsługę sprzecznych źródeł i stanu „różne zalecenia” do S-07; obecny kod `nodes.py:134-145` nadal odrzuca tezy `contradicted` tak samo jak `insufficient`.
- `context/archive/2026-11-23-grounded-answer-or-abstention/plan.md:329, 335` — **Supported:** tabela `answers` (`0002_answers.sql:4-19`) nie ma kluczy obcych do `snapshots`/`documents`/`chunks` i ogranicza `outcome` do `('answered', 'abstained', 'failed')`.
- `context/archive/2026-11-23-grounded-answer-or-abstention/plan.md:31` — **Supported:** `01_01_grounding` nie zawiera fact-checkingu ani wykrywania sprzeczności (zweryfikowane bezpośrednio w `01_01_grounding/src/schemas/*.js`).
- `context/archive/2026-11-25-answer-copy-and-narrow-window/plan.md:46` — **Supported:** kopiowanie „obu wersji zaleceń” (`FR-019`) zostało celowo odłożone do S-07; `frontend/app/lib/copy-answer.ts:11` przyjmuje wyłącznie `AnsweredResult`.
- `context/archive/2026-11-25-abstention-evaluation/plan.md:37` i `eval-report.md:20-25, 50-55` — **Supported:** Sprawdzian 2b (`SYN-KB-0007`) został odłożony do S-07; zmierzony baseline S-02 na `test` (`n=114`, `n_failed=0`) ma `p50 = 1670 ms`, `p95 = 2303 ms`, więc przy budżecie `p95 < 10 s` istnieje zapas czasowy na dodatkowy krok wykrywania konfliktu (zwłaszcza jeśli uruchamiany warunkowo, gdy w grę wchodzą co najmniej 2 różne dokumenty).

---

## Related Research

- `context/archive/2026-11-23-grounded-answer-or-abstention/plan.md` (brak osobnego `research.md` w zarchiwizowanych zmianach; ustalenia techniczne i decyzje są udokumentowane w `plan.md` i `reviews/impl-review.md` zmian `S-02`, `S-05` i `S-06`).

---

## Open Questions (decyzje do rozstrzygnięcia w `/10x-plan conflicting-sources`)

1. **Strategia przechowywania i włączania dokumentów syntetycznych (PRD Open Question #3, `roadmap.md:303`):**
   - Czy dokumenty syntetyczne (w tym `SYN-KB-0007` z ekranu 4 i pozostałe przypadki Sprawdzianu 2b) powinny żyć w osobnym nakładkowym `chunk_set_id` / z jawną kolumną `is_synthetic` i metadanymi (`doc_date`, `product_version`, `audience`/`scope_note`) oraz dedykowanym poleceniem CLI (np. `import-synthetic-conflicts`), tak aby:
     - czysty `import-techqa` i ewaluacja S-06 pozostawały w 100% nienaruszone i idempotentne,
     - a jednocześnie użytkownik demo w UI mógł zadać pytanie o `nproc` dla WAS na Linuksie i zobaczyć ekran 4 z `swg21648497` vs `SYN-KB-0007`?
   - Które dokumenty syntetyczne mają być aktywne w demo UI (np. tylko wybrany przykład demo jak `SYN-KB-0007`, czy cały zestaw syntetyczny Sprawdzianu 2b)?
2. **Reprezentacja konfliktu w kontrakcie API i tabeli `answers`:**
   - Nowy wariant `outcome = "conflicting"` w `AnswerResult` (wymaga migracji `0003_*.sql` rozszerzającej `CHECK` w `answers`, aktualizacji `ResultEvent`, `AnswerRecord`, `runner.py` w S-06 oraz UI `routes/answer.tsx` i `PreparationDetails.tsx`) z podtypem stanu (`"contradiction"` vs `"different_recommendations"`), czy pole opcjonalne na `AnsweredResult`? (Osobny `outcome = "conflicting"` czyściej odzwierciedla maszynę stanów ekranów 1A / 1C / 4, ale wymaga aktualizacji S-06 `runner.py`).
3. **Architektura wykrywania konfliktu w grafie LangGraph:**
   - Czy rozbieżność wykrywa osobny węzeł po `verify` (albo równolegle/po `retrieve`, wywoływany tylko gdy wśród kandydatów/tez jest `>= 2` różnych `doc_id`), aby nie zwiększać latencji i liczby wywołań LLM dla pytań jednodokumentowych?
   - Jakie pola ma porównywać tabela kontekstu (ekran 4 pokazuje 4 wiersze: wartość/zalecenie, odbiorca dokumentu, data dokumentu, wersja produktu — czy mają być generowane strukturalnie per przypadek przez LLM z cytatami, czy stały zestaw pól z metadanymi dokumentu)?
4. **Projekt wizualny stanu „Sprzeczność” (ten sam zakres) i akcja „Otwórz oba dokumenty”:**
   - Makieta `S4.dc.html` pokazuje wariant neutralny „Źródła podają różne zalecenia / Nierozstrzygnięte”. W planie trzeba określić dokładny styl wariantu „Sprzeczność” (ikona `✕` + słowo + nowy token koloru w `app.css`) oraz zachowanie przycisku „Otwórz oba dokumenty” w `PanelFrame` (np. otwarcie `EvidencePanel` na cytacie A z nawigacją `1 / 2` do B, czy inny układ).
5. **Rozmiar i skład zestawu syntetycznego dla Sprawdzianu 2b:**
   - Ile przypadków testowych i w jakich kategoriach (np. `contradiction` — ten sam produkt/wersja/kontekst; `different_recommendations` — różny zakres/wersja/nieznane metadane; przypadki kontrolne `answered` bez konfliktu z tymi samymi dokumentami), oraz czy w ewaluacji S-07 reużywamy wyłącznie metryk deterministycznych (klasyfikacja stanu + macierz pomyłek + obecność cytatów z obu stron + inwarianty cytatów), czy także sędziego LLM.
