<!-- IMPL-REVIEW-REPORT -->

# Implementation Review: Odpowiedź z cytatami albo abstencja (S-02)

- **Plan**: context/changes/grounded-answer-or-abstention/plan.md
- **Scope**: Full plan
- **Reviewed phases**: 1, 2, 3, 4, 5, 6
- **Date**: 2026-11-25
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 3 warnings, 7 observations

## Verdicts

| Dimension           | Verdict |
| ------------------- | ------- |
| Plan Adherence      | WARNING |
| Scope Discipline    | WARNING |
| Safety & Quality    | WARNING |
| Architecture        | PASS    |
| Pattern Consistency | WARNING |
| Success Criteria    | PASS    |

## Success Criteria (uruchomione 2026-11-25)

- Backend (kontener Linux, `uv:python3.14-bookworm-slim`): `uv sync --locked` OK, `ruff check` OK, `ruff format --check` OK (54 pliki), `mypy` OK (51 plików), `python -m app.cli migrate` → „Schemat aktualny”, `pytest` → 199 passed, 1 skipped, 2 deselected (`live`).
- Frontend: `npm run lint`, `format:check`, `typecheck`, `build` OK; `npm run api:types` + `git diff --exit-code app/api/schema.d.ts` bez zmian.
- CI na `4242dfa`: backend, frontend, contract zielone.
- Ręczne: wszystkie wiersze `[x]`. Dwa zastąpione słabszym dowodem: 5.4 (przycisk „Więcej kontekstu powyżej” niewidziany w UI, API symetryczne sprawdzone) i 5.6 (okno prywatne zastąpione żądaniem bez ciasteczka → 404 oraz stanem „Nie znaleziono odpowiedzi w tej sesji” dla fałszywego id).

## Findings

### F1 — Limit czasu obejmuje `yield` w generatorze SSE

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: backend/app/api/answers.py:234
- **Detail**: `async with asyncio.timeout(answer_deadline_s)` obejmuje pętlę z `yield ServerSentEvent(...)`. Jeśli termin minie, gdy generator jest wstrzymany na `yield` (Starlette zapisuje do gniazda), anulowanie trafia poza blok i nie staje się `TimeoutError` (PEP 789). Strumień kończy się wtedy bez zdarzenia `error` i bez wiersza `failed`. Okno jest wąskie, ale skutek cichy, a plan wymaga `failed` z `model_unavailable` po przekroczeniu terminu.
- **Fix**: Ogranicz czas tylko dla pobrania kolejnego zdarzenia: wylicz `deadline = loop.time() + answer_deadline_s` i owiń każde `anext(stream)` w `asyncio.timeout_at(deadline)`, a `yield` zostaw poza blokiem.
  - Strength: Usuwa klasę problemu bez nowej architektury; obsługa błędów i zapis `failed` zostają bez zmian.
  - Tradeoff: Kilka linii więcej i jawny iterator zamiast `async for`.
  - Confidence: HIGH — to zalecany wzorzec dla async generatorów (PEP 789).
  - Blind spot: Brak testu wymuszającego termin w trakcie `yield`; warto dodać test z wolnym fałszywym modelem.
- **Decision**: FIXED

### F2 — Pusty `CHAT_REASONING_EFFORT` nie wyłącza parametru

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: backend/app/settings.py:11,24-25; .env.example:22-23; docker-compose.yml:32
- **Detail**: `env_ignore_empty=True` sprawia, że pusta wartość przyjmuje domyślne `"low"`. Komentarze w `settings.py` i `.env.example` mówią, że pusty ciąg wyłącza parametr. `docker-compose.yml` przekazuje `${CHAT_REASONING_EFFORT:-}`, więc pusta wartość też daje `low`. Model bez rozumowania dostanie `reasoning_effort=low` i może zwrócić błąd. Działa tylko `none`.
- **Fix**: Popraw komentarze w `settings.py` i `.env.example` na „`none` wyłącza parametr” i usuń ścieżkę `effort or None` w `model.py`, albo w compose domyślnie przekazuj `low`.
- **Decision**: FIXED

