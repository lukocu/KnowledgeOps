# Lokalne środowisko z bazą i automatycznymi sprawdzeniami (F-01) — plan implementacji

## Overview

F-01 z roadmapy (`context/foundation/roadmap.md`). Cel: powtarzalne środowisko, na którym da się zbudować import TechQA (S-01) i pierwszy przepływ pytania (S-02). Po zmianie:

- ParadeDB działa w Docker Compose z rozszerzeniami pg_search i pgvector.
- Backend FastAPI ma kontrolę stanu i specyfikację OpenAPI.
- Frontend generuje z tej specyfikacji typowanego klienta i ma obraz pod tryb SPA.
- Repozytorium jest publiczne na GitHubie z zielonym CI.

## Current State Analysis

- Repozytorium nie jest w git. Nie ma `docker-compose.yml`, CI, testów ani linterów (AGENTS.md:54).
- `backend/main.py` to szablon z generatora uv (`print("Hello…")`), bez aplikacji FastAPI. Zależność to tylko `fastapi[standard]>=0.165.0` (`backend/pyproject.toml`), a `requires-python = ">=3.14"`.
- `frontend/` to szablon React Router 8.5.2 z `ssr: false` (`frontend/react-router.config.ts:5`).
- `frontend/Dockerfile` i skrypt `start` uruchamiają `react-router-serve ./build/server/index.js`. W trybie SPA ten katalog nie powstaje (powstaje tylko `build/client/`), więc obraz z generatora jest niespójny z naszym trybem.
- `.gitignore` wyklucza `.env*` (poza `.env.example`), `/data/` (206 MB), `node_modules/`, `build/` i `.venv/`. Nie wyklucza `.claude/skills/`, `.agents/` ani `skills-lock.json`.
- Narzędzia na maszynie: Docker 29.1.5, Compose v5.0.1, uv 0.10.5, Node 24.13.0, `gh` 2.92.0 (zalogowany).

### Key Discoveries

- **Python 3.14 zostaje.** `uv pip compile` dla Linux x86_64 i Pythona 3.14 rozwiązuje cały zestaw z gotowymi wheelami. Rozstrzyga to pytanie z roadmapy (Unknowns F-01 i Open Roadmap Question 15). Sprawdzone pakiety:
  - `langgraph` 1.2.24;
  - `langgraph-checkpoint-postgres` 3.2.1;
  - `langchain-core` 1.8.4;
  - `langfuse` 5.2.0;
  - `psycopg[binary,pool]` 3.3.9;
  - `pydantic` 2.14.4;
  - `ruff` 0.17.6;
  - `mypy` 2.4.1.
- **Obraz ParadeDB:** `paradedb/paradedb:0.27.0-pg18` (Docker Hub, 2026-11-19). Obecność pgvector potwierdzimy testem, bo obraz nie był jeszcze pobierany.
- Skrypty w `/docker-entrypoint-initdb.d` wykonują się tylko na pustym wolumenie. Obraz ParadeDB może sam tworzyć rozszerzenia, dlatego nasz skrypt używa `CREATE EXTENSION IF NOT EXISTS`.

## Desired End State

- `docker compose up -d db backend` uruchamia bazę i backend. `GET http://localhost:8000/api/health` zwraca 200 z informacją, że baza odpowiada.
- Test integracyjny potwierdza, że w bazie są rozszerzenia `pg_search` i `vector`. Wersje PostgreSQL, pg_search i pgvector są zapisane w `architecture-notes.md`.
- `npm run api:types` generuje `frontend/app/api/schema.d.ts` z `backend/openapi.json`, a typowany klient kompiluje się w `npm run typecheck`.
- `docker compose --profile web up` serwuje zbudowane SPA przez nginx z proxy `/api` do backendu.
- Publiczne repo na GitHubie, bez skilli kursu i bez sekretów, z zielonym workflow CI:
  - lint, format, typy i testy backendu z bazą;
  - lint, typy i build frontendu;
  - kontrola, że `openapi.json` i typy są aktualne.
