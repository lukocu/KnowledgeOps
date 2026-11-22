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

## Dane

Planowany korpus to [NVIDIA TechQA-RAG-Eval](https://huggingface.co/datasets/nvidia/TechQA-RAG-Eval) (licencja Apache 2.0 według karty zbioru). Dane są pobierane lokalnie i nie należą do repozytorium.

`pg_search` jest na licencji AGPL; warto o tym pamiętać przy ewentualnym udostępnianiu usługi.
