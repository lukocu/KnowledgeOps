# Ewaluacja abstencji i odpowiedzi (S-06) — Plan implementacji

## Overview

Budujemy odtwarzalne narzędzie CLI dla operatora do ewaluacji odpowiedzi i abstencji (Sprawdzian 1b i Sprawdzian 2a z `context/foundation/prd.md` oraz etap `S-06` w `context/foundation/roadmap.md`). Pipeline odblokowuje bloker ręcznej weryfikacji etykiet `is_impossible`, eliminuje przeciek między duplikatami w `train.json` poprzez deterministyczny podział `dev`/`test` (30/70), mierzy trafność abstencji, fałszywe odmowy, wsparcie cytatów, zgodność z odpowiedzią referencyjną TechQA, opóźnienia (`p50`/`p95`) oraz liczbę błędów (`failed`), zapisuje przebiegi jako eksperymenty w Langfuse Cloud (z jawną flagą `--no-langfuse` do lokalnych prób) oraz wspiera ręczną walidację próbki ocen automatycznego sędziego.

## Current State Analysis

- **Graf odpowiedzi (`S-02`):** `backend/app/answering/graph.py:47-73` kompiluje graf LangGraph `retrieve → draft → quote_check → verify → compose | abstain`. Węzeł `retrieve` używa BM25 (`ANSWER_K=8`), `quote_check` weryfikuje dosłowność cytatu w kodzie Python, a `verify` ocenia każdą tezę wyłącznie względem cytowanego fragmentu (bez pytania). Graf zwraca pełny `AnswerState` (`retrieved`, `draft_claims`, `rejected`, `quoted`, `verdicts`, `outcome`, `answer`).
- **Model czatu i prompty:** `backend/app/answering/model.py:15-51` tworzy `ChatOpenAI` z `max_retries=0`, `timeout=settings.chat_timeout_s` (12 s) i obsługą `OPENAI_BASE_URL` (domyślnie Gemini `gemini-3.5-flash-lite`, `CHAT_REASONING_EFFORT=low`). Prompty (`draft.md`, `verify.md`) są wersjonowane 12-znakowym prefiksem SHA-256 (`backend/app/answering/prompts/__init__.py:31-37`).
- **CLI i obserwacja:** `backend/app/cli.py:95-140` udostępnia synchroniczne polecenia `migrate`, `import-techqa`, `search`. `backend/app/observability.py:59-82` podpina wyłącznie `CallbackHandler` Langfuse (`langfuse==5.2.0`) i nie zapisuje `chat_reasoning_effort`, `snapshot_id`, `config_sha256` ani `state_sha256` w metadanych. Brak jakiegokolwiek modułu ewaluacji, datasetów i ocen (`Evaluation`) w Langfuse.
- **Dane TechQA (`train.json`):** `data/raw/techqa/train.json` zawiera 910 rekordów (`610` `is_impossible=false`, `300` `is_impossible=true`), ale S-01 jedynie waliduje w nim nazwy plików i nie zapisuje pytań w bazie. Po przycięciu białych znaków występuje **20 grup identycznych pytań**, w tym **6 par ze sprzecznymi flagami `is_impossible`** (`TRAIN_Q138`/`DEV_Q298`, `TRAIN_Q156`/`DEV_Q195`, `TRAIN_Q210`/`DEV_Q189`, `TRAIN_Q238`/`DEV_Q082`, `TRAIN_Q248`/`DEV_Q276`, `TRAIN_Q333`/`DEV_Q228`). Brak kontekstu przy `is_impossible=true` nie dowodzi braku odpowiedzi w 28 478 kanonicznych dokumentach.

## Desired End State

