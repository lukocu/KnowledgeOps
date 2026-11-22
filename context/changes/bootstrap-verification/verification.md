---
bootstrapped_at: 2026-11-22T19:59:57Z
starter_id: custom
starter_name: "FastAPI (backend/) + React Router SPA (frontend/) + ParadeDB Postgres, one repository"
project_name: knowledgeops-assistant
language_family: multi
package_manager: uv (backend), npm (frontend)
cwd_strategy: subdir-then-move
bootstrapper_confidence: best-effort
phase_3_status: ok
audit_command: "null"
---

## Hand-off

    starter_id: custom
    custom_starter:
      name: "FastAPI (backend/) + React Router SPA (frontend/) + ParadeDB Postgres, one repository"
      docs_url: https://fastapi.tiangolo.com
    package_manager: uv
    project_name: knowledgeops-assistant
    hints:
      language_family: multi
      team_size: solo
      deployment_target: self-host
      ci_provider: github-actions
      ci_default_flow: auto-deploy-on-merge
      bootstrapper_confidence: best-effort
      path_taken: custom
      quality_override: false
      self_check_answers:
        typed: true
        from_official_starter: true
        conventions: true
        docs_current: true
        can_judge_agent: false
      has_auth: false
      has_payments: false
      has_realtime: true
      has_ai: true
      has_background_jobs: true


KnowledgeOps Assistant is a solo, 8-week, zero-cost portfolio web app with two parts: a Python backend for RAG, data import and evaluations, and a TypeScript frontend. FastAPI was picked for the backend because it has typed Pydantic contracts, an OpenAPI spec that gives the frontend its TypeScript types, and native streaming; it passes all four agent-friendly gates. React Router in SPA mode was picked for the frontend: it has file-based route conventions, needs no second server next to FastAPI, and is verified for scaffolding. Real BM25 is a requirement, and hosted Supabase has no BM25 extension, so the database is ParadeDB Postgres (pg_search plus pgvector) running in Docker. That keeps BM25, vector and hybrid retrieval in one database. Everything runs locally in Docker Compose (`self-host`); public hosting is deferred. The two frameworks live in two folders, with no monorepo tooling. Scaffolding is best-effort: bootstrapper runs the official FastAPI (uv) and create-react-router generators. Usage of LangGraph, LangChain and Langfuse is in `context/foundation/architecture-notes.md`.

## Pre-scaffold verification

| Signal | Value | Severity | Notes |
| --- | --- | --- | --- |
| npm package | create-react-router v8.5.2 published 2026-11-18 | fresh | frontend generator |
| GitHub repo | remix-run/react-router last pushed 2026-11-20 | fresh | |
| GitHub repo | fastapi/fastapi last pushed 2026-11-18 | fresh | docs_url of custom starter |
| GitHub repo | astral-sh/uv last pushed 2026-11-22 | fresh | backend generator (uv 0.10.5 local) |

Local toolchain: uv 0.10.5, Node v24.13.0, npm 11.6.2.

## Scaffold log

**Resolved invocation**:
1. `uv init .bootstrap-scaffold/backend --app --name knowledgeops-backend --vcs none && cd .bootstrap-scaffold/backend && uv add "fastapi[standard]"`
2. `npx --yes create-react-router@latest .bootstrap-scaffold/frontend --yes --package-manager npm --no-git-init --no-agent-skills`
3. Manual edit: `frontend/react-router.config.ts` set to `ssr: false` (SPA mode, per React Router docs "how-to/spa").

**Strategy**: subdir-then-move (both folders moved up as a whole)
**Exit code**: 0 (both generators)
**Files moved**: backend/ (5 files + .venv), frontend/ (17 files + node_modules)
**Conflicts (.scaffold siblings)**: none (backend/ and frontend/ did not exist)
**.gitignore handling**: root .gitignore untouched; frontend/ keeps its own .gitignore
**.bootstrap-scaffold cleanup**: deleted

Post-move checks: `uv sync` OK (fastapi 0.165.0, Python 3.14.3 picked by uv; `requires-python = ">=3.14"`). `npm run typecheck` OK. `npm run build` OK, "SPA Mode: Generated build/client/index.html".

Notes:
- `frontend/Dockerfile` from the template targets the SSR server (`react-router-serve`); with SPA mode it needs adjusting before Docker Compose.
- Not created by generators: `docker-compose.yml` (ParadeDB, Langfuse), FastAPI app structure (`backend/main.py` is a uv hello-world), OpenAPI type generation, CI workflow.

## Post-scaffold audit

**Tool**: skipped — no built-in audit tool for multi
**Recommended external tool**: `npm audit` in frontend/, `pip-audit` (e.g. `uvx pip-audit`) in backend/

Additional informational run: `npm audit --json` in frontend/ → 0 CRITICAL, 0 HIGH, 0 MODERATE, 0 LOW. Backend not audited.

## Hints recorded but not acted on

| Hint | Value |
| --- | --- |
| bootstrapper_confidence | best-effort |
| quality_override | false |
| path_taken | custom |
| self_check_answers | typed: true, from_official_starter: true, conventions: true, docs_current: true, can_judge_agent: false |
| team_size | solo |
| deployment_target | self-host |
| ci_provider | github-actions |
| ci_default_flow | auto-deploy-on-merge |
| has_auth | false |
| has_payments | false |
| has_realtime | true |
| has_ai | true |
| has_background_jobs | true |

## Next steps

Next: a future skill will set up agent context (CLAUDE.md, AGENTS.md). For now, your project is scaffolded and verified — happy hacking.

Useful manual steps in the meantime:
- `git init` (if you have not already) to start your own repo history.
- Review any `.scaffold` siblings the conflict policy created and decide which version of each file to keep.
- Address audit findings per your project's risk tolerance — the full breakdown is in this log.