- AGENTS.md opisuje faktyczne polecenia i konwencję commitów.

## What We're NOT Doing

- Schematu domenowego, migracji (narzędzie migracji wybierze S-01) i importu danych.
- Langfuse lokalnie ani w chmurze. Wchodzi w S-02.
- LangGraph i LangChain w zależnościach. Sprawdziliśmy tylko zgodność z Pythonem 3.14; instalują je etapy, które ich używają.
- Wdrożenia, hostingu i auto-deployu (Open Roadmap Question 14).
- Frontendu w kontenerze w trybie deweloperskim. Na co dzień `npm run dev` działa na hoście.
- Testów E2E i Playwright. Dochodzą z pierwszym ekranem (S-02/S-03) przez `/10x-e2e-setup`.
- Zmian w wyglądzie strony startowej poza tym, czego wymaga usunięcie zależności serwerowych.

## Implementation Approach

Od dołu do góry: baza → backend (zależy od bazy) → frontend (zależy od `openapi.json`) → git, CI i publikacja (sprawdza wszystko razem).

- Ścieżki API mają prefiks `/api`, więc proxy w Vite i w nginx to jedna reguła.
- Plik `backend/openapi.json` jest commitowany jako kontrakt. CI regeneruje go razem z typami i kończy się błędem, jeśli coś się różni.
- Publikacja jest ostatnim krokiem i wymaga potwierdzenia użytkownika w czacie: `gh repo create --public` to działanie zewnętrzne, trudne do odwrócenia.

## Critical Implementation Details

- **Kolejność publikacji.** Najpierw `.gitignore` i przegląd plików przed pierwszym commitem. Publiczna historia git jest trwała, a pliku usuniętego w późniejszym commicie nie usuwa się z historii.
- **Adres e-mail w commitach.** Publiczne commity pokazują `user.email` z konfiguracji git. Przed pierwszym commitem użytkownik decyduje, czy użyć adresu `noreply` GitHuba. To krok ręczny i plan nie zmienia konfiguracji git.
- **Usługa `postgres` w CI.** Workflow uruchamia obraz ParadeDB jako `services`. Skrypt inicjalizujący z repo nie jest tam montowany, więc rozszerzenia tworzy krok `psql` przed testami albo fixture testu tym samym SQL. Test ma sprawdzać to samo co lokalnie.

## Phase 1: Baza w Compose

### Overview

ParadeDB jako usługa `db` z przypiętą wersją, rozszerzeniami, healthcheckiem i zmiennymi z `.env`.

### Changes Required

#### 1. Plik Compose

**File**: `docker-compose.yml`

**Intent**: Definiuje usługę `db` z obrazu ParadeDB, z trwałym wolumenem i healthcheckiem, aby kolejne usługi mogły czekać na gotową bazę.

**Contract**:
- Usługa `db`: obraz `paradedb/paradedb:0.27.0-pg18`.
- Zmienne `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` z `.env`, z wartościami domyślnymi do pracy lokalnej.
- Port `127.0.0.1:5432:5432` (tylko localhost).
- Nazwany wolumen danych.
- Healthcheck `pg_isready`.
- Montowanie `./db/init` do `/docker-entrypoint-initdb.d:ro`.

#### 2. Skrypt rozszerzeń

**File**: `db/init/01-extensions.sql`

**Intent**: Gwarantuje obecność `pg_search` i `vector` niezależnie od tego, co robi init obrazu.

**Contract**: `CREATE EXTENSION IF NOT EXISTS pg_search;` oraz `CREATE EXTENSION IF NOT EXISTS vector;`. Ten sam plik wykonuje CI.

#### 3. Przykładowe zmienne

**File**: `.env.example`

**Intent**: Dokumentuje zmienne bazy i backendu (`DATABASE_URL`) bez prawdziwych sekretów. Lokalny `.env` pozostaje poza repo.

