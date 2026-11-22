<!-- IMPL-REVIEW-REPORT -->

# Implementation Review: Lokalne środowisko z bazą i automatycznymi sprawdzeniami (F-01)

- **Plan**: context/changes/local-dev-stack/plan.md
- **Scope**: Full plan
- **Reviewed phases**: 1, 2, 3, 4
- **Date**: 2026-11-22
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 5 warnings, 3 observations

## Verdicts

| Dimension           | Verdict |
| ------------------- | ------- |
| Plan Adherence      | PASS    |
| Scope Discipline    | PASS    |
| Safety & Quality    | WARNING |
| Architecture        | PASS    |
| Pattern Consistency | WARNING |
| Success Criteria    | PASS    |

Success criteria run during review: ruff check, ruff format --check, mypy, pytest (3 passed incl. db test with DATABASE_URL from .env), eslint, prettier --check, typecheck, build (only build/client), nginx container: /api/health 200 ok, SPA fallback 200. CI was green for 1811a8f. Minor plan deviations (harmless): `POSTGRES_PORT=5433` in .env.example, `httpx` dev dependency, `--no-install-project` in the backend Dockerfile, `tests` in backend/.dockerignore, `setup-uv` pinned to a full version (no floating major tag exists).

## Findings

### F1 — Health check: no query timeout, errors swallowed, pool without connect timeout

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: backend/app/main.py:42-46, backend/app/db.py
- **Detail**: `timeout` in `pool.connection(timeout=...)` covers only pool checkout, not `SELECT 1` on a stalled connection. `except Exception` returns 503 with no log, so bad credentials and a real outage look the same. The pool has no `connect_timeout` or connection check.
- **Fix**: Log the failure (`logger.warning(..., exc_info=True)`), wrap the query in `asyncio.timeout`, set `kwargs={"connect_timeout": 5}` and `check=AsyncConnectionPool.check_connection` in the pool.
- **Decision**: FIXED

### F2 — Containers run as root, backend has no healthcheck

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: backend/Dockerfile, frontend/Dockerfile, docker-compose.yml
- **Detail**: Backend runs as root in the uv builder image; frontend uses the regular nginx image. Compose has no backend healthcheck, so `frontend` waits only for start, not readiness.
- **Fix A ⭐ Recommended**: Add a non-root `USER` to the backend and a Python-based compose healthcheck on `/api/health`; leave nginx as is for now.
  - Strength: Small change, gives a real readiness signal.
  - Tradeoff: Frontend stays on the root-master nginx image (workers are unprivileged).
  - Confidence: HIGH — standard pattern.
  - Blind spot: File permissions for `.venv` after switching user are not yet tested.
- **Fix B**: Also switch the frontend to `nginxinc/nginx-unprivileged`.
  - Strength: Fully non-root.
  - Tradeoff: Different port and base image to maintain; local-only stack gains little.
  - Confidence: MED
  - Blind spot: nginx.conf paths may differ.
- **Decision**: FIXED via Fix A (backend USER 10001, healthcheck in Compose; frontend depends_on service_healthy)

### F3 — nginx /api proxy: no timeouts, no forwarded headers, name resolved once

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: frontend/nginx.conf:6-10
- **Detail**: Default 60 s read timeout and buffering will hurt later LLM or streaming responses; `backend` is resolved at nginx startup, so recreating the backend container gives 502 until nginx restarts.
- **Fix A ⭐ Recommended**: Defer to S-02, when the first long or streaming route appears; note it in the roadmap.
  - Strength: No speculative config; nothing in F-01 is streaming.
  - Tradeoff: Easy to forget.
  - Confidence: HIGH — the nginx image is only the optional `web` profile.
  - Blind spot: Whether the final deployment even uses this nginx.
- **Fix B**: Add `proxy_read_timeout`, `X-Forwarded-Proto` and `resolver 127.0.0.11` with a variable upstream now.
  - Strength: Removes the 502-after-recreate annoyance immediately.
  - Tradeoff: Guessing values before real routes exist.
  - Confidence: MED
  - Blind spot: Streaming needs `proxy_buffering off` on specific routes only.
- **Decision**: ACCEPTED via Fix A: deferred to S-02, no code change

### F4 — CI: actions pinned to tags, no concurrency, duplicate runs

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: .github/workflows/ci.yml:3-5, 33-34, 52-53, 67-69
- **Detail**: The plan asked for major-release pins, which is what was done (setup-uv is an exact version). Pinning to commit SHAs is safer supply-chain practice, and `push` plus `pull_request` runs jobs twice for same-repo PR branches.
- **Fix**: Add `concurrency` with `cancel-in-progress` and limit `push` to `main`; optionally move to SHA pins with Dependabot.
- **Decision**: FIXED (concurrency + push only on main; SHA pins not done)

### F5 — Vite proxy defaults to `localhost`, contrary to the 127.0.0.1 rule

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: frontend/vite.config.ts:12
- **Detail**: The plan used `http://localhost:8000`, but AGENTS.md and the repo convention say `localhost` is slow on Windows because of IPv6. Everything else uses 127.0.0.1.
- **Fix**: Default to `http://127.0.0.1:8000`.
- **Decision**: FIXED

### F6 — `getHealth` accepts any error body as a health response

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: frontend/app/api/client.ts:12-18
- **Detail**: For a 502 HTML page or a 422, `error` is not a `HealthResponse` but is cast as one.
- **Fix**: Destructure `response` and accept the body only for status 200 or 503.
- **Decision**: FIXED

### F7 — Template `root.tsx` still has `lang="en"`, English strings and Google Fonts

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Scope Discipline
- **Location**: frontend/app/root.tsx:14-28
- **Detail**: The plan excluded visual changes, so this is expected, but the product is Polish. Fonts are loaded from a third party at runtime.
- **Fix**: Handle it with the first real screen (S-02/S-03): `lang="pl"`, Polish copy, self-hosted font.
- **Decision**: FIXED (lang=pl, Polish error strings; Google Fonts left for the first real screen)

### F8 — Init script runs only on an empty volume; `down -v` wipes data

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: docker-compose.yml:12, db/init/01-extensions.sql, README.md
- **Detail**: A new extension added to the init script will not appear on an existing volume (CI runs it by hand, which masks this). `docker compose down -v` deletes the database.
- **Fix**: Add one line to the README about `down -v`; treat later schema changes as migrations (S-01).
- **Decision**: FIXED
