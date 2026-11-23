# KnowledgeOps Assistant

Projekt portfolio: asystent dla konsultanta help desku i redaktora wiedzy.

- **Konsultant** zadaje pytanie i dostaje odpowiedź z cytatami albo informację, że brakuje dowodów (RAG).
- **Redaktor wiedzy** sprawdza notatki z rozwiązanych zgłoszeń względem dokumentacji. System ocenia, a decyzję zawsze podejmuje człowiek.

Stan: działa lokalne środowisko (baza, backend z `/api/health`, szkielet frontendu, CI). Logiki aplikacji jeszcze nie ma.

## Stos

- Backend: FastAPI, Python 3.14, `uv`, psycopg 3.
- Baza: [ParadeDB](https://www.paradedb.com/) (`pg_search` z BM25 i `pgvector`) w Dockerze.
- Frontend: React Router w trybie SPA, TypeScript, Tailwind, `npm`. Typy API są generowane z `backend/openapi.json`.

## Uruchomienie lokalne

Wymagane: Docker, `uv`, Node 24.

```powershell
Copy-Item .env.example .env
docker compose up -d db backend
curl http://127.0.0.1:8000/api/health
```

Frontend z odświeżaniem na żywo (proxy `/api` do backendu):

```powershell
cd frontend
npm ci
npm run dev
```

Obraz SPA z nginx: `docker compose --profile web up -d --build`, strona pod `http://localhost:8080`.

Skrypty z `db/init/` wykonują się tylko na pustym wolumenie bazy, więc nowe rozszerzenia dodawaj migracją. `docker compose down -v` kasuje wolumen razem z danymi.

## Kontrole jakości

```powershell
cd backend
uv sync
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest
```

```powershell
cd frontend
npm run lint
npm run format:check
npm run typecheck
npm run build
```

Po zmianie API: `cd backend; uv run python scripts/export_openapi.py`, potem `cd frontend; npm run api:types`. CI zatrzymuje zmianę, w której kontrakt nie został odświeżony.

## Import TechQA

Import wczytuje migawkę TechQA do bazy: dokumenty, deduplikację i fragmenty (`sections-v1`) z indeksami BM25 i tsvector. Dane nie należą do repozytorium (`/data/` jest w `.gitignore`).

Wymagany układ `data/raw/techqa/`:

```text
data/raw/techqa/
  README.md
  train.json
  corpus.zip
  revision.txt
```

Manifest w kodzie (`backend/app/techqa/manifest.json`) sprawdza SHA-256 plików `README.md`, `train.json` i `corpus.zip` oraz zgodność rewizji z `revision.txt`. Przy niezgodności import kończy się błędem, a baza zostaje bez zmian.

Polecenia w Compose (baza musi działać: `docker compose up -d db`):

```powershell
docker compose run --rm backend python -m app.cli migrate
docker compose run --rm backend python -m app.cli import-techqa
docker compose run --rm backend python -m app.cli search "restarting the server" --method bm25
docker compose run --rm backend python -m app.cli search "restarting the server" --method fts --k 5
```

Po zmianie kodu backendu przebuduj obraz: `docker compose build backend`.

Import jest idempotentny: ponowne uruchomienie zastępuje poprzedni stan w jednej transakcji i porównuje hash stanu z poprzednim importem.

Wynik pierwszego pełnego importu:

- 28 481 dokumentów, w tym 28 478 kanonicznych (dwie grupy duplikatów);
- 105 450 fragmentów (mediana 3 na dokument, maksimum 159);
- etap zapisu ok. 22 s, cały import ok. 27 s;
- `state_sha256`: `3981ae29e8406ad9fbb59591d77f5babee768f733d76ca0ac35b26f0414b8eb9`.

## Dane

Planowany korpus to [NVIDIA TechQA-RAG-Eval](https://huggingface.co/datasets/nvidia/TechQA-RAG-Eval) (licencja Apache 2.0 według karty zbioru). Dane są pobierane lokalnie i nie należą do repozytorium.

`pg_search` jest na licencji AGPL; warto o tym pamiętać przy ewentualnym udostępnianiu usługi.