**Contract**: Klucze `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `DATABASE_URL` z wartościami deweloperskimi.

#### 4. Zapis wersji

**File**: `context/foundation/architecture-notes.md` (sekcja „Baza i wyszukiwanie”)

**Intent**: Zamienia punkt „Przy bootstrapie sprawdzić…” na zapis faktów: tag obrazu, wersja PostgreSQL, pg_search i pgvector, odczytane z działającej bazy.

**Contract**: Jedna linia z wersjami w miejsce zdania o sprawdzeniu przy bootstrapie.

### Success Criteria

#### Automated Verification

- `docker compose up -d db` kończy się, a `docker compose ps db` pokazuje stan `healthy`.
- `docker compose exec db psql -U <user> -d <db> -tAc "select extname, extversion from pg_extension"` zwraca `pg_search` i `vector`.
- `docker compose exec db psql … -tAc "show server_version"` zwraca wersję 18.x.

#### Manual Verification

- Wersje zapisane w `architecture-notes.md` zgadzają się z wynikiem zapytań.

**Implementation Note**: Po weryfikacji automatycznej poczekaj na potwierdzenie użytkownika przed fazą 2.

---

## Phase 2: Backend z kontrolą stanu i OpenAPI

### Overview

Minimalna aplikacja FastAPI w pakiecie `app` z ustawieniami z env, endpointem `/api/health` sprawdzającym bazę, testami, lintem i typami, obrazem Dockera i eksportem specyfikacji OpenAPI do pliku.

### Changes Required

#### 1. Pakiet aplikacji

**File**: `backend/app/__init__.py`, `backend/app/main.py`, `backend/app/settings.py`, `backend/app/db.py`; usuwamy `backend/main.py`

**Intent**: Zastępuje szablon generatora aplikacją FastAPI.
- Ustawienia przez `pydantic-settings`, z `DATABASE_URL` jako jedynym wymaganym polem.
- Dostęp do bazy przez async psycopg. Pula połączeń jest tworzona w `lifespan` i dostarczana jako zależność, aby testy mogły ją podmienić.

**Contract**:
- `GET /api/health` z `response_model` (np. `HealthResponse`: `status: Literal["ok","degraded"]`, `database: Literal["ok","unavailable"]`).
- Kod 200, gdy `SELECT 1` się powiedzie, a 503 z tym samym schematem, gdy baza nie odpowiada.
- Tytuł i wersja aplikacji ustawione w konstruktorze `FastAPI` (widoczne w OpenAPI).
- Każdy endpoint ma `response_model`, bo inaczej typy frontendu będą puste.

#### 2. Zależności i konfiguracja narzędzi

**File**: `backend/pyproject.toml`, `backend/uv.lock`

**Intent**: Dodaje zależności runtime i deweloperskie oraz konfigurację ruff, mypy i pytest w jednym pliku.

**Contract**:
- Runtime przez `uv add`: `psycopg[binary,pool]`, `pydantic-settings`.
- Grupa `dev` przez `uv add --dev`: `pytest`, `ruff`, `mypy`.
- `[tool.ruff]`: target py314 i zestaw reguł (co najmniej `E,F,I,B,UP`).
- `[tool.mypy]`: `strict = true`.
- `[tool.pytest.ini_options]`: marker `db` dla testów wymagających bazy.
- Opis projektu w miejsce „Add your description here”.

#### 3. Testy

**File**: `backend/tests/test_health.py`, `backend/tests/test_database.py`

**Intent**: Testy jednostkowe sprawdzają kontrakt kontroli stanu bez bazy (zależność bazy podmieniona). Test z markerem `db` łączy się z prawdziwą bazą i potwierdza obecność rozszerzeń.

**Contract**:
- `test_health`: 200 i `database == "ok"` przy działającej zależności; 503 i `database == "unavailable"`, gdy zależność rzuca wyjątek połączenia.
- `test_database` (`@pytest.mark.db`): `pg_extension` zawiera `pg_search` i `vector`.
- Testy `db` są pomijane, gdy brak `DATABASE_URL`.

#### 4. Eksport OpenAPI

**File**: `backend/scripts/export_openapi.py`, `backend/openapi.json`

**Intent**: Zapisuje `app.openapi()` do commitowanego pliku. To kontrakt dla frontendu i podstawa kontroli aktualności w CI.

**Contract**: `uv run python scripts/export_openapi.py` zapisuje `backend/openapi.json`: JSON z wcięciem 2, posortowane klucze, znak nowej linii na końcu. Format musi być deterministyczny, bo inaczej CI będzie zgłaszać fałszywe różnice.

#### 5. Obraz i usługa Compose

**File**: `backend/Dockerfile`, `backend/.dockerignore`, `docker-compose.yml`

**Intent**: Obraz backendu na oficjalnym obrazie uv z Pythonem 3.14 i usługa `backend` w Compose, czekająca na zdrową bazę.

**Contract**:
- Obraz bazowy `ghcr.io/astral-sh/uv` z Pythonem 3.14 na Debianie, z przypiętym tagiem.
- `uv sync --locked --no-dev`.
- Start przez `fastapi run app/main.py --port 8000`.
- Usługa `backend`: `depends_on: db: condition: service_healthy`, `DATABASE_URL` wskazujący host `db`, port `127.0.0.1:8000:8000`.
- `.dockerignore` wyklucza `.venv`.

### Success Criteria

#### Automated Verification

- `cd backend; uv run ruff check .` i `uv run ruff format --check .` przechodzą.
- `cd backend; uv run mypy app tests scripts` przechodzi w trybie strict.
- `cd backend; uv run pytest` przechodzi, a testy `db` przechodzą przy działającej bazie i ustawionym `DATABASE_URL`.
- `docker compose up -d --build db backend`, a `curl -fsS http://localhost:8000/api/health` zwraca 200 z `"database":"ok"`.
- Ponowne uruchomienie `export_openapi.py` nie zmienia `backend/openapi.json` (`git diff --exit-code` po fazie 4; przed gitem porównanie hashy).

