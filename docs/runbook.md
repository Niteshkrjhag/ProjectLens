# ProjectLens runbook

## Fresh clone

Install Python 3.12, Node.js 22, and optionally Docker Desktop. From the
repository root, run one command:

```bash
./scripts/bootstrap.sh
```

The script creates `.venv`, installs the pinned backend/dev dependencies, and
installs the locked frontend dependencies. It does not create or read `.env`.

## No-key proof

```bash
PYTHONPATH=backend/src .venv/bin/python -m projectlens.cli demo \
  --source "testing dataset/simple/general" \
  --state-dir data/dry-run \
  --approve-all
```

This uses SQLite and local deterministic embeddings. It does not call Gemini,
Ollama, Supabase, or PostgreSQL.

## Local web review

Run the API and frontend in separate terminals:

```bash
PROJECTLENS_STORAGE_URL=sqlite:///./data/projectlens.db \
PYTHONPATH=backend/src .venv/bin/uvicorn projectlens.api:app --reload --port 8000
npm --prefix frontend run dev
```

Open `http://localhost:5173`, choose Demo for the synthetic stakeholder
workspace, then inspect Activity, ask a source question, and approve/reject the
human-gate items.

## Supabase/PostgreSQL

Copy `.env.example` to `.env`. Set `DATABASE_URL` to the server-side Supabase
pooler connection string and set `PROJECTLENS_STORAGE_URL` to that same URL for
the application. Set `SUPABASE_URL` and `SUPABASE_SECRET_KEY` for Supabase
management-side integration. The secret key is not the database password.

To enable provider verification, set `PROJECTLENS_LLM_MODE=live`, provide a
Gemini or Ollama Cloud key, and choose `PROJECTLENS_LLM_PROVIDER=gemini`,
`ollama`, or `auto`. Configure Gemini rates only if a spend estimate is wanted.
Ollama token usage is retained, but cost is labeled provider-unreported when
the API does not return pricing.

## Verification commands

```bash
PYTHONPATH=backend/src .venv/bin/python -m pytest -q
npm --prefix frontend run build
docker compose config
```

Live integration tests are opt-in because they can consume quota:

```bash
PROJECTLENS_RUN_LIVE_TESTS=1 PYTHONPATH=backend/src .venv/bin/pytest -m live -q
```

## Recovery operator path

1. Read `GET /runs/{run_id}` or call MCP `get_run`.
2. If the run is paused, call `resume_run`; if a stage failed, call
   `retry_run`.
3. Review every pending item with the FastAPI review endpoint or the matching
   MCP approve/reject tool.
4. Confirm `status=committed` and inspect the deliverable's citations, hash,
   events, cost, and elapsed time.
5. For new files, call the watch scan endpoint/tool and confirm the incremental
   run reports changed paths and preserves unaffected sections.