### F3 — Stałe szerokości paneli łamią układ poniżej 1280 px

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Plan Adherence
- **Location**: frontend/app/components/assistant/EvidencePanel.tsx:411; CheckedChunksPanel.tsx:45; AssistantFrame.tsx
- **Detail**: Plan („What We're NOT Doing”): „Układ nie może jednak blokować węższych okien: nie zakładamy stałych szerokości, które psułyby się poniżej 1280 px”. Panele mają `w-[400px]`/`w-[420px]` z `flex-none`, a wątek stałe `px-10`, bez klas responsywnych. Przy ok. 1024 px panel ściska wątek. Wąskie okno 390 px należy do S-05, ale zakres 1024–1280 px nie powinien się psuć już teraz.
- **Fix**: Zamień szerokość na `w-[min(400px,45%)]` (oraz 420px analogicznie) i zezwól na `shrink`, a `px-10` na `px-6 xl:px-10`; sprawdź zrzut przy 1024 px.
  - Strength: Mała zmiana klas; nie wyprzedza arkusza dowodu z S-05.
  - Tradeoff: Panel przy 1024 px węższy niż na kanwie.
  - Confidence: MED — nie mierzono jeszcze układu przy 1024 px.
  - Blind spot: Długie `doc_id` i nagłówki w węższym panelu.
- **Decision**: FIXED

### F4 — Połączenie z bazą w grafie bez limitu czasu

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: backend/app/answering/nodes.py:270
- **Detail**: `self._pool.connection()` używa domyślnych 30 s puli, a reszta kodu `CONNECTION_TIMEOUT_S = 5.0`. Przy wyczerpanej puli pierwszy pada termin 25 s i błąd jest klasyfikowany jako `model_unavailable` zamiast `database_unavailable`.
- **Fix**: Przekaż `timeout=CONNECTION_TIMEOUT_S` w `nodes.py:270`.
- **Decision**: FIXED

### F5 — Przełączanie dostawcy modelu spoza planu

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Scope Discipline
- **Location**: backend/app/answering/model.py; backend/app/settings.py:21-25; .env.example; docker-compose.yml
- **Detail**: `OPENAI_BASE_URL` (OpenRouter, Gemini) i `CHAT_REASONING_EFFORT` doszły po fazie 6 (commity 4b0fe89, 9de51ec, 00369c2). Zmiana świadoma, z testami (`test_model.py`) i opisem w dokumentach fundamentowych, ale plan dalej mówi tylko o OpenAI. Domyślny `CHAT_MODEL=gpt-6-luna` w `.env.example` i `settings.py` pozostał niezweryfikowany.
- **Fix**: Dopisz do planu krótki aneks (dostawca przez `OPENAI_BASE_URL`, lokalnie Gemini `gemini-3.5-flash-lite` z `low`) i zweryfikuj albo zmień domyślny `CHAT_MODEL`.
- **Decision**: FIXED

### F6 — `verify` pomijany, gdy wszystkie tezy odrzucone

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: backend/app/answering/graph.py:35-38
- **Detail**: Plan zawsze uruchamia `verify` po `quote_check`. Kod przy braku ocalałych tez przechodzi wprost do `abstain` (`none_supported`), więc zdarzenie `verify` nie przychodzi. Rozsądne (bez zbędnego wywołania modelu), skomentowane i przetestowane, ale nieopisane w planie.
- **Fix**: Dopisz do „Reguły odpowiedzi” w planie: zero tez po `quote_check` → `abstain` bez `verify`.
- **Decision**: FIXED

### F7 — `retrieved_chunk_ids` nie trafia do metadanych śladu

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: backend/app/api/answers.py:224; backend/app/observability.py:66-81
- **Detail**: Plan wymienia `retrieved_chunk_ids` w metadanych śladu. `run_config` obsługuje ten parametr, ale wywołanie go nie przekazuje (id nie są znane przed startem grafu). Identyfikatory są w śladzie jako wyjście węzła `retrieve`, co potwierdziła ręczna kontrola Langfuse (6.5).
- **Fix**: Dopisz w planie, że id fragmentów są w wyjściu spanu `retrieve`, i usuń nieużywany parametr z `run_config`.
- **Decision**: FIXED

### F8 — Komunikat o roli widoczny tylko po najechaniu

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: frontend/app/components/shell/RoleSwitch.tsx:48
- **Detail**: Plan: stały komunikat jako tooltip DEMO i tekst przy przełączniku. Kod daje `title` i `sr-only`, więc widzący użytkownik widzi go tylko po najechaniu (dla klawiatury i dotyku w ogóle).
- **Fix**: Dodaj krótki widoczny podpis przy przełączniku (np. „Rola nie jest kontrolą dostępu”, mały wyciszony tekst) albo potwierdź, że tooltip DEMO wystarczy, i dopisz to do planu.
- **Decision**: FIXED

### F9 — Pomocnicze funkcje routerów i ustawienia niespójne

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: backend/app/api/answers.py:30; backend/app/api/evidence.py:51,56,83
- **Detail**: `answers.py` importuje prywatne `_connection` z `evidence.py`, a `CONNECTION_TIMEOUT_S` jest zdublowane. `evidence.py` tworzy `Settings()` wprost zamiast `SettingsDep` jak `answers.py`. 404 w `/api/evidence` zwraca `str(exc)` z wewnętrznym `chunk_set_id`, a inne trasy stałe komunikaty.
- **Fix**: Przenieś `_connection` i stałą do `app/db.py` jako publiczny helper, użyj `SettingsDep` w `evidence.py` i zwracaj stały komunikat 404.
- **Decision**: FIXED

### F10 — Drobne długi: nieużywane ustawienie, kolory i odczyt promptów

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: backend/app/settings.py:19; backend/app/answering/prompts/__init__.py:16-26; frontend/app/components/assistant/{ProgressCard,AbstentionView,ErrorState,AnswerView}.tsx
- **Detail**: `evidence_context_chunks` jest zadeklarowane, ale nieużywane (endpoint i front mają własne 1). Kilka komponentów używa surowych hex (`#1a6b36`, `#2f5fc4`) obok tokenów. Prompty są czytane i hashowane synchronicznie przy każdym żądaniu (ok. 6 odczytów). Brak limitu żądań `POST /api/answers` przed publicznym demo.
- **Fix**: Użyj `evidence_context_chunks` jako domyślnego `before`/`after`, zamień hex na tokeny, dodaj `functools.cache` do `load_prompt`/`prompt_versions`; limit żądań zapisz jako wymaganie przed publicznym demo.
- **Decision**: FIXED

## Triage (2026-11-25)

Wszystkie ustalenia naprawione (decyzja użytkownika: „Napraw teraz” dla F1–F10).

- **F1**: `answers.py` liczy termin `asyncio.timeout_at(deadline)` tylko wokół `anext(stream)`, `yield` jest poza blokiem, a strumień grafu zamyka `aclose()` w `finally`. Nowy test `test_answer_deadline_saves_failed_row_and_sends_error` (wolny fałszywy model, `ANSWER_DEADLINE_S=0.5`).
- **F2**: komentarze w `settings.py` i `.env.example` mówią, że `none` wyłącza, a pusta wartość daje `low`; `model.py` bez martwej ścieżki `effort or None`; compose domyślnie `low`.
- **F3**: panele `w-[min(400px,45%)]` / `w-[min(420px,45%)]` z `min-w-[300px]`, wątek `px-6 xl:px-10`. Sprawdzone w przeglądarce przy 1024 px (panel sprawdzonych fragmentów i okno dowodu) i 1280 px.
- **F4**: `nodes.py` bierze połączenie z `timeout=CONNECTION_TIMEOUT_S`.
- **F5**: aneks w planie; `.env.example` ma domyślnie Gemini `gemini-3.5-flash-lite` z `low`, a OpenAI i OpenRouter jako zakomentowane warianty.
- **F6**: reguła dopisana w aneksie planu.
- **F7**: aneks w planie; nieużywany parametr `retrieved_chunk_ids` usunięty z `run_config` i testu.
- **F8**: widoczny podpis „Rola nie jest kontrolą dostępu” / „Role is not access control” (`header.roleNoticeShort`), podpięty przez `aria-describedby`; nagłówek mieści się przy 1280 px.
- **F9**: `http_connection` i `CONNECTION_TIMEOUT_S` w `app/db.py`, `SettingsDep` w `app/settings.py`; `evidence.py` używa `SettingsDep`, a 404 korpusu ma stały komunikat.
- **F10**: `before`/`after` bez parametru biorą `EVIDENCE_CONTEXT_CHUNKS` (kontrakt odświeżony); hex zastąpione tokenami (`--color-secondary`, `--color-icon`, `text-success`, `text-primary`, `fill-text`, `stroke-accent`; zostały dwa jednorazowe: `#eef2fc`, `#6b7078`); prompty czytane raz (`functools.cache`); limit żądań dopisany do `docs/przeplyw-danych.md` jako wymaganie przed publicznym demo.

Bramki po poprawkach: backend `ruff`, `ruff format --check`, `mypy`, `pytest` (200 passed, 1 skipped, 2 deselected); frontend `lint`, `format:check`, `typecheck`, `build`; `backend/openapi.json` i `frontend/app/api/schema.d.ts` wygenerowane ponownie.
