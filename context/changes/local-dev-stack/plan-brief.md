# Lokalne środowisko z bazą i automatycznymi sprawdzeniami (F-01) — skrót planu

> Pełny plan: `context/changes/local-dev-stack/plan.md`

## Co i dlaczego

Element F-01 z roadmapy. Daje powtarzalne środowisko, na którym powstanie import TechQA (S-01) i pierwszy przepływ „pytanie → odpowiedź z dowodem albo abstencja” (S-02): bazę z prawdziwym BM25 i wektorami, kontrakt API między backendem a frontendem oraz CI, które pilnuje jakości od pierwszego commita.

## Punkt wyjścia

Mamy tylko szablony z generatorów. `backend/main.py` wypisuje „Hello”, a obraz frontendu uruchamia serwer SSR, który w trybie SPA nie istnieje. Nie ma gita, Compose, testów, linterów ani CI.

## Stan docelowy

- `docker compose up` uruchamia ParadeDB z pg_search i pgvector oraz backend, którego `/api/health` sprawdza bazę.
- Frontend generuje typy z `openapi.json` i ma obraz nginx z buildem SPA.
- Kod jest w publicznym repo GitHub, bez materiałów kursu, z zielonym CI.

## Kluczowe decyzje

| Decyzja | Wybór | Dlaczego | Źródło |
| --- | --- | --- | --- |
| Wersja Pythona | Zostaje 3.14 | Cały docelowy zestaw (LangGraph, langfuse, psycopg) rozwiązuje się z gotowymi wheelami | Plan (sprawdzone `uv pip compile`) |
| Obraz bazy | `paradedb/paradedb:0.27.0-pg18`, przypięty | Najnowsze wydanie, PostgreSQL 18; pgvector potwierdza test | Plan |
| Lint i format | Ruff + mypy strict; ESLint + Prettier | Najpopularniejsze i najlepiej znane agentom | Użytkownik |
| Typy API | `openapi-typescript` + `openapi-fetch` | Najmniej zależności, bez generowanego kodu runtime, łatwa kontrola w CI | Użytkownik |
| Frontend lokalnie | `npm run dev` na hoście; obraz nginx w Compose pod profilem `web` | Szybki HMR na Windows i gotowy obraz SPA pod demo | Użytkownik |
| Repo | Publiczne na GitHubie | Portfolio, darmowe Actions | Użytkownik |
| Skille kursu | Wykluczone z repo (`.claude/skills/`, `.agents/`, `skills-lock.json`) | Nie publikujemy materiałów kursu ani cudzych skilli | Użytkownik |
| Kontrakt API | Commitowany `backend/openapi.json` i `schema.d.ts`; CI sprawdza ich aktualność | Zmiana API bez regeneracji typów nie przejdzie | Plan |

## Zakres

**W zakresie:**
- Compose z bazą, backendem i (pod profilem) frontendem;
- `/api/health` z testami;
- eksport OpenAPI i typowany klient;
- lint, typy i testy w obu częściach;
- przegląd przed publikacją, publiczne repo i CI;
- aktualizacja AGENTS.md.

**Poza zakresem:**
- schemat domenowy i migracje;
- import danych;
- Langfuse;
- instalacja LangGraph i LangChain;
- wdrożenie;
- frontend dev w kontenerze;
- E2E/Playwright.

## Podejście

Od dołu: baza → backend (prefiks `/api`, pula async psycopg, 503 przy niedostępnej bazie) → frontend (typy z `openapi.json`, proxy `/api` w Vite i w nginx) → git, CI i publikacja. CI ma trzy zadania:
- **backend:** z usługą ParadeDB;
- **frontend:** lint, typy i build;
- **contract:** regeneracja kontraktu bez różnic.

## Fazy

| Faza | Co dostarcza | Główne ryzyko |
| --- | --- | --- |
| 1. Baza w Compose | ParadeDB z rozszerzeniami, zapis wersji | Init obrazu inny niż zakładany; skrypt `IF NOT EXISTS` to łagodzi |
| 2. Backend | `/api/health`, testy, ruff/mypy, obraz, `openapi.json` | Niedeterministyczny eksport OpenAPI dający fałszywe różnice w CI |
| 3. Frontend | Typowany klient, ESLint/Prettier, obraz nginx SPA | Zależności serwerowe React Router mogą być wymagane przez build |
| 4. Git, CI i publikacja | `.gitignore`, przegląd, workflow, publiczne repo | Trwała publiczna historia; przegląd i zgoda przed pierwszym commitem |

**Warunki wstępne:** działający Docker Desktop, `gh` zalogowany (spełnione).
**Szacowany nakład:** ~2 sesje w 4 fazach.

## Otwarte ryzyka i założenia

- Licencja TechQA może nie pozwalać na publikację cytatów z `docs/`. Sprawdzamy to w przeglądzie fazy 4, a decyzja należy do użytkownika.
- Publiczne commity ujawniają `user.email`. Użytkownik wybiera adres przed pierwszym commitem.
- Utworzenie repo i push wymagają jawnego potwierdzenia w czacie w trakcie implementacji.

## Kryteria sukcesu (skrót)

- Jedno polecenie Compose daje działającą bazę z obydwoma rozszerzeniami i zdrowy backend.
- Zmiana API bez regeneracji typów frontendu zatrzymuje CI.
- Publiczne repo ma zielone CI i nie zawiera skilli, danych ani sekretów.