#### Manual Verification

- Po `docker compose stop db` endpoint zwraca 503 z `"database":"unavailable"`, a po starcie bazy wraca do 200.
- `http://localhost:8000/docs` pokazuje endpoint z opisanym schematem odpowiedzi.

**Implementation Note**: Po weryfikacji automatycznej poczekaj na potwierdzenie użytkownika przed fazą 3.

---

## Phase 3: Frontend — typy API, lint i obraz SPA

### Overview

Typowany klient z `openapi.json`, proxy `/api` w trybie deweloperskim, ESLint i Prettier oraz obraz nginx z buildem SPA. Usuwamy ślady trybu serwerowego z generatora.

### Changes Required

#### 1. Generowanie typów i klient

**File**: `frontend/package.json`, `frontend/app/api/schema.d.ts` (generowany, commitowany), `frontend/app/api/client.ts`

**Intent**: `openapi-typescript` (dev) generuje typy, a `openapi-fetch` (runtime) daje cienkiego typowanego klienta. Typowane wywołanie health jest jedynym użyciem, które dowodzi, że kontrakt kompiluje się po stronie frontendu.

**Contract**:
- Skrypt `api:types`: `openapi-typescript ../backend/openapi.json -o app/api/schema.d.ts`.
- `client.ts` eksportuje `createClient<paths>({ baseUrl: "/" })` i funkcję `getHealth()`, która zwraca typ odpowiedzi z `paths["/api/health"]`.
- Bez hooków danych i bez TanStack Query.

#### 2. Proxy deweloperskie

**File**: `frontend/vite.config.ts`

**Intent**: `npm run dev` na hoście przekazuje `/api` do backendu, więc frontend i backend nie potrzebują CORS.

**Contract**: `server.proxy["/api"]` kieruje na `process.env.BACKEND_URL ?? "http://localhost:8000"`.

