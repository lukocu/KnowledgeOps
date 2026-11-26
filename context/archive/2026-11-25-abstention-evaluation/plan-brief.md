# Ewaluacja abstencji i odpowiedzi (S-06) — Plan Brief

> Full plan: `context/changes/abstention-evaluation/plan.md`

## What & Why

Budujemy odtwarzalne narzędzie CLI dla operatora do pomiaru jakości odpowiedzi i abstencji (Sprawdzian 1b i 2a z PRD / `S-06`). Bez ręcznie zweryfikowanego zbioru pytań i systematycznej ewaluacji nie wiemy, czy graf odpowiedzi z S-02 nie odmawia zbyt często (fałszywe odmowy), czy rzeczywiście wstrzymuje się przy braku dowodów oraz czy cytaty faktycznie wspierają generowane tezy.

## Starting Point

Graf odpowiedzi (`retrieve → draft → quote_check → verify → compose | abstain`) działa w `backend/app/answering/` i wysyła pojedyncze ślady do Langfuse Cloud (`langfuse==5.2.0`), ale poza dwoma testami kontrolnymi (`TRAIN_Q000`, `TRAIN_Q002`) brak jakiejkolwiek warstwy ewaluacyjnej. Plik `data/raw/techqa/train.json` (910 rekordów: 610/300) ma 20 grup identycznych pytań, w tym 6 par ze sprzecznymi flagami `is_impossible`, a `is_impossible=true` nie dowodzi braku odpowiedzi w całym korpusie.

## Desired End State

Operator dysponuje zamrożonym, ręcznie zweryfikowanym zbiorem etykiet w repo (`backend/evals/abstention-dataset.json`, min. 50+50 pytań w podziale `dev`/`test` bez przecieku) oraz poleceniami CLI (`eval-prepare-abstention`, `eval-freeze-abstention`, `eval-abstention`, `eval-judge-agreement`). Uruchomienie ewaluacji zapisuje eksperyment z ocenami per-item i run-level w Langfuse Cloud, eksportuje stratyfikowaną próbkę do kontroli ręcznej i generuje raport bazowy `context/changes/abstention-evaluation/eval-report.md` z liczebnością próby, `n_failed`, opóźnieniem `p50`/`p95` i zgodnością sędzia–człowiek.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) |
|---|---|---|
| Weryfikacja `is_impossible` i próba | Dwuetapowy CLI (eksport top-10 BM25 + zamrożenie etykiet), cel min. 50+50 | Odblokowuje bloker roadmapy bez fałszywych etykiet przy realistycznym nakładzie ręcznego przeglądu. |
| Duplikaty i podział zbioru | Podział `dev`/`test` (30/70) po grupowaniu pytań i `doc_id`; 6 konfliktów wykluczone | Eliminuje przeciek TRAIN/DEV i pozwala na przyszłe strojenie wyłącznie na `dev`. |
| Sędzia automatyczny (LLM) | Osobny `EVAL_JUDGE_MODEL` (jawny fallback na `CHAT_MODEL`), cytat binarny, referencja `full`/`partial`/`incorrect` | Ogranicza self-preference bias względem `verify` z S-02 i odróżnia odpowiedzi częściowe od błędnych. |
| Walidacja ręczna sędziego | Stratyfikowana próbka min. 20 przypadków (lub 25% odpowiedzi) + Cohen's kappa | Waliduje wiarygodność sędziego automatycznego (roadmap Unknown #2) bez efektu zakotwiczenia recenzenta. |
| Przechowywanie artefaktów | Etykiety (ID + etykieta + notatka) i raport MD w repo; surowe eksporty w `data/evals/` | Zachowuje pełną odtwarzalność w git bez kopiowania treści TechQA i bez nowej migracji DB. |
| Błędy, współbieżność, tryby | Błędy API/timeouty jako osobne `failed`, `concurrency=2`, `--split`, `--limit`, `--yes`, bez cichych retry | Błąd sieci nigdy nie zniekształca trafności abstencji ani fałszywych odmów. |
| Granica zakresu S-06 | Wyłącznie narzędzie + weryfikacja etykiet + pomiar bazowy (bez zmian w S-02) | Zapewnia czysty punkt odniesienia przed ewentualnym strojeniem promptów lub eksperymentami. |
| Tryb Langfuse Cloud | Wymagany domyślnie (fail-fast bez kluczy); jawna flaga `--no-langfuse` z ostrzeżeniem w raporcie | Gwarantuje, że każda publikowana liczba ma przebieg w Langfuse, nie blokując prób lokalnych. |

## Scope

