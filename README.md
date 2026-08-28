# ProjectLens

ProjectLens is an agentic document analyst for a synthetic Atlas migration
portfolio. It accepts mixed project evidence, extracts grounded facts, keeps
contradictions visible, examines a rules layer, pauses for human decisions,
and commits a cited project brief. The default path is deterministic and
offline-testable; Gemini 3.5 Flash and Ollama Cloud GPT OSS 120B are opt-in
verification providers.

## What is implemented

```text
upload/watch folder
        ↓
discover → extract → reconcile → draft → examine → human_gate → commit
        ↓          ↓          ↓        ↓          ↓           ↓
 hashes     claims+chunks conflicts  brief    findings  approve/reject
```

Each stage is a LangGraph node and writes durable status, attempt, decision,
timing, cost, and events before the next stage runs. A restart recovers
incomplete work and skips completed stages. Provider failures record a
fallback event instead of losing deterministic evidence. Conflicts and rules
findings are reviewed one by one; approving or rejecting one item does not
discard the others.

The React review surface, FastAPI transport, and MCP server all call the same
workflow and storage services. The UI shows the stage path, activity trail,
human gate, grounded citations, total elapsed time, estimated spend, and
per-stage timing/cost.

## Fresh-clone setup

Requirements: Python 3.12, Node.js 22, and optionally Docker Desktop. From the
repository root, one command creates the environment and installs the pinned
dependencies:

```bash
./scripts/bootstrap.sh
```

The script creates `.venv`, installs `backend/requirements.txt`, and installs
the locked frontend dependencies. It does not create, print, or modify `.env`.

For the no-key proof:

```bash
PYTHONPATH=backend/src .venv/bin/python -m projectlens.cli demo \
  --source "testing dataset/simple/general" \
  --state-dir data/dry-run \
  --approve-all
```

This uses SQLite and a stable local hash embedding. It never calls a model or
external database and prints the persisted stage decisions, review decisions,
source count, and committed deliverable.

## Run the web POC

Run the API and frontend in separate terminals:

```bash
PROJECTLENS_STORAGE_URL=sqlite:///./data/projectlens.db \
PYTHONPATH=backend/src .venv/bin/uvicorn projectlens.api:app --reload --port 8000
```

```bash
npm --prefix frontend run dev
```

