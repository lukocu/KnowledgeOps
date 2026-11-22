---
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
---
## Why this stack

KnowledgeOps Assistant is a solo, 8-week, zero-cost portfolio web app with two parts: a Python backend for RAG, data import and evaluations, and a TypeScript frontend. FastAPI was picked for the backend because it has typed Pydantic contracts, an OpenAPI spec that gives the frontend its TypeScript types, and native streaming; it passes all four agent-friendly gates. React Router in SPA mode was picked for the frontend: it has file-based route conventions, needs no second server next to FastAPI, and is verified for scaffolding. Real BM25 is a requirement, and hosted Supabase has no BM25 extension, so the database is ParadeDB Postgres (pg_search plus pgvector) running in Docker. That keeps BM25, vector and hybrid retrieval in one database. Everything runs locally in Docker Compose (`self-host`); public hosting is deferred. The two frameworks live in two folders, with no monorepo tooling. Scaffolding is best-effort: bootstrapper runs the official FastAPI (uv) and create-react-router generators. Usage of LangGraph, LangChain and Langfuse is in `context/foundation/architecture-notes.md`.