**In scope:** Pakiet `backend/app/evals/` (dataset, prepare, metrics, judge, runner, langfuse_eval, report, sampling, agreement), 4 podpolecenia w `backend/app/cli.py`, konfiguracja `EVAL_JUDGE_*`, testy jednostkowe/DB/korpusowe, ręczna weryfikacja etykiet (`backend/evals/abstention-dataset.json`), pomiar bazowy `dev`/`test` w Langfuse Cloud, raport `eval-report.md` i aktualizacja `docs/przeplyw-danych.md`.

**Out of scope:** Zmiany w promptach lub grafie S-02, migracje PostgreSQL, zmiany w API/frontendzie, ewaluacja sprzecznych źródeł (`S-07`), porównanie retrieval (`S-04`), kopiowanie surowych tekstów TechQA do repozytorium.

## Architecture / Approach

Nowy pakiet `backend/app/evals/` wywołuje bezpośrednio skompilowany graf S-02 (`build_answer_graph`) w pętli `asyncio.SelectorEventLoop` (wymaganej przez `psycopg` async na Windows), mierzy wyłącznie czas grafu (`p50`/`p95`), uruchamia niezależnego sędziego LLM przez `langchain-openai` (`with_structured_output(..., strict=True)`) i przekazuje oceny per-item oraz run-level do `Langfuse.run_experiment` (lub lokalnego runnera z `Semaphore` przy `--no-langfuse`).

## Phases at a Glance

| Phase | What it delivers | Key risk |
|---|---|---|
| 1. Zbiór i eksport kandydatów | Deduplikacja, podział `dev`/`test`, `eval-prepare-abstention` i `eval-freeze-abstention` | Przeciek między splitami przy powtarzających się `doc_id` |
| 2. Sędziowie i metryki | Deterministyczne metryki + sędzia LLM (`EVAL_JUDGE_*`) + testy bez sieci | Zbyt ciasny lub zbyt luźny prompt sędziego vs definicja PRD |
| 3. Runner, Langfuse i raport | `eval-abstention`, Langfuse 5.2.0 `run_experiment`, `--no-langfuse`, raport MD | Interakcja pętli `SelectorEventLoop` z `Langfuse.run_experiment` na Windows |
| 4. Próbkowanie i walidacja | Stratyfikowany eksport audytu (bez werdyktów sędziego) i `eval-judge-agreement` | Brak wariancji ocen w małej próbce (`p_e == 1.0` dla Cohen's kappa) |
| 5. Etykiety i pomiar bazowy | Ręczny przegląd `is_impossible` (≥50+50), pomiar `dev`/`test`, raport końcowy | Czasochłonność ręcznego przeglądu lub limity RPM dostawcy LLM |

**Prerequisites:** Zaimportowana migawka TechQA w lokalnym ParadeDB (`S-01`), działający graf odpowiedzi (`S-02`), lokalny `data/raw/techqa/train.json`, klucze `OPENAI_API_KEY` oraz `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` (do Fazy 5).
**Estimated effort:** ~3–4 sesje implementacyjne (Fazy 1–4) + czas ręcznego przeglądu etykiet i próbki audytu przez operatora (Faza 5).

## Open Risks & Assumptions

- Ręczny przegląd ~60–80 kandydatów `is_impossible` zakłada, że co najmniej 50 okaże się rzeczywiście nieodpowiadalnych w całym korpusie; jeśli odsetek fałszywych `is_impossible` będzie wyższy, operator wyeksportuje dodatkową partię flagą `--unanswerable`.
- Domyślny `EVAL_JUDGE_MODEL` bez osobnej konfiguracji używa `CHAT_MODEL` (fallback oznaczony ostrzeżeniem w raporcie) — do końcowego pomiaru w Fazie 5 zalecane jest wskazanie odrębnego lub mocniejszego modelu sędziego.
- `p95 < 10 s` zależy od opóźnień zewnętrznego dostawcy API (np. Gemini/OpenRouter) i może być wrażliwe na limity RPM przy wyższym `--concurrency`.

## Success Criteria (Summary)

- Operator zamraża zweryfikowany zbiór `backend/evals/abstention-dataset.json` (≥50+50 pytań, 0 konfliktów, 0 przecieków) i uruchamia pełną ewaluację jednym poleceniem `eval-abstention`.
- Każda opublikowana metryka w `eval-report.md` (abstencja, fałszywe odmowy, wsparcie cytatów, zgodność z referencją, `p50`/`p95`, `n_failed`) ma podaną liczebność próby, hashe odtwarzalności oraz ID/link przebiegu w Langfuse Cloud.
- Wiarygodność automatycznego sędziego jest potwierdzona ręczną walidacją stratyfikowanej próbki (≥20 przypadków / 25% odpowiedzi) z policzoną zgodnością i Cohen's kappa.