Open [http://localhost:5173](http://localhost:5173). The Demo tab loads the
synthetic stakeholder workspace; the normal flow lets a user create a project,
upload sources into the mandatory/optional categories, watch the analysis
stages, ask cited questions, and approve or reject review items.

## Supabase and PostgreSQL

Copy `.env.example` to `.env`. Set the server-side pooler URL in
`DATABASE_URL` and `PROJECTLENS_STORAGE_URL`. Set `SUPABASE_URL` and
`SUPABASE_SECRET_KEY` for Supabase integration. The Supabase secret key is not
the PostgreSQL password and must not be placed in the connection string.

The PostgreSQL path provisions the relational schema, a 1536-dimensional
`extensions.vector` chunk column, and a cosine HNSW index. PostgreSQL also
enables the LangGraph Postgres checkpointer. SQLite remains the zero-setup
fallback for tests and demos.

## Models, embeddings, and spend

Set `PROJECTLENS_LLM_MODE=live` to enable bounded model verification. Choose
`PROJECTLENS_LLM_PROVIDER=gemini`, `ollama`, or `auto`; `auto` prefers Ollama
Cloud when its key is present. The Gemini adapter uses `GEMINI_MODEL` and the
Google Gen AI SDK. The Ollama adapter uses `OLLAMA_HOST=https://ollama.com`
and `OLLAMA_MODEL=gpt-oss:120b-cloud` with a bearer API key.

Gemini embeddings are used in live mode when configured; offline mode uses the
stable local hash embedding. Both paths are persisted as source chunks and
retrieved by the question endpoint. Model output is advisory only: a live
response cannot create a claim without exact source evidence.

Runs report elapsed time and cost metadata. Offline/local work reports zero
cost with a `deterministic_local` basis. Gemini estimates use returned token
counts and the optional `GEMINI_INPUT_COST_PER_MILLION` and
`GEMINI_OUTPUT_COST_PER_MILLION` settings. Ollama usage is retained, but spend
is explicitly `provider_unreported` when the hosted API does not return a
price.

## Interfaces

FastAPI endpoints:

- `POST /projects` creates a workspace.
- `GET /projects` and `GET /projects/{id}/documents` inspect context.
- `POST /projects/{id}/documents` accepts Markdown, TXT, PDF, DOCX, RTF, and
  HTML.
- `POST /projects/{id}/runs` starts an initial or incremental run.
- `GET /runs/{id}` returns stages, events, sources, claims, conflicts,
  findings, review items, and the draft/committed deliverable.
- `POST /runs/{id}/pause`, `/resume`, and `/retry` control recovery.
- `POST /runs/{id}/review/{item_id}/approve` or `/reject` are explicit gate
  operations.
- `POST /projects/{id}/watch/scan` runs a focused incremental scan.
- `GET /projects/{id}/deliverable` reads the latest committed brief.
- `POST /projects/{id}/ask` answers from committed and current source context
  with citations, or explicitly refuses unsupported claims.

The MCP server runs with `python -m projectlens.mcp_server` over stdio. Its
tools cover project/source listing, ingestion, start, inspect, pause, resume,
retry, watch scan, demo bootstrap, deliverable retrieval, grounded questions,
and item-level approve/reject decisions. Background calls return immediately;
the caller polls `get_run`.

## Tests and synthetic dataset

```bash
PYTHONPATH=backend/src .venv/bin/python -m pytest -q
npm --prefix frontend run build
docker compose config
```

Tests are intentionally organized as `test/<feature-or-function>/scripts/`.
The end-to-end suite uses real temporary SQLite state and synthetic files. It
covers human-gated commits, restart recovery, pause boundaries, retry from a
failed stage, concurrent runs, prompt-injection isolation, incremental
byte-preservation, no-change scans, unsupported-answer refusal, source-aware
pre-commit Q&A, embedding retrieval, FastAPI driving, MCP driving, and
telemetry consistency.

The corpus in `testing dataset/` contains 54 unique synthetic documents across
simple, medium, complex, day-to-day, rush-day, and light-day scenarios, with
general, odd, and even modes and three versions each. It contains no real
customer, employee, vendor, or production secrets.

Live tests are opt-in because they can consume quota:

```bash
PROJECTLENS_RUN_LIVE_TESTS=1 PYTHONPATH=backend/src .venv/bin/pytest -m live -q
```

## Architecture decisions and boundaries

See [docs/architecture.md](docs/architecture.md) and
[docs/adr/0001-deterministic-vertical-slice.md](docs/adr/0001-deterministic-vertical-slice.md)
for the detailed design, trade-offs, and deliberate cuts. The runbook is in
[docs/runbook.md](docs/runbook.md).

The project proves a strong first vertical slice, not a production SaaS. It
does not claim production authentication, tenant isolation, object storage, a
scheduler daemon, streaming responses, ZIP ingestion, embedding quality
benchmarks, or a full observability platform. All fixtures are synthetic and
the human gate remains required before a deliverable is committed.

## Milestone history

Each important change is committed with what changed, why, what improved,
verification, and explicit non-claims:

- `bbdf41c` — grounded answers from uncommitted source files
- `e10fded` — persisted embeddings and pgvector-ready retrieval
- `922d1b0` — durable pause, retry, skip, escalation, and checkpoints
- `cdb5814` — incremental source changes and conflict choices
- `05ea0c4` — truthful run/stage cost and timing telemetry
- `f857fd6` — complete machine-driven MCP lifecycle
