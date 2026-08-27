# ProjectLens

ProjectLens is an agentic document analyst for a synthetic Atlas migration portfolio. It accepts mixed project documents, extracts grounded facts, surfaces conflicts, checks a rules layer, pauses for item-level human decisions, and commits a cited project brief. The POC is deterministic and offline-testable by default, with an opt-in live verification path for Gemini 3.5 Flash and Ollama Cloud.

## First POC architecture

```text
documents (upload or watched folder)
        ↓
discover → extract → reconcile → draft → examine → human_gate → commit
        ↓             ↓          ↓          ↓            ↓
  file hashes    line citations  conflicts  findings   approve/reject
        └────────────── durable SQLite or Supabase/PostgreSQL state ──────┘
```

Each stage writes its status, attempt, decision, elapsed time, and event before the next stage runs. A process restart re-queues interrupted runs and skips completed stages. Conflicts and findings must be approved or rejected individually; the last decision resumes the run and commits only after the gate is clear. The MCP tools drive the same workflow as the FastAPI and React interfaces.

## Fresh-clone setup

Requirements: Python 3.12, Node.js 22, and optionally Docker Desktop.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
cd frontend && npm ci && cd ..
```

For the no-key, no-network proof:

```bash
PYTHONPATH=backend/src .venv/bin/python -m projectlens.cli demo --source "testing dataset/simple/general" --state-dir data/dry-run --approve-all
```

The command prints the project, run status, all stage decisions, review decisions, source count, and committed deliverable. It uses SQLite under the selected state directory and never calls a model.

To run the web POC locally:

```bash
PROJECTLENS_STORAGE_URL=sqlite:///./data/projectlens.db PYTHONPATH=backend/src .venv/bin/uvicorn projectlens.api:app --reload --port 8000
```

In another terminal, run `npm --prefix frontend run dev` and open http://localhost:5173. The UI creates the local Atlas workspace, uploads documents into the selected Mandatory/Optional category, starts analysis, polls the visible stages, presents the human gate, and displays citations.

To run the containerized path:

```bash
docker compose up --build
```

This starts pgvector/PostgreSQL, the API on port 8000, and the React UI on port 5173. Set `PROJECTLENS_STORAGE_URL` to your Supabase connection string when using Supabase instead of the local Postgres service. Do not commit `.env` or secret keys.

## Supabase, models, and storage

`.env.example` documents `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `DATABASE_URL`, `PROJECTLENS_STORAGE_URL`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `OLLAMA_API_KEY`, `OLLAMA_HOST`, and `OLLAMA_MODEL`. The API prefers `PROJECTLENS_STORAGE_URL`; when it is absent, it falls back to `DATABASE_URL` from `.env`.

The Postgres path initializes the POC relational tables and a `document_chunks` table with a pgvector cosine HNSW index. The offline POC uses lexical retrieval to stay deterministic and free; embeddings and vector queries are intentionally the next increment. The current report builder does not invent facts and the question endpoint explicitly returns an unsupported answer when no committed source supports the question.

To exercise the live path after filling `.env`, set `PROJECTLENS_LLM_MODE=live`. Provider selection is controlled by `PROJECTLENS_LLM_PROVIDER=auto|gemini|ollama`; `auto` prefers Ollama Cloud when its key is present. Live provider output is an advisory only: the deterministic, line-cited extractor remains authoritative and the workflow records a fallback event if a provider is unavailable. Run the external smoke tests explicitly (they can consume quota):

```bash
PROJECTLENS_RUN_LIVE_TESTS=1 PYTHONPATH=backend/src .venv/bin/pytest -m live -q
```

The Gemini adapter uses the Google Gen AI SDK and the Ollama adapter uses Ollama's hosted `https://ollama.com` API with `gpt-oss:120b`. Supabase initializes pgvector in the `extensions` schema. The application keeps lexical retrieval as the deterministic baseline; the vector table and index are ready for the embedding-backed retrieval increment.

## Interfaces

- `POST /projects` creates a workspace.
- `POST /projects/{id}/documents` uploads Markdown, text, PDF, DOCX, RTF, or HTML.
- `POST /projects/{id}/runs` starts an initial or incremental run.
- `GET /runs/{id}` returns stages, events, sources, claims, conflicts, findings, review items, and the draft/committed deliverable.
- `POST /runs/{id}/review/{item_id}/approve` and `/reject` are explicit machine/human gate operations.
- `POST /projects/{id}/watch/scan` runs a focused incremental scan over a folder.
- `POST /projects/{id}/ask` answers only from the latest committed brief.
- `python -m projectlens.mcp_server` exposes equivalent MCP tools over stdio: create project, ingest document, start run, inspect run, approve/reject review item, and ask.

## Tests and dataset

```bash
PYTHONPATH=backend/src .venv/bin/python -m pytest -q
npm --prefix frontend run build
```

Tests live under `test/<feature-or-function>/scripts/`. The end-to-end suite uses real temporary SQLite state and synthetic files. It covers a human-gated commit, restart from a persisted stage boundary, two concurrent runs, document prompt-injection isolation, incremental preservation of unaffected sections, unsupported-answer refusal, FastAPI driving, and MCP registration. The corpus in `testing dataset/` contains 54 unique synthetic documents across simple, medium, complex, day-to-day, rush-day, and light-day scenarios, with general, odd, and even modes and three versions each.

## Explicit POC boundaries

This commit sequence proves the first vertical slice, not a production SaaS. It does not claim production authentication, tenant isolation, object storage, a scheduler daemon, streaming model responses, embedding quality, full ZIP ingestion, or a production migration/observability platform. All fixtures are synthetic. The cut is intentional: a smaller deterministic path with durable stages and real gates is more useful for validating the brief than a model-shaped demo with untestable behavior.

## Commit sequence

The implementation history is organized by coherent milestones:

1. `feat: add durable grounded analysis workflow`
2. `feat: expose ProjectLens through API and MCP`
3. `feat: connect review workspace to live POC`
4. `test: prove POC safety and recovery behaviors`
5. `feat: add Supabase-ready storage path`

Each commit body records what changed, why, improvements, verification, and explicit non-claims.
