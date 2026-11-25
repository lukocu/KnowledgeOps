<!-- PLAN-REVIEW-REPORT -->

# Plan Review: Ewaluacja abstencji i odpowiedzi (S-06)

- **Plan**: `context/changes/abstention-evaluation/plan.md`
- **Mode**: Deep
- **Date**: 2026-11-25
- **Verdict**: REVISE → SOUND (po zastosowaniu poprawek F1–F6)
- **Findings**: 1 critical, 4 warnings, 1 observation

## Verdicts

| Dimension             | Verdict | After Fixes |
| --------------------- | ------- | ----------- |
| End-State Alignment   | PASS    | PASS        |
| Lean Execution        | PASS    | PASS        |
| Architectural Fitness | WARNING | PASS        |
| Blind Spots           | FAIL    | PASS        |
| Plan Completeness     | WARNING | PASS        |

## Grounding

`Grounding: 7/7 paths ✓, 7/7 symbols ✓, brief↔plan ✓`

## Findings

### F1 — Brak mapowania canonical_doc_id w assign_splits i walidacji offline

- **Severity**: ❌ CRITICAL
- **Impact**: 🔎 MEDIUM — warto się zatrzymać; rzeczywisty kompromis lub nietrywialna edycja
- **Dimension**: Blind Spots
- **Location**: Critical Implementation Details; Phase 1 — Zmiany 1–2; Phase 5 (kryterium 5.1)
- **Detail**: Sekcja Critical Implementation Details wymaga grupowania pytań z odpowiedzią według `canonical_doc_id` (mapując `contexts[].filename` przez `documents.canonical_doc_id`), a `backend/app/techqa/importer.py:185-219, 304-308` potwierdza, że niekanoniczne kopie nie mają chunków w `chunks`. Tymczasem `assign_splits` nie przyjmowało mapy `doc_id -> canonical_doc_id`, a `validate_and_freeze_labels` i `test_dataset.py` działają offline bez dostępu do bazy.
- **Fix A ⭐ Recommended**: Przekaż opcjonalną mapę `canonical_doc_map: Mapping[str, str] | None` do `assign_splits` (pobieraną z `documents` w `eval-prepare-abstention`) i zapisz `canonical_doc_id` dla pytań z odpowiedzią w `backend/evals/abstention-dataset.json`.
  - Strength: Zero przecieków duplikatów dokumentów i pełna walidacja offline w `eval-freeze-abstention` oraz `test_dataset.py`.
  - Tradeoff: Dodaje jedno pole ID (`canonical_doc_id: str | None`) do schematu `abstention-dataset.json`.
  - Confidence: HIGH — `documents(doc_id, canonical_doc_id)` jest już wypełniane przez `importer.py:199`.
  - Blind spot: Nie sprawdzono, czy w 610 rekordach `is_impossible=False` występują niekanoniczne `doc_id`.
- **Fix B**: Wyliczaj `canonical_doc_id` z `corpus.zip` (SHA-256) podczas `assign_splits` i `validate_and_freeze_labels`.
  - Strength: Bez połączenia z bazą i bez dodatkowego pola w JSON.
  - Tradeoff: Czytanie i hashowanie całego `corpus.zip` (~28k plików) spowalnia walidację.
  - Confidence: MEDIUM — wymaga rozpakowywania zipa w każdym uruchomieniu.
  - Blind spot: Czas pełnego odczytu `corpus.zip` na Windows niezmierzony.
- **Decision**: FIXED (Fixed via Fix A)

### F2 — Warstwa abstained w próbce audytu sędziego vs brak ocen sędziego dla abstencji

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — warto się zatrzymać; rzeczywisty kompromis lub nietrywialna edycja
- **Dimension**: Blind Spots
- **Location**: Phase 2 — Zmiana 2; Phase 4 — Zmiany 1–2
- **Detail**: Sędzia LLM w Fazie 2 jest wywoływany wyłącznie dla `outcome == "answered"`, natomiast w Fazie 4 `sample_for_manual_audit` włącza warstwę `abstained`, a `evaluate_judge_agreement` walidowało brak pustych ocen człowieka na wszystkich recenzowanych pozycjach i brakowało reguły podziału budżetu próbki między warstwy.
- **Fix**: Doprecyzuj jawne proporcje warstw (do 5 `omitted_claims > 0`, do 5 `abstained`, reszta z `answered`) oraz pomiń pola werdyktów sędziego dla `abstained` w `evaluate_judge_agreement` (dodając opcjonalne `human_abstain_justified: bool | null`).
  - Strength: Eliminuje blokującą sprzeczność kontraktu i zachowuje przegląd jakościowy abstencji bez psucia Cohen's kappa.
  - Tradeoff: Minimalnie rozszerza schemat `ManualAuditEntry` o pole opcjonalne dla warstwy `abstained`.
  - Confidence: HIGH — wynika wprost z kontraktu Fazy 2 i Fazy 4.
  - Blind spot: None significant.