#### 3. Lint i format

**File**: `frontend/eslint.config.js`, `frontend/.prettierrc`, `frontend/.prettierignore`, `frontend/package.json`

**Intent**: ESLint w formacie flat config z `typescript-eslint` (typed linting) i `eslint-plugin-react-hooks`, plus Prettier. Pliki generowane (`schema.d.ts`, `.react-router/`, `build/`) są wyłączone z lintu i formatu.

**Contract**:
- Skrypty `lint` (`eslint .`), `format` (`prettier --write .`) i `format:check` (`prettier --check .`).
- `eslint-config-prettier` wyłącza reguły stylistyczne konfliktujące z Prettierem.

#### 4. Usunięcie trybu serwerowego

**File**: `frontend/package.json`, `frontend/app/root.tsx` (tylko jeśli importuje zależności serwerowe)

**Intent**: Usuwa skrypt `start` (`react-router-serve`) oraz zależności `@react-router/serve`, `@react-router/node` i `isbot`, o ile build SPA przechodzi bez nich. To kod nieużywany w trybie `ssr: false`.

**Contract**: `npm run build` tworzy `build/client/index.html` i nie tworzy `build/server/`. Jeśli któraś zależność okaże się wymagana przez `@react-router/dev`, zostaje, a w planie dopisujemy notatkę.

#### 5. Obraz nginx i usługa Compose

**File**: `frontend/Dockerfile`, `frontend/nginx.conf`, `frontend/.dockerignore`, `docker-compose.yml`

**Intent**: Dwuetapowy obraz: build na `node:24-alpine`, serwowanie `build/client` przez nginx z fallbackiem SPA i proxy `/api` do `backend:8000`. W Compose jako usługa `frontend` w profilu `web`, aby zwykłe `docker compose up` jej nie uruchamiało.

**Contract**:
- `nginx.conf`: `location / { try_files $uri /index.html; }` oraz `location /api/ { proxy_pass http://backend:8000; }`.
- Obraz nginx z przypiętym tagiem alpine (stabilny w dniu implementacji).
- Port `127.0.0.1:8080:80`.
- `.dockerignore` wyklucza `node_modules` i `build`.

### Success Criteria

#### Automated Verification

- `cd frontend; npm run api:types` nie zmienia commitowanego `schema.d.ts` (porównanie hashy, a po fazie 4 `git diff --exit-code`).
- `cd frontend; npm run lint`, `npm run format:check` i `npm run typecheck` przechodzą.
- `cd frontend; npm run build` tworzy `build/client/index.html` bez `build/server/`.
- `docker compose --profile web up -d --build`, a `curl -fsS http://localhost:8080/` zwraca HTML, `curl -fsS http://localhost:8080/api/health` zwraca 200, a `curl -fsS http://localhost:8080/dowolna/sciezka` zwraca `index.html` (fallback SPA).

#### Manual Verification

- `npm run dev` na hoście: strona startowa się ładuje, a w konsoli przeglądarki nie ma błędów. `http://localhost:5173/api/health` przez proxy zwraca odpowiedź backendu.

**Implementation Note**: Po weryfikacji automatycznej poczekaj na potwierdzenie użytkownika przed fazą 4.

---

## Phase 4: Git, CI i publikacja

### Overview

Repo trafia do git z przeglądem przed publikacją, dostaje workflow GitHub Actions i jest publikowane jako publiczne repo GitHub po potwierdzeniu użytkownika. AGENTS.md dostaje faktyczne polecenia.

### Changes Required

#### 1. Wykluczenia

**File**: `.gitignore`

**Intent**: Wyklucza materiały kursu i cudze skille oraz pliki lokalne, zanim cokolwiek trafi do historii.

**Contract**: Nowe wpisy:
- `.claude/skills/`, `.agents/`, `skills-lock.json`;
- `.claude/settings.local.json`;
- `frontend/.react-router/`.

Pozostała zawartość `.claude/` jest oceniana w przeglądzie (krok 2).