Po zakończeniu wszystkich 5 faz:
1. W repozytorium istnieje zamrożony, zweryfikowany ręcznie plik etykiet `backend/evals/abstention-dataset.json` (tylko ID, split `dev`/`test`, zweryfikowana etykieta i notatka — bez kopiowania treści TechQA), zawierający co najmniej **50 zweryfikowanych pytań bez odpowiedzi** i **50 pytań z odpowiedzią**, z wykluczonymi 6 konfliktami `is_impossible` i bez przecieku identycznych pytań ani pokrewnych `doc_id` między `dev` i `test`.
2. Operator ma cztery udokumentowane polecenia w `python -m app.cli`:
   - `eval-prepare-abstention` — eksport kandydatów z `train.json` + top-10 trafień BM25 do `data/evals/` na potrzeby ręcznej weryfikacji etykiet,
   - `eval-freeze-abstention` — walidacja uzupełnionych etykiet i zapis zamrożonego `backend/evals/abstention-dataset.json` (bez treści TechQA),
   - `eval-abstention` — uruchomienie ewaluacji na `--split dev|test|all` z metrykami deterministycznymi, niezależnym sędzią LLM, zapisem eksperymentu w Langfuse Cloud (lub `--no-langfuse` z ostrzeżeniem), eksportem surowych wyników i próbki do kontroli ręcznej w `data/evals/` oraz raportem Markdown,
   - `eval-judge-agreement` — wyliczenie zgodności sędzia–człowiek (% zgodności i Cohen's kappa) z uzupełnionego arkusza ręcznego przeglądu i dopisanie wyników walidacji do raportu.
3. Opublikowany raport bazowy w `context/changes/abstention-evaluation/eval-report.md` zawiera wyniki Sprawdzianu 1b i Sprawdzianu 2a na zamrożonym splicie `test` z liczebnością próby (`n`), liczbą błędów (`n_failed`), opóźnieniem `p50`/`p95`, ograniczeniami, hashami migawki i konfiguracji, wynikiem ręcznej walidacji sędziego oraz identyfikatorem/linkiem przebiegu w Langfuse Cloud.

### Key Discoveries:

- `langfuse==5.2.0` (`backend/uv.lock:780-781`) udostępnia `create_dataset`, `create_dataset_item`, `get_dataset`, `DatasetClient.run_experiment(...)` oraz `langfuse.experiment.Evaluation` i `ExperimentResult(experiment_id, experiment_url, format)` (`dataset_run_id`/`dataset_run_url` to deprecated aliasy) — wzorzec przeniesiony z AI Devs 4 (`03_01_evals/experiments/response-correctness.ts`).
- `backend/tests/conftest.py:21-26` potwierdza, że na Windows `psycopg` async wymaga `asyncio.SelectorEventLoop` (domyślny `ProactorEventLoop` kończy się błędem).
- `backend/app/retrieval.py:242-258` (`get_corpus_info`) nie zwraca jeszcze `config_sha256` ani `state_sha256` z tabeli `chunk_sets` (`backend/migrations/0001_techqa_schema.sql:27-36`) — potrzebne będzie lekkie zapytanie odczytujące te hashe dla raportu odtwarzalności.
- `backend/app/answering/schemas.py:88-92` (`AbstainedResult`) łączy przypadki odrzucenia przez `quote_check` i przez `verify` pod jednym `reason="none_supported"`; szczegółowy podział jest dostępny w `AnswerState` (`rejected`, `verdicts`) zwracanym bezpośrednio przez graf.
- `backend/app/answering/model.py:15-51` ma `max_retries=0` i limit `chat_timeout_s=12`, a `answer_deadline_s=25` jest egzekwowane dopiero w `backend/app/api/answers.py:241-244` — runner ewaluacji musi sam egzekwować `answer_deadline_s` wokół wywołania grafu.

## What We're NOT Doing

- **Bez zmian w promptach (`draft.md`, `verify.md`) ani w grafie odpowiedzi S-02:** S-06 dostarcza czysty pomiar bazowy; ewentualne strojenie trafi do osobnej zmiany.
- **Bez nowych migracji PostgreSQL:** rejestr eksperymentów i ocen żyje w Langfuse Cloud, zamrożone etykiety w `backend/evals/abstention-dataset.json`, a robocze eksporty w `data/evals/` (poza git).
- **Bez ewaluacji sprzecznych źródeł (Sprawdzian 2b / `SYN-KB-0007`):** to zakres etapu `S-07`.
- **Bez porównania retrieval BM25 vs wektory vs hybryda (Sprawdzian 1a):** to zakres etapu `S-04` (choć nasz podział `dev`/`test` po grupowaniu pytań i `doc_id` będzie możliwy do ponownego użycia w `S-04`).
- **Bez automatycznych cichych retry w runnerze ewaluacji:** błędy dostawcy/timeouty są raportowane jawnie jako `failed`.
- **Bez kopiowania treści TechQA do repozytorium:** w git zapisujemy wyłącznie ID pytań, split, zweryfikowane etykiety, krótkie notatki recenzenta i zagregowane raporty.

## Implementation Approach

Dodajemy nowy, niezależny pakiet `backend/app/evals/` podpięty do istniejącego `backend/app/cli.py`. Logika dzielona jest na cztery czyste warstwy:
1. **Dane i podział (`dataset.py`, `prepare.py`):** deterministyczne parsowanie `train.json` (z weryfikacją SHA-256 przeciwko `manifest.json`), grupowanie duplikatów pytań i kanonicznych `doc_id` (z wykluczeniem 6 konfliktów `is_impossible`), stratyfikowany podział 30/70 na `dev`/`test` (stały seed) oraz eksport kandydatów z top-10 BM25 do ręcznej weryfikacji.
2. **Ewaluatory (`metrics.py`, `judge.py`, `prompts/`):** czyste funkcje metryk deterministycznych (abstencja, fałszywe odmowy, inwarianty cytatów, wykluczenie `failed` z mianowników jakości, percentyle opóźnień `p50`/`p95`) oraz niezależny sędzia LLM przez `langchain-openai` (`with_structured_output(..., strict=True)`, uzasadnienie przed werdyktem) korzystający z `EVAL_JUDGE_MODEL` (lub jawnego fallbacku na `CHAT_MODEL`).
3. **Runner i raportowanie (`runner.py`, `langfuse_eval.py`, `report.py`):** wspólna funkcja wykonująca graf S-02 z limitem `answer_deadline_s` i zbierająca `AnswerState` + czas + tokeny/koszt (jeśli zwracane przez provider), podpięta pod natywny `Langfuse.run_experiment` (z synchronizacją datasetu po deterministycznym ID elementu) albo pod lokalny `asyncio.Semaphore(concurrency)` przy `--no-langfuse`.
4. **Walidacja ręczna sędziego (`sampling.py`, `agreement.py`):** deterministyczne stratyfikowane próbkowanie wyników przebiegu (min. 20 przypadków lub 25% odpowiedzi) do arkusza w `data/evals/` oraz obliczanie % zgodności i współczynnika Cohen's kappa po uzupełnieniu ocen przez człowieka.

## Critical Implementation Details

- **Timing & lifecycle (Windows `SelectorEventLoop` + `Langfuse.run_experiment`):** `psycopg` `AsyncConnectionPool` na Windows wymaga `asyncio.SelectorEventLoop`, natomiast `Langfuse.run_experiment(...)` w SDK 5.2.0 wywołuje wewnętrznie `run_async_safely(self._run_experiment_async(...))`, które przy już aktywnej pętli może uruchomić wątek z osobną domyślną pętlą (`ProactorEventLoop`). W `langfuse_eval.py` wywołuj `await client._run_experiment_async(...)` albo otwieraj `AsyncConnectionPool` wewnątrz korutyny uruchamianej przez `asyncio.run(..., loop_factory=asyncio.SelectorEventLoop)` i zweryfikuj testem integracyjnym na Windows, że pula połączeń i eksperyment dzielą tę samą pętlę `SelectorEventLoop` (bez `RuntimeError: ProactorEventLoop is not supported`).
- **State sequencing (wykluczenie `failed` z mianowników):** Przypadki, w których graf odpowiedzi lub sędzia zgłosił timeout/błąd dostawcy, otrzymują status `failed` (odpowiedź) lub `judge_failed` (ocena sędziego) i **nigdy** nie zwiększają licznika ani mianownika trafności abstencji, fałszywych odmów ani `p50`/`p95` poprawnych odpowiedzi. Każdy raport i ocena run-level w Langfuse podaje jawnie `n_total`, `n_evaluated` i `n_failed`.
- **Data integrity (grupowanie przed podziałem `dev`/`test`):** Klucz grupowania pytań to `question.strip()` (ujawnia 20 grup duplikatów i 6 konfliktów `is_impossible`). Przed przypisaniem splitu `dev`/`test` pytania z odpowiedzią grupujemy ponadto według `canonical_doc_id` (mapując nazwy plików z `contexts[].filename` przez `documents.canonical_doc_id` lub bazowy `doc_id`), aby dwa pytania odwołujące się do tego samego dokumentu nigdy nie trafiły do różnych splitów.

---

## Phase 1: Zbiór ewaluacyjny, deduplikacja i eksport kandydatów

### Overview
Budujemy deterministyczną warstwę danych dla `train.json`: walidację manifestu, wykrywanie duplikatów i konfliktów `is_impossible`, podział `dev`/`test` bez przecieku, polecenie CLI `eval-prepare-abstention` (eksport kandydatów + top-10 BM25 do `data/evals/`) oraz loader/walidator zamrożonego pliku etykiet `backend/evals/abstention-dataset.json`.

### Changes Required:

#### 1. Moduł ładowania, grupowania i podziału TechQA
**File**: `backend/app/evals/__init__.py` (nowy), `backend/app/evals/dataset.py` (nowy)

**Intent**: Wczytać `train.json` z walidacją SHA-256 przeciwko `manifest.json`, pogrupować identyczne pytania (wykluczając konflikty `is_impossible`) oraz pytania współdzielące `canonical_doc_id`, a następnie przypisać deterministyczny podział `dev`/`test` (30/70) i zdefiniować kontrakt zamrożonego pliku etykiet.

**Contract**:
- `TechQARecord`, `VerifiedLabel = Literal["verified_unanswerable", "answerable_in_corpus", "ambiguous"]`, `Split = Literal["dev", "test"]`, `EvalItem` (Pydantic).
- `load_techqa_records(techqa_dir: Path) -> list[TechQARecord]`: weryfikuje SHA-256 `train.json` względem `load_manifest()`.
- `deduplicate_and_filter(records: list[TechQARecord]) -> tuple[list[TechQARecord], list[ConflictGroup]]`: grupuje po `question.strip()`, wyklucza grupy ze sprzecznymi `is_impossible` (6 grup w migawce bazowej), z pozostałych grup duplikatów wybiera stabilnie rekord o najmniejszym `id`.
- `assign_splits(records: list[TechQARecord], *, canonical_doc_map: Mapping[str, str] | None = None, dev_ratio: float = 0.3, seed: int = 20261125) -> dict[str, Split]`: grupuje rekordy z odpowiedzią według `canonical_doc_id` (rozwiązywanego przez `canonical_doc_map` z fallbackiem na `doc_id` kontekstu — każda grupa w całości trafia do `dev` albo `test`), osobno stratyfikuje `is_impossible=True` i `is_impossible=False`.
- `load_verified_dataset(labels_path: Path, techqa_dir: Path, *, split: Literal["dev", "test", "all"] = "all") -> list[EvalItem]`: wczytuje `backend/evals/abstention-dataset.json`, sprawdza brak duplikatów `question_id`, brak przecieku `canonical_doc_id` między `dev` i `test`, spójność z `train.json` i wyklucza rekordy `ambiguous` z listy aktywnych pytań ewaluacyjnych (zwracając ich liczbę w metadanych do raportu).
- Schemat `backend/evals/abstention-dataset.json` (bez tekstu pytań/dokumentów z TechQA):
```json
{
  "schema_version": 1,
  "snapshot_id": "techqa@0b5bbc84b7f07d6d09d063130e90b716d8d4a32a",
  "train_json_sha256": "69d97231509482ed6bd5ec1c4bc0607acb82a88d11169eb8383592d0ca8b93c7",
  "split_seed": 20261125,
  "dev_ratio": 0.3,
  "excluded_conflict_ids": ["TRAIN_Q138", "DEV_Q298", "..."],
  "items": [
    {
      "question_id": "TRAIN_Q002",
      "split": "test",
      "original_is_impossible": true,
      "canonical_doc_id": null,
      "verified_label": "verified_unanswerable",
      "reviewer_note": "Top-10 BM25 dotyczy innych przyczyn kodu 2189.",
      "reviewed_at": "2026-11-25"
    }
  ]
}
```

#### 2. Eksport kandydatów z top-10 BM25 do ręcznej weryfikacji
**File**: `backend/app/evals/prepare.py` (nowy)

**Intent**: Wybrać deterministyczną pulę kandydatów (`is_impossible=true` oraz `is_impossible=false`) z obu splitów `dev`/`test` (proporcjonalnie 30/70 po deterministycznym sortowaniu po `question_id`), pobrać z `documents` mapowanie `doc_id -> canonical_doc_id` oraz dla kandydatów `is_impossible=true` top-10 trafień BM25 z bazy (tytuł, `doc_id`, wynik, krótki fragment) i zapisać dwa pliki w `data/evals/`: czytelny przewodnik przeglądu Markdown oraz szablon JSON gotowy do uzupełnienia etykiet `verified_label` i zamrożenia jako `backend/evals/abstention-dataset.json`.

**Contract**:
- `prepare_abstention_candidates(conn, *, techqa_dir: Path, chunk_set_id: str, out_dir: Path, unanswerable_candidates: int = 80, answerable_candidates: int = 60, top_k: int = 10, seed: int = 20261125) -> PrepareReport`: pobiera `canonical_doc_map` jednym zapytaniem z `documents(doc_id, canonical_doc_id)` dla aktywnego `snapshot_id`, wywołuje `assign_splits(..., canonical_doc_map=canonical_doc_map)` i dobiera kandydatów stratyfikowanie proporcjonalnie 30/70 (`dev`/`test`) po deterministycznym sortowaniu `question_id`.
- Zapisuje `<out_dir>/abstention-candidates-review.md` (pytanie + tabela top-10 BM25 z `doc_id`, tytułem i fragmentem dla każdego kandydata `is_impossible=true`) oraz `<out_dir>/abstention-labels-template.json` (z `canonical_doc_id` dla pytań z odpowiedzią, pustym `verified_label: null` dla `is_impossible=true` do wypełnienia ręcznego i `verified_label: "answerable_in_corpus"` dla rekordów `is_impossible=false` z potwierdzonym dokumentem kontekstowym).
- Funkcja `validate_and_freeze_labels(template_path: Path, target_path: Path, techqa_dir: Path) -> FreezeSummary`: sprawdza, że wszystkie niepominięte rekordy mają poprawną etykietę, weryfikuje offline brak przecieku `canonical_doc_id` między `dev` i `test`, liczy `verified_unanswerable` i `answerable_in_corpus` w `dev` i `test` oraz zapisuje czysty plik `backend/evals/abstention-dataset.json` (tylko ID, `canonical_doc_id`, split, etykieta, notatka, data — zero treści z TechQA).

#### 3. Podpięcie pod CLI
**File**: `backend/app/cli.py`

**Intent**: Dodać podpolecenia `eval-prepare-abstention` (eksport kandydatów z top-10 BM25) oraz `eval-freeze-abstention` (walidacja i zapis zamrożonego pliku etykiet do `backend/evals/abstention-dataset.json`).

**Contract**:
- `python -m app.cli eval-prepare-abstention [--out-dir ../data/evals] [--unanswerable 80] [--answerable 60] [--k 10] [--chunk-set ...]`
- `python -m app.cli eval-freeze-abstention --input <path> [--output evals/abstention-dataset.json]`

#### 4. Testy jednostkowe i korpusowe Fazy 1
**File**: `backend/tests/evals/test_dataset.py` (nowy), `backend/tests/evals/test_prepare.py` (nowy)

**Intent**: Zweryfikować deduplikację, wykluczanie konfliktów, brak przecieku `doc_id` i identycznych pytań między `dev`/`test`, walidację schematu `abstention-dataset.json` (w tym odrzucenie brakujących etykiet i duplikatów) oraz poprawność formatu eksportu kandydatów.

**Contract**: Testy jednostkowe na syntetycznych rekordach (bez DB i bez `TECHQA_DIR`) + test `@pytest.mark.corpus` potwierdzający na prawdziwym `train.json` dokładnie 910 rekordów, 20 grup duplikatów i 6 grup konfliktów.

### Success Criteria:

#### Automated Verification:
- Testy jednostkowe i korpusowe Fazy 1 przechodzą: `cd backend; uv run pytest tests/evals/test_dataset.py tests/evals/test_prepare.py`
- Kontrola lintera, formatu i typów przechodzi: `cd backend; uv run ruff check .; uv run ruff format --check .; uv run mypy .`
- Polecenie `python -m app.cli eval-prepare-abstention --help` i `eval-freeze-abstention --help` zwracają kod 0 z czytelnym opisem flag.

#### Manual Verification:
- Uruchomienie `eval-prepare-abstention` na lokalnej bazie generuje w `data/evals/` czytelny plik `abstention-candidates-review.md` z top-10 BM25 (sprawdzić 2–3 losowe pytania, czy układ ułatwia ocenę w minutę na przypadek).

**Implementation Note**: Po ukończeniu tej fazy i przejściu wszystkich testów automatycznych zatrzymaj się na ręczne potwierdzenie czytelności eksportu kandydatów przed przejściem do Fazy 2.

---

## Phase 2: Sędziowie automatyczni, metryki deterministyczne i testy

### Overview
Implementujemy wszystkie oceny per-item i run-level: metryki deterministyczne (trafność abstencji, fałszywe odmowy, inwarianty cytatów, podział przyczyn abstencji, osobne `n_failed`, opóźnienia `p50`/`p95`) oraz niezależnego sędziego LLM (`EVAL_JUDGE_MODEL` z jawnym fallbackiem na `CHAT_MODEL`) oceniającego wsparcie cytatów (binarne) i zgodność z odpowiedzią referencyjną TechQA (`full`/`partial`/`incorrect`).

### Changes Required:

#### 1. Konfiguracja modelu sędziego
**File**: `backend/app/settings.py`, `backend/app/answering/model.py`, `.env.example`

**Intent**: Dodać opcjonalną konfigurację modelu sędziego (`EVAL_JUDGE_MODEL`, `EVAL_JUDGE_BASE_URL`, `EVAL_JUDGE_API_KEY`, `EVAL_JUDGE_REASONING_EFFORT`) z jawnym fallbackiem na ustawienia `CHAT_*`, tak aby ograniczyć self-preference bias względem weryfikatora S-02 i jednocześnie pozwolić na uruchomienie bez dodatkowego klucza (z jawnym oznaczeniem fallbacku w raporcie).

**Contract**:
- Nowe pola w `Settings`: `eval_judge_model: str | None = None`, `eval_judge_base_url: str | None = None`, `eval_judge_api_key: SecretStr | None = None`, `eval_judge_reasoning_effort: str | None = None`, `eval_judge_timeout_s: float = 20`.
- `make_judge_model(settings: Settings) -> tuple[BaseChatModel, JudgeModelInfo]` w `backend/app/answering/model.py` (lub `backend/app/evals/judge.py` reużywające wspólnego helpera `_build_openai_chat(...)`), gdzie `JudgeModelInfo` zawiera `model: str`, `reasoning_effort: str`, `is_fallback_to_chat_model: bool`.
- Aktualizacja `.env.example` o zakomentowane zmienne `EVAL_JUDGE_*`.

#### 2. Prompty i schematy sędziego LLM
**File**: `backend/app/evals/prompts/__init__.py` (nowy), `backend/app/evals/prompts/citation_support.md` (nowy), `backend/app/evals/prompts/reference_agreement.md` (nowy), `backend/app/evals/judge.py` (nowy)

**Intent**: Zdefiniować wersjonowane (12-znakowy SHA-256, jak w S-02) prompty oraz schematy Pydantic (`reasoning` przed werdyktem, `strict=True`) dla dwóch niezależnych ocen sędziego LLM: (1) czy cytowany fragment i cytat wspierają konkretną tezę (`supported` / `unsupported`), (2) czy odpowiedź zgadza się z odpowiedzią referencyjną TechQA (`full` / `partial` / `incorrect`).

**Contract**:
- `CitationJudgeVerdict(claim_index: int, reasoning: str, verdict: Literal["supported", "unsupported"])`, `CitationJudgeOutput(verdicts: list[CitationJudgeVerdict])`.
- `ReferenceAgreementOutput(reasoning: str, verdict: Literal["full", "partial", "incorrect"])` (mapowane numerycznie w Langfuse: `full=1.0`, `partial=0.5`, `incorrect=0.0`, z komentarzem zawierającym kategorię i `reasoning`).
- `EvalJudge`: `async def judge_citations(claims, citations, chunk_texts) -> CitationJudgeResult` (wywoływane wyłącznie dla `outcome == "answered"`) oraz `async def judge_reference(question, reference_answer, claims) -> ReferenceAgreementOutput` (wywoływane wyłącznie dla `verified_label == "answerable_in_corpus"` i `outcome == "answered"`).
- Błąd/timeout sędziego nie wysypuje przebiegu — zwraca `judge_error: str` zapisywane osobno (`n_judge_failed`), bez zafałszowywania średnich ocen.

#### 3. Metryki deterministyczne i agregatory run-level
**File**: `backend/app/evals/metrics.py` (nowy)

**Intent**: Zaimplementować czyste, w pełni testowalne funkcje obliczające oceny per-item (zgodne z `langfuse.experiment.Evaluation`) oraz agregację całego przebiegu (`RunSummary`) z oddzielnym raportowaniem `n_failed`, rozbiciem przyczyn abstencji (`no_hits`, `no_claims`, `quote_check_rejected_all`, `verify_rejected_all`) i percentylami opóźnień.

**Contract**:
- `check_citation_invariants(result: AnsweredResult, chunk_texts: dict[str, str]) -> CitationInvariantCheck`: sprawdza, że każda teza ma numer cytatu `1..N`, lista cytatów jest niepusta, a dla każdego `CitationClaim` zakres `0 <= quote_start < quote_end <= len(chunk_texts[chunk_id])` jest poprawny i dosłowny wycinek `chunk_texts[chunk_id][quote_start:quote_end] == quote` (zgodnie z `compose_answer` w `backend/app/answering/nodes.py:199`).
- `score_item(item: EvalItem, run_item: EvalItemExecution) -> list[ItemScore]`:
  - dla `failed`: zwraca wyłącznie `execution_ok = 0.0` (bez ocen abstencji/fałszywej odmowy),
  - dla `verified_unanswerable`: `abstention_accuracy = 1.0 if outcome == "abstained" else 0.0`,
  - dla `answerable_in_corpus`: `false_refusal = 1.0 if outcome == "abstained" else 0.0`,
  - dla `outcome == "answered"`: `citation_invariants_ok` (`0.0`/`1.0`), `citation_support_rate` (odsetek tez z werdyktem `supported` od sędziego), `reference_agreement` (`1.0`/`0.5`/`0.0`, tylko dla `answerable_in_corpus`),
  - dla każdego nie-`failed`: `latency_ms` (oraz flaga `within_latency_budget = 1.0 if latency_ms < 10_000 else 0.0`).
- `aggregate_run(results: list[EvalItemExecution]) -> RunSummary`: liczy `n_total`, `n_evaluated`, `n_failed`, `n_unanswerable_eval`, `abstention_accuracy`, `n_answerable_eval`, `false_refusal_rate`, `citation_invariants_pass_rate`, `citation_support_claim_rate` (po wszystkich tezach) i `citation_support_answer_rate` (odpowiedzi w 100% wsparte), rozkład `reference_agreement` (`full`/`partial`/`incorrect` + średnia), `latency_p50_ms`, `latency_p95_ms`, rozbicie przyczyn abstencji oraz `n_judge_failed`.

#### 4. Testy jednostkowe Fazy 2
**File**: `backend/tests/evals/fakes.py` (nowy), `backend/tests/evals/test_metrics.py` (nowy), `backend/tests/evals/test_judge.py` (nowy)

**Intent**: Pokryć testami jednostkowymi (na dedykowanym, lekkim `FakeJudgeChatModel` obsługującym dowolny schemat w `with_structured_output(..., strict=True)` i symulację błędów/timeoutów) wszystkie przypadki brzegowe metryk i sędziego: `failed` wykluczone z mianowników, pustą listę wyników, 100% abstencji, 0% abstencji, błędy inwariantów cytatów, częściowe wsparcie cytatów, timeout sędziego oraz fallback `EVAL_JUDGE_MODEL` → `CHAT_MODEL`.

**Contract**: Wszystkie testy działają bez sieci i bez DB.

### Success Criteria:

#### Automated Verification:
- Testy jednostkowe Fazy 2 przechodzą: `cd backend; uv run pytest tests/evals/test_metrics.py tests/evals/test_judge.py`
- Wszystkie dotychczasowe testy backendu nadal przechodzą: `cd backend; uv run pytest`
- Kontrola lintera, formatu i typów przechodzi: `cd backend; uv run ruff check .; uv run ruff format --check .; uv run mypy .`

#### Manual Verification:
- Przegląd treści promptów `citation_support.md` i `reference_agreement.md` pod kątem spójności z definicją wsparcia z PRD („cytat wspiera konkretnie tę tezę, a nie tylko podobny temat”).

**Implementation Note**: Po ukończeniu tej fazy i przejściu wszystkich testów automatycznych zatrzymaj się na ręczny przegląd promptów sędziego przed przejściem do Fazy 3.

---

## Phase 3: Runner ewaluacji, Langfuse Cloud i raport Markdown

### Overview
Łączymy graf odpowiedzi S-02, sędziego i metryki w asynchroniczny runner `eval-abstention` z pełnymi hashami odtwarzalności, natywną integracją eksperymentów Langfuse 5.2.0, trybem `--no-langfuse`, zapisem surowych wyników do `data/evals/` i generatorem raportu Markdown.

### Changes Required:

#### 1. Metadane odtwarzalności z bazy i obserwacji
**File**: `backend/app/retrieval.py`, `backend/app/observability.py`, `backend/tests/answering/test_observability.py`

**Intent**: Udostępnić odczyt `config_sha256` i `state_sha256` z `chunk_sets` dla pełnej odtwarzalności raportu ewaluacyjnego, udostępnić helper `get_langfuse_client(settings)` oraz uzupełnić `run_config` w `observability.py` o `chat_reasoning_effort` (natomiast `snapshot_id`, `config_sha256` i `state_sha256` trafiają do metadanych eksperymentu w `langfuse_eval.py`, ponieważ `run_config` nie ma dostępu do DB).

**Contract**:
- `ChunkSetReproInfo(snapshot_id, revision, chunk_set_id, variant, config_sha256, state_sha256)` i `async def get_chunk_set_repro_info(conn, chunk_set_id) -> ChunkSetReproInfo` w `backend/app/retrieval.py`.
- `get_langfuse_client(settings: Settings) -> Langfuse | None` w `backend/app/observability.py` (reużywa istniejącego singletona `_client`).
- `run_config(...)` dodaje `chat_reasoning_effort` do `metadata`, wraz z odpowiadającą aktualizacją asercji słownika w `backend/tests/answering/test_observability.py`.

#### 2. Asynchroniczny runner ewaluacji i integracja z Langfuse 5.2.0
**File**: `backend/app/evals/runner.py` (nowy), `backend/app/evals/langfuse_eval.py` (nowy)

**Intent**: Wykonać graf S-02 dla każdego pytania z aktywnego splitu (egzekwując `answer_deadline_s`, mierząc `latency_ms` zegarem monotonicznym i przechwytując wyjątki jako `failed`), uruchomić sędziego dla wygenerowanych odpowiedzi, zapisać eksperyment w Langfuse Cloud (domyślnie) lub uruchomić lokalnie z `asyncio.Semaphore(concurrency)` przy `--no-langfuse`.

**Contract**:
- `EvalRunConfig`: przechowuje `split`, `limit`, `concurrency` (domyślnie `2`), `use_langfuse` (domyślnie `True`), `dataset_name` (domyślnie `knowledgeops/abstention-eval`), `run_name`, `repro_info`, `chat_model`, `chat_reasoning_effort`, `k`, `answer_prompt_versions`, `judge_model_info`, `judge_prompt_versions`, `config_sha256` (kanoniczny SHA-256 całej konfiguracji przebiegu).
- Tryb Langfuse (`use_langfuse=True`):
  - Fail-fast przed pierwszym wywołaniem LLM, jeśli brak `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` (komunikat wskazuje ustawienie kluczy lub użycie `--no-langfuse`).
  - Idempotentnie zapewnia dataset (`get_dataset` / `create_dataset`), synchronizuje aktywne elementy (`create_dataset_item` z deterministycznym `id=f"abstention_{item.split}_{item.question_id}"`, `input`, `expected_output`, `metadata`) i filtruje `dataset.items` po `id` wyłącznie do aktywnego `--split` oraz `--limit`.
  - Uruchamia eksperyment przez `await client._run_experiment_async(name=..., run_name=..., description=..., data=selected_items, task=..., evaluators=..., composite_evaluator=None, run_evaluators=..., max_concurrency=..., metadata=...)` na tej samej pętli `SelectorEventLoop` co `AsyncConnectionPool` (zabezpieczone testem kontraktu sygnatury w `test_runner.py`), rejestrując oceny per-item (`Evaluation`) i run-level (`abstention_accuracy`, `false_refusal_rate`, `citation_invariants_pass_rate`, `citation_support_claim_rate`, `reference_agreement_avg`, `latency_p95_ms`, `failed_count`), a następnie wywołuje `flush_traces()`.
  - Zwraca `langfuse_run_id = result.experiment_id` i `langfuse_run_url = result.experiment_url` (zamiast deprecated aliasów `dataset_run_id` / `dataset_run_url`).
- Tryb lokalny (`use_langfuse=False`): uruchamia tę samą funkcję `execute_item` z `asyncio.Semaphore(concurrency)` i te same ewaluatory, ustawiając `langfuse_run_id=None`.
- Bramka potwierdzenia kosztu przed startem (jak `confirmExperiment` w `03_01_evals`): wypisuje liczbę pytań, model odpowiedzi, model sędziego i szacowaną liczbę wywołań LLM; pomijana flagą `--yes`.

#### 3. Generator raportu Markdown i eksport surowego JSON
**File**: `backend/app/evals/report.py` (nowy)

**Intent**: Zapisać kompletny, odtwarzalny zapis przebiegu w `data/evals/<run_name>.json` (wszystkie itemy, odpowiedzi, cytaty, werdykty sędziego, błędy) oraz wygenerować czytelny raport Markdown (Sprawdzian 1b i 2a) z tabelami metryk, liczebnością próby, hashami odtwarzalności, ograniczeniami, sekcją analizy błędów (top błędne abstencje / fałszywe odmowy) oraz jawnym ostrzeżeniem, gdy użyto `--no-langfuse` lub fallbacku `EVAL_JUDGE_MODEL`.

**Contract**:
- `write_raw_run(path: Path, run: EvalRunArtifact) -> None`
- `render_markdown_report(run: EvalRunArtifact, *, agreement: JudgeAgreementSummary | None = None) -> str`
- Raport zawiera obowiązkowe sekcje: Metadane i odtwarzalność (w tym `langfuse_run_id`/`url` lub baner ostrzegawczy), Podsumowanie Sprawdzianu 2a (Abstencja i fałszywe odmowy), Podsumowanie Sprawdzianu 1b (Cytaty, zgodność z referencją, opóźnienie `p50`/`p95`, błędy `n_failed`), Rozbicie przyczyn abstencji, Przykłady błędów (ID pytań + diagnoza), Walidacja ręczna sędziego (placeholder do uzupełnienia w Fazie 4) oraz Ograniczenia.

#### 4. Polecenie CLI `eval-abstention` i testy Fazy 3
**File**: `backend/app/cli.py`, `backend/tests/evals/test_runner.py` (nowy), `backend/tests/evals/test_report.py` (nowy)

**Intent**: Dodać podpolecenie `eval-abstention` w `app/cli.py` (uruchamiane przez `asyncio.run(..., loop_factory=asyncio.SelectorEventLoop)`) oraz testy runnera (w tym timeout -> `failed`, `--no-langfuse`, brak kluczy Langfuse -> fail-fast, spójność metryk między trybem Langfuse i lokalnym, render raportu Markdown).

**Contract**:
- `python -m app.cli eval-abstention [--dataset evals/abstention-dataset.json] [--split dev|test|all] [--limit N] [--concurrency 2] [--out-dir ../data/evals] [--report-out <path.md>] [--no-langfuse] [--yes]`

### Success Criteria:

#### Automated Verification:
- Testy Fazy 3 (runner, Langfuse mock, raport, CLI) przechodzą: `cd backend; uv run pytest tests/evals/test_runner.py tests/evals/test_report.py`
- Testy obserwacji i całego backendu przechodzą: `cd backend; uv run pytest`
- Kontrola lintera, formatu i typów przechodzi: `cd backend; uv run ruff check .; uv run ruff format --check .; uv run mypy .`

#### Manual Verification:
- Próbne uruchomienie `eval-abstention --split dev --limit 3 --no-langfuse --yes` (na małym próbnym pliku etykiet lub tymczasowym zestawie) przechodzi na Windows przeciwko lokalnemu ParadeDB bez błędów `SelectorEventLoop` i generuje poprawny plik JSON oraz raport Markdown z ostrzeżeniem o braku Langfuse.

**Implementation Note**: Po ukończeniu tej fazy i przejściu wszystkich testów automatycznych zatrzymaj się na ręczne potwierdzenie próbnego przebiegu lokalnego przed przejściem do Fazy 4.

---

## Phase 4: Próbkowanie i walidacja ręczna ocen sędziego

### Overview
Dodajemy deterministyczne stratyfikowane próbkowanie wyników przebiegu (min. 20 przypadków lub 25% odpowiedzi) do ręcznej kontroli przez człowieka oraz polecenie `eval-judge-agreement` wyliczające zgodność sędzia–człowiek (% zgodności i współczynnik Cohen's kappa) i dopisujące sekcję walidacji do raportu.

### Changes Required:

#### 1. Stratyfikowane próbkowanie do audytu ręcznego
**File**: `backend/app/evals/sampling.py` (nowy)

**Intent**: Wybierać deterministycznie (ze stałym seedem) próbkę przypadków z `EvalRunArtifact` o rozmiarze `target = min(n_non_failed, max(20, ceil(0.25 * n_answered)))` według jawnej reguły warstwowej: najpierw do 5 odpowiedzi z odrzuconymi tezami (`answered` i `omitted_claims > 0`), następnie do 5 abstencji (`abstained`, jako przegląd jakościowy ewentualnych fałszywych odmów), a pozostały budżet z pozostałych odpowiedzi (`answered`) — i eksportować arkusz JSON + czytelny plik Markdown do `data/evals/`.

**Contract**:
- `sample_for_manual_audit(run: EvalRunArtifact, *, min_samples: int = 20, answer_fraction: float = 0.25, max_omitted_layer: int = 5, max_abstained_layer: int = 5, seed: int = 20261125) -> list[ManualAuditEntry]`
- `export_manual_audit(entries, out_dir: Path, run_name: str) -> tuple[Path, Path]`: zapisuje `<run_name>-manual-audit.json` (dla `answered`: `human_citation_supported: bool | null`, `human_reference_verdict: Literal["full", "partial", "incorrect"] | null`; dla `abstained`: `human_abstain_justified: bool | null` przy pominiętych polach sędziego; dla wszystkich: `human_note: str`) oraz `<run_name>-manual-audit.md` (pytanie, tezy, dosłowne cytaty z kontekstem fragmentu, odpowiedź referencyjna TechQA — **bez pokazywania werdyktu sędziego**, aby uniknąć efektu zakotwiczenia recenzenta!).
- Automatyczne wywołanie eksportu próbki na końcu `eval-abstention` (z wypisaniem ścieżek do plików w `data/evals/`).

#### 2. Obliczanie zgodności sędzia–człowiek i aktualizacja raportu
**File**: `backend/app/evals/agreement.py` (nowy), `backend/app/cli.py`

**Intent**: Wczytać uzupełniony przez człowieka plik `<run_name>-manual-audit.json` i odpowiadający mu surowy `<run_name>.json`, wyliczyć dokładną zgodność (% zgodności oraz Cohen's kappa) wyłącznie na pozycjach `answered` posiadających werdykt sędziego (osobno dla wsparcia cytatów i dla zgodności z odpowiedzią referencyjną TechQA, z jawną obsługą przypadków brzegowych gdy `p_e == 1.0`), osobno podsumować jakościowo warstwę `abstained` (`human_abstain_justified`, jeśli wypełniona) oraz opcjonalnie zregenerować/zaktualizować raport Markdown.

**Contract**:
- `compute_cohens_kappa(pairs: list[tuple[str, str]]) -> float | None`: zwraca `None` z wyjaśnieniem w raporcie, gdy `p_e == 1.0` (brak wariancji w ocenach — np. 100% `supported`).
- `evaluate_judge_agreement(run_path: Path, audit_path: Path) -> JudgeAgreementSummary`: waliduje brak pustych ocen człowieka na recenzowanych pozycjach `answered` (pomijając pola sędziego dla warstwy `abstained`, której sędzia LLM nie ocenia) i liczy macierz pomyłek sędzia vs człowiek, % zgodności i Cohen's kappa.
- Podpolecenie CLI: `python -m app.cli eval-judge-agreement --run <data/evals/run.json> --audit <data/evals/audit.json> [--report-out <path.md>]`.

#### 3. Testy jednostkowe Fazy 4
**File**: `backend/tests/evals/test_sampling.py` (nowy), `backend/tests/evals/test_agreement.py` (nowy)

**Intent**: Zweryfikować determinizm i stratyfikację próbkowania (w tym `n < 20`, `25% > 20`, brak wycieku werdyktów sędziego do arkusza MD dla recenzenta) oraz poprawność obliczeń Cohen's kappa (idealna zgodność, losowa zgodność, brak wariancji `p_e == 1.0`, niezgodność).

**Contract**: Testy jednostkowe bez sieci i bez DB.

### Success Criteria:

#### Automated Verification:
- Testy Fazy 4 przechodzą: `cd backend; uv run pytest tests/evals/test_sampling.py tests/evals/test_agreement.py`
- Wszystkie testy backendu, lint, format i mypy przechodzą: `cd backend; uv run ruff check .; uv run ruff format --check .; uv run mypy .; uv run pytest`
- `python -m app.cli eval-judge-agreement --help` zwraca kod 0.

#### Manual Verification:
- Przejrzenie wygenerowanego pliku `*-manual-audit.md` i potwierdzenie, że nie zdradza werdyktu sędziego przed oceną człowieka oraz zawiera pełny kontekst potrzebny do oceny tezy i referencji.

**Implementation Note**: Po ukończeniu tej fazy i przejściu wszystkich testów automatycznych zatrzymaj się na ręczne potwierdzenie formatu arkusza audytu przed przejściem do Fazy 5.

---

## Phase 5: Weryfikacja etykiet, pomiar bazowy i raport końcowy

### Overview
Wykonujemy operacyjną część S-06: ręczną weryfikację kandydatów `is_impossible` (rozwiązującą bloker z roadmapy), zamrożenie `backend/evals/abstention-dataset.json` (cel: min. 50 zweryfikowanych pytań bez odpowiedzi + 50 z odpowiedzią w podziale `dev`/`test`), próbny bieg na `dev`, końcowy pomiar bazowy na zamrożonym `test` w Langfuse Cloud, ręczną walidację próbki ocen sędziego oraz publikację raportu w repozytorium.

### Changes Required:

#### 1. Zamrożony zbiór zweryfikowanych etykiet
**File**: `backend/evals/abstention-dataset.json` (nowy, wygenerowany przez `eval-freeze-abstention`)

**Intent**: Utrwalić w repozytorium ręcznie zweryfikowane etykiety (bez treści TechQA), osiągając cel min. 50 `verified_unanswerable` i min. 50 `answerable_in_corpus`, z wykluczonymi 6 grupami konfliktów `is_impossible` i podziałem `dev`/`test` (30/70).

**Contract**: Plik przechodzi walidację `load_verified_dataset(...)` bez błędów i nie zawiera tekstu dokumentów ani pytań z `train.json`.

#### 2. Raport bazowy Sprawdzianu 1b i 2a
**File**: `context/changes/abstention-evaluation/eval-report.md` (nowy, wygenerowany przez `eval-abstention` + `eval-judge-agreement`)

**Intent**: Opublikować uczciwy pomiar bazowy dla bieżącej konfiguracji S-02 na zamrożonym splicie `test`, z pełnymi metrykami, liczebnością próby, `n_failed`, opóźnieniem `p50`/`p95`, wynikami ręcznej kontroli próbki sędziego (zgodność % i Cohen's kappa), analizą błędów oraz identyfikatorem/linkiem przebiegu w Langfuse Cloud.

**Contract**: Każda opublikowana liczba pochodzi bezpośrednio z przebiegu w Langfuse Cloud (bez flagi `--no-langfuse`) i ma zapisane hashe migawki (`snapshot_id`, `state_sha256`), konfiguracji chunkera (`config_sha256`), modeli i promptów.

#### 3. Aktualizacja dokumentacji przepływu danych
**File**: `docs/przeplyw-danych.md`

**Intent**: Dopisać zwięzłą informację o danych wysyłanych podczas uruchomień operatorowych CLI ewaluacji (pytania z TechQA, cytaty i odpowiedzi referencyjne trafiające do modelu sędziego `EVAL_JUDGE_MODEL` oraz do datasetu/eksperymentu w Langfuse Cloud).

**Contract**: Nowa sekcja lub wiersz w tabeli przepływu danych w `docs/przeplyw-danych.md`, bez zmiany ustaleń dla ruchu użytkowników aplikacji webowej.

### Success Criteria:

#### Automated Verification:
- Zamrożony plik `backend/evals/abstention-dataset.json` istnieje i przechodzi walidację (min. 50 `verified_unanswerable` + min. 50 `answerable_in_corpus`, 0 konfliktów, 0 przecieków `doc_id` między `dev`/`test`): `cd backend; uv run pytest tests/evals/test_dataset.py`
- Wszystkie kontrole backendu przechodzą: `cd backend; uv run ruff check .; uv run ruff format --check .; uv run mypy .; uv run pytest`

#### Manual Verification:
- Operator wykonał ręczny przegląd kandydatów `is_impossible` na podstawie `data/evals/abstention-candidates-review.md` i zamroził `backend/evals/abstention-dataset.json` poleceniem `eval-freeze-abstention`.
- Przebieg próbny na `--split dev` zakończył się poprawnie w Langfuse Cloud.
- Przebieg bazowy na zamrożonym `--split test` zakończył się w Langfuse Cloud, a jego `experiment_id` / link jest widoczny w `context/changes/abstention-evaluation/eval-report.md` i zweryfikowany w UI Langfuse.
- Operator uzupełnił ręczny arkusz próbki (min. 20 przypadków / 25% odpowiedzi), uruchomił `eval-judge-agreement` i zweryfikował sekcję zgodności sędzia–człowiek w `eval-report.md`.
- Sprawdzono, że `git status` nie zawiera żadnych plików z `data/` ani `.env*`.

**Implementation Note**: Faza 5 zawiera bramki wymagające decyzji i przeglądu człowieka (etykiety `is_impossible` oraz próbka audytu sędziego); nie generuj ani nie zgaduj ocen człowieka automatycznie.

---

## Testing Strategy

### Unit Tests:
- `tests/evals/test_dataset.py`: deduplikacja 20 grup, wykluczanie 6 konfliktów `is_impossible`, brak przecieku `doc_id` między `dev`/`test`, walidacja schematu `abstention-dataset.json`, pomijanie `ambiguous`.
- `tests/evals/test_prepare.py`: generowanie szablonu etykiet i przewodnika MD, `validate_and_freeze_labels` (odrzucenie nieuzupełnionych etykiet, brak kopiowania treści TechQA).
- `tests/evals/test_metrics.py`: `abstention_accuracy`, `false_refusal_rate`, inwarianty cytatów, wykluczenie `failed` z mianowników jakości i `p50`/`p95`, rozbicie przyczyn abstencji (`no_hits`, `no_claims`, `quote_check_rejected_all`, `verify_rejected_all`).
- `tests/evals/test_judge.py`: `FakeJudgeChatModel` (`tests/evals/fakes.py`) dla wsparcia cytatów i zgodności 3-stopniowej (`full`/`partial`/`incorrect`), obsługa timeoutu/błędu sędziego (`n_judge_failed`), fallback `EVAL_JUDGE_MODEL` → `CHAT_MODEL`.
- `tests/evals/test_runner.py` i `tests/evals/test_report.py`: egzekwowanie `answer_deadline_s`, tryb `--no-langfuse`, fail-fast bez kluczy Langfuse, synchronizacja datasetu i wywołanie mockowanego `run_experiment`, kompletność sekcji i ostrzeżeń w raporcie MD.
- `tests/evals/test_sampling.py` i `tests/evals/test_agreement.py`: determinizm i stratyfikacja próbki (min. 20 lub 25%), brak przecieku werdyktów sędziego do arkusza MD, obliczenia Cohen's kappa (w tym przypadek brzegowy `p_e == 1.0`).

### Integration Tests:
- Test `@pytest.mark.corpus` na prawdziwym `data/raw/techqa/train.json` (potwierdzenie 910 rekordów, 20 grup duplikatów, 6 konfliktów).
- Test `@pytest.mark.db` sprawdzający `get_chunk_set_repro_info` oraz uruchomienie `eval-abstention --no-langfuse --yes` na mini-migawce w `imported_conn` z `ScriptedChatModel` na `SelectorEventLoop`.

### Manual Testing Steps:
1. Uruchomienie `eval-prepare-abstention` na pełnej bazie i weryfikacja czytelności arkusza `data/evals/abstention-candidates-review.md`.
2. Przegląd treści promptów sędziego `citation_support.md` i `reference_agreement.md`.
3. Próbne uruchomienie `eval-abstention --split dev --limit 3 --no-langfuse --yes` na Windows przeciwko lokalnemu ParadeDB.
4. Pełna weryfikacja etykiet `is_impossible` → `eval-freeze-abstention` → bieg `dev` i `test` w Langfuse Cloud → ręczna ocena próbki → `eval-judge-agreement`.

## Performance Considerations

- Przy `n ≈ 70` pytań w splicie `test` (70% ze 100+) i `concurrency = 2` (domyślnie): każde pytanie z odpowiedzią to 2 wywołania grafu (`draft` + `verify`) + do 2 wywołań sędziego (`citation_support` + `reference_agreement`), czyli ~4 wywołania LLM/pytanie (pytania z abstencją: 1–2 wywołania). Czas pełnego przebiegu `test` wyniesie orientacyjnie 3–6 minut.
- Pomiar `latency_ms` obejmuje wyłącznie wykonanie grafu odpowiedzi S-02 (od `retrieve` do `compose`/`abstain`), **bez** czasu wywołań sędziego LLM, aby metryka `p95 < 10 s` dokładnie odpowiadała NFR z PRD dla konsultanta.

## Migration Notes

Brak migracji bazy danych i brak zmian w kontrakcie API (OpenAPI / frontend bez zmian).

## References

- Wymagania i kryteria: `context/foundation/prd.md` (FR-014, FR-003, Success Criteria §Primary)
- Roadmapa etapu: `context/foundation/roadmap.md` (sekcja `S-06: Ewaluacja abstencji` oraz `Jak weryfikujemy`)
- Profil danych: `docs/raport-techqa.md`
- Poprzednia kontrola abstencji: `context/archive/2026-11-23-grounded-answer-or-abstention/abstention-check.md`
- Istniejący graf odpowiedzi: `backend/app/answering/graph.py:47-73`, `backend/app/answering/nodes.py:247-339`
- Wzorzec eksperymentów Langfuse (AI Devs 4): `D:\Firma\second-brain\super-brain\AI_DEVS_4\4th-devs\03_01_evals\experiments\response-correctness.ts`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Zbiór ewaluacyjny, deduplikacja i eksport kandydatów

#### Automated

- [x] 1.1 Testy jednostkowe i korpusowe Fazy 1 przechodzą (`pytest tests/evals/test_dataset.py tests/evals/test_prepare.py`) — 376e738
- [x] 1.2 Kontrola lintera, formatu i typów przechodzi (`ruff check`, `ruff format --check`, `mypy`) — 376e738
- [x] 1.3 Polecenia `eval-prepare-abstention --help` i `eval-freeze-abstention --help` zwracają kod 0 — 376e738

#### Manual

- [x] 1.4 Eksport `eval-prepare-abstention` na lokalnej bazie generuje czytelny `data/evals/abstention-candidates-review.md` z top-10 BM25 — 376e738

### Phase 2: Sędziowie automatyczni, metryki deterministyczne i testy

#### Automated

- [x] 2.1 Testy jednostkowe Fazy 2 przechodzą (`pytest tests/evals/test_metrics.py tests/evals/test_judge.py`) — 0e108a2
- [x] 2.2 Wszystkie dotychczasowe testy backendu nadal przechodzą (`pytest`) — 0e108a2
- [x] 2.3 Kontrola lintera, formatu i typów przechodzi (`ruff check`, `ruff format --check`, `mypy`) — 0e108a2

#### Manual

- [x] 2.4 Przegląd promptów `citation_support.md` i `reference_agreement.md` potwierdza zgodność z definicją wsparcia z PRD — 0e108a2

### Phase 3: Runner ewaluacji, Langfuse Cloud i raport Markdown

#### Automated

- [x] 3.1 Testy Fazy 3 przechodzą (`pytest tests/evals/test_runner.py tests/evals/test_report.py`) — b3ea0d4
- [x] 3.2 Wszystkie testy backendu przechodzą (`pytest`) — b3ea0d4
- [x] 3.3 Kontrola lintera, formatu i typów przechodzi (`ruff check`, `ruff format --check`, `mypy`) — b3ea0d4

#### Manual

- [x] 3.4 Próbne uruchomienie `eval-abstention --split dev --limit 3 --no-langfuse --yes` na Windows przechodzi bez błędów `SelectorEventLoop` i generuje JSON oraz raport MD — b3ea0d4

### Phase 4: Próbkowanie i walidacja ręczna ocen sędziego

#### Automated

- [x] 4.1 Testy Fazy 4 przechodzą (`pytest tests/evals/test_sampling.py tests/evals/test_agreement.py`) — e59031b
- [x] 4.2 Wszystkie kontrole backendu przechodzą (`ruff check`, `ruff format --check`, `mypy`, `pytest`) — e59031b
- [x] 4.3 Polecenie `eval-judge-agreement --help` zwraca kod 0 — e59031b

#### Manual

- [x] 4.4 Wygenerowany arkusz `*-manual-audit.md` nie zdradza werdyktów sędziego i zawiera pełny kontekst do oceny ręcznej — e59031b

### Phase 5: Weryfikacja etykiet, pomiar bazowy i raport końcowy

#### Automated

- [x] 5.1 Zamrożony `backend/evals/abstention-dataset.json` przechodzi walidację (min. 50+50, 0 konfliktów, 0 przecieków `doc_id`) — 4b5a464
- [x] 5.2 Wszystkie kontrole backendu przechodzą (`ruff check`, `ruff format --check`, `mypy`, `pytest`) — 4b5a464

#### Manual

- [x] 5.3 Operator zweryfikował kandydatów `is_impossible` i zamroził `backend/evals/abstention-dataset.json` — 4b5a464
- [x] 5.4 Przebieg próbny na `--split dev` zakończył się poprawnie w Langfuse Cloud — 4b5a464
- [x] 5.5 Przebieg bazowy na `--split test` zapisał się w Langfuse Cloud i jego ID/link widnieje w `eval-report.md` — 4b5a464
- [x] 5.6 Operator uzupełnił próbkę ręczną (min. 20 / 25%), uruchomił `eval-judge-agreement` i zatwierdził sekcję walidacji w `eval-report.md` — 4b5a464
- [x] 5.7 `git status` nie zawiera żadnych plików z `data/` ani `.env*` — 4b5a464
