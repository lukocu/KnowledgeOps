# Backend

FastAPI, Python 3.14, zależności przez `uv`. Ogólny opis i uruchomienie: `../README.md`.

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