#### 2. Przegląd przed publikacją (bez commitu)

**File**: — (czynność; wynik w raporcie dla użytkownika)

**Intent**: Przed pierwszym commitem pokazuje użytkownikowi listę plików, które trafią do repo (`git init`, `git add --dry-run .`), sprawdza je i czeka na zgodę.

**Contract**:
- Skan wzorców sekretów (klucze API, `password=`, tokeny, adresy e-mail) w plikach do commitu.
- Potwierdzenie, że nie ma `.env`, `data/` ani skilli.
- Sprawdzenie licencji zbioru TechQA pod kątem cytatów w `docs/`. Jeśli licencja nie pozwala na redystrybucję fragmentów, użytkownik decyduje o ich skróceniu.
- Decyzja użytkownika o `user.email` (adres `noreply` GitHuba lub obecny).

#### 3. Workflow CI

**File**: `.github/workflows/ci.yml`

**Intent**: Na `push` i `pull_request` uruchamia trzy zadania.

**Contract**:
- **`backend`:**
  - `astral-sh/setup-uv`, `uv sync --locked`;
  - `ruff check`, `ruff format --check`, `mypy`;
  - `pytest` z usługą `paradedb/paradedb:0.27.0-pg18` (healthcheck i `DATABASE_URL`), a przed testami krok `psql -f db/init/01-extensions.sql`.
- **`frontend`:**
  - `actions/setup-node` (Node 24, cache npm), `npm ci`;
  - `lint`, `format:check`, `typecheck`, `build`.
- **`contract`:**
  - eksport OpenAPI i `npm run api:types`;
  - `git diff --exit-code backend/openapi.json frontend/app/api/schema.d.ts`.
- Akcje przypięte do wydań głównych.
- `permissions: contents: read`.

#### 4. Commit, repo i push

**File**: — (czynność)

**Intent**: Pierwszy commit w Conventional Commits z linią `Co-Authored-By`. Publiczne repo jest tworzone wyłącznie po jawnym „tak” użytkownika w czacie, z nazwą repo podaną w pytaniu.

**Contract**:
- `git init -b main`.
- Commit `chore: bootstrap local dev stack`.
- `gh repo create <nazwa> --public --source . --remote origin --push`.
- Bez auto-merge i bez ochrony gałęzi (poza zakresem).

#### 5. AGENTS.md i roadmapa

**File**: `AGENTS.md`, `context/foundation/roadmap.md`

**Intent**: AGENTS.md ma odpowiadać faktycznym poleceniom.
- Dochodzą Compose, lint, testy, `api:types` i konwencja commitów Conventional Commits.
- Usuwamy zdanie „Testów, lintera, `docker-compose.yml` ani CI jeszcze nie ma…”.
- W roadmapie zamykamy pytanie o Pythona 3.14 (Open Roadmap Question 15: zostaje 3.14) i wypełniamy Unknowns F-01.

**Contract**: AGENTS.md mieści się w limicie około 400 słów treści. Status elementu roadmapy zmieniają `/10x-implement` i `/10x-archive`, nie ta faza.

### Success Criteria

#### Automated Verification

- `git ls-files` nie zawiera `.env`, `data/`, `.claude/skills/`, `.agents/` ani `skills-lock.json`.
- Skan sekretów na `git ls-files` nie zwraca trafień (albo trafienia są wyjaśnione w raporcie).
- `gh run list --limit 1` pokazuje workflow `ci` ze statusem `success` dla pierwszego pusha.
- Celowe zepsucie `openapi.json` na gałęzi testowej powoduje błąd zadania `contract`. Sprawdzamy to raz, lokalnie tymi samymi poleceniami, bez pushowania zepsutego stanu.

#### Manual Verification

- Użytkownik zatwierdził listę plików i ustawienie e-maila przed pierwszym commitem.
- Użytkownik potwierdził utworzenie publicznego repo w czacie.
- Strona repo na GitHubie wygląda poprawnie (README, brak skilli i danych).