- **Decision**: FIXED (Fixed in plan)

### F3 — Prywatne API Langfuse._run_experiment_async, filtrowanie splitu i deprecated pola

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — warto się zatrzymać; rzeczywisty kompromis lub nietrywialna edycja
- **Dimension**: Architectural Fitness
- **Location**: Critical Implementation Details; Phase 3 — Zmiana 2
- **Detail**: W `langfuse==5.2.0` `DatasetClient.run_experiment` nie ma wersji async i uruchamia eksperyment na wszystkich elementach datasetu (brak filtrowania dla `--split`/`--limit`), `Langfuse._run_experiment_async` wymaga wszystkich argumentów keyword-only (w tym `composite_evaluator`), a `dataset_run_id`/`dataset_run_url` to deprecated aliasy dla `experiment_id`/`experiment_url`.
- **Fix A ⭐ Recommended**: Pozostań przy `await client._run_experiment_async(...)` (dla `SelectorEventLoop` na Windows), dopisz filtrowanie `dataset.items` po `id` dla `--split`/`--limit`, pełną sygnaturę keyword-only (`composite_evaluator=None`), odczyt `experiment_id`/`experiment_url` oraz test kontraktu w `test_runner.py`.
  - Strength: Jedna pętla `SelectorEventLoop` z jedną pulą DB i obsługa podzbiorów w jednym datasecie.
  - Tradeoff: Zależność od prywatnej metody `_run_experiment_async` (zabezpieczona testem kontraktu).
  - Confidence: HIGH — zweryfikowano sygnatury w `langfuse==5.2.0`.
  - Blind spot: Idempotentność `create_dataset_item` z powtarzalnym `id` w Langfuse Cloud do potwierdzenia w próbnym biegu `dev`.
- **Fix B**: Publiczne `client.run_experiment(data=selected_items, ...)` poza pętlą `asyncio` z osobnym wątkiem `SelectorEventLoop` dla puli DB.
  - Strength: Brak zależności od prywatnego `_run_experiment_async`.
  - Tradeoff: Dodatkowa złożoność wielowątkowej pętli.
  - Confidence: MEDIUM — więcej kodu infrastrukturalnego.
  - Blind spot: None significant.
- **Decision**: FIXED (Fixed via Fix A)

### F4 — Zmiana run_config złamie tests/answering/test_observability.py (+ niespójność snapshot_id)

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — szybka decyzja; poprawka jest oczywista i wąsko ograniczona
- **Dimension**: Architectural Fitness
- **Location**: Phase 3 — Zmiana 1
- **Detail**: `backend/tests/answering/test_observability.py:30-35` porównuje cały słownik `metadata == {...}`, więc dodanie `chat_reasoning_effort` wymaga aktualizacji testu; ponadto Intent wspominał o `snapshot_id` w `run_config`, czego Contract już nie zawierał.
- **Fix**: Dopisz `backend/tests/answering/test_observability.py` do listy plików modyfikowanych w Fazie 3 i doprecyzuj, że `run_config` dodaje wyłącznie `chat_reasoning_effort` (a `snapshot_id` trafia do metadanych eksperymentu w `langfuse_eval.py`).
- **Decision**: FIXED (Fixed in plan)

### F5 — ScriptedChatModel nie obsługuje schematów sędziego LLM

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — szybka decyzja; poprawka jest oczywista i wąsko ograniczona
- **Dimension**: Plan Completeness
- **Location**: Phase 2 — Zmiana 4; Testing Strategy
- **Detail**: `backend/tests/answering/fakes.py:65-69` akceptuje na sztywno wyłącznie `DraftOutput` i `VerifyOutput`, rzucając `AssertionError` dla innych schematów.
- **Fix**: Zaplanuj dedykowany `FakeJudgeChatModel` w `backend/tests/evals/fakes.py` obsługujący dowolny schemat w `with_structured_output(..., strict=True)` oraz symulację wyjątków/timeoutów.
- **Decision**: FIXED (Fixed in plan)

### F6 — Proporcja dev/test w prepare.py i ścisłe porównanie cytatu w check_citation_invariants

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — szybka decyzja; poprawka jest oczywista i wąsko ograniczona
- **Dimension**: Blind Spots
- **Location**: Phase 1 — Zmiana 2; Phase 2 — Zmiana 3
- **Detail**: `prepare_abstention_candidates` nie precyzowało proporcji `dev`/`test` (30/70), a `compose_answer` (`nodes.py:199`) wycina `quote` dosłownie z `chunk.text[quote_start:quote_end]`.
- **Fix**: Dopisz stratyfikowany dobór proporcjonalny 30/70 po deterministycznym sortowaniu `question_id` oraz ścisłe porównanie `chunk_texts[chunk_id][quote_start:quote_end] == quote` w `check_citation_invariants`.
- **Decision**: FIXED (Fixed in plan)