**Implementation Note**: Kroki 2 i 4 wymagają odpowiedzi użytkownika w czacie. Nie wykonuj ich na podstawie samego planu.

---

## Testing Strategy

### Unit Tests

- Kontrakt `/api/health`: przypadek 200 i 503 z podmienioną zależnością bazy.

### Integration Tests

- `@pytest.mark.db`: obecność `pg_search` i `vector` w prawdziwej bazie, lokalnie i w CI.
- Kontrola kontraktu: regeneracja `openapi.json` i typów nie daje różnic.

### Manual Testing Steps

1. `docker compose up -d db backend`, następnie `curl http://localhost:8000/api/health` → 200.
2. `docker compose stop db`, następnie `curl` → 503; `docker compose start db` → 200.
3. `docker compose --profile web up -d --build` i otwarcie `http://localhost:8080` oraz dowolnej podstrony (fallback SPA).
4. `npm run dev` i sprawdzenie proxy `/api/health` na porcie 5173.

## Performance Considerations

Brak wymagań na tym etapie. Pula połączeń psycopg ma małe limity domyślne, wystarczające dla jednego użytkownika lokalnie.

## Migration Notes

Nie dotyczy: brak danych i schematu. Zmiana obrazu ParadeDB w przyszłości wymaga nowego wolumenu albo `pg_upgrade`. Do odnotowania przy S-01, gdy pojawią się dane.

## References

- Roadmapa: `context/foundation/roadmap.md` (F-01, Open Roadmap Questions 14–15)
- Stos: `context/foundation/tech-stack.md`, `context/foundation/architecture-notes.md`
- Log bootstrapu: `context/changes/bootstrap-verification/verification.md`
- Szablony z generatorów: `frontend/Dockerfile`, `frontend/react-router.config.ts:5`, `backend/main.py`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Baza w Compose

#### Automated

- [x] 1.1 Usługa db osiąga stan healthy
- [x] 1.2 pg_extension zawiera pg_search i vector
- [x] 1.3 server_version zwraca 18.x

#### Manual

- [x] 1.4 Wersje w architecture-notes.md zgodne z bazą

### Phase 2: Backend z kontrolą stanu i OpenAPI

#### Automated

- [x] 2.1 ruff check i ruff format --check przechodzą
- [x] 2.2 mypy strict przechodzi
- [x] 2.3 pytest przechodzi, łącznie z testami db
- [x] 2.4 /api/health w Compose zwraca 200 z database ok
- [x] 2.5 Eksport OpenAPI jest deterministyczny

#### Manual

- [x] 2.6 Zatrzymana baza daje 503, po starcie wraca 200
- [x] 2.7 /docs pokazuje schemat odpowiedzi health

### Phase 3: Frontend — typy API, lint i obraz SPA

#### Automated

- [x] 3.1 api:types nie zmienia commitowanego schema.d.ts
- [x] 3.2 lint, format:check i typecheck przechodzą
- [x] 3.3 build tworzy tylko build/client
- [x] 3.4 Obraz nginx serwuje SPA, proxy /api i fallback

#### Manual

- [x] 3.5 npm run dev ładuje stronę i proxy /api działa

### Phase 4: Git, CI i publikacja

#### Automated

- [x] 4.1 git ls-files bez .env, data, skilli — e4647f8
- [x] 4.2 Skan sekretów bez niewyjaśnionych trafień — e4647f8
- [x] 4.3 Workflow ci zielony dla pierwszego pusha — e4647f8
- [x] 4.4 Kontrola kontraktu wykrywa nieaktualny openapi.json — e4647f8

#### Manual

- [x] 4.5 Użytkownik zatwierdził listę plików i e-mail — e4647f8
- [x] 4.6 Użytkownik potwierdził utworzenie publicznego repo — e4647f8
- [x] 4.7 Strona repo na GitHubie wygląda poprawnie — e4647f8
