# ProjectLens

Initial full-stack foundation for a FastAPI + LangGraph + PostgreSQL/pgvector + React/TypeScript application, using Gemini 3.5 Flash and Ollama Cloud's `gpt-oss:120b`.

## Local setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt

cp .env.example .env
docker compose up -d postgres

cd frontend
npm install
npm run build
```

The backend dependency versions are pinned in `backend/pyproject.toml`; frontend versions are pinned in `frontend/package.json`. `mcp` provides the Python MCP interface and `@modelcontextprotocol/sdk` provides the TypeScript MCP SDK.

## Model configuration

Supabase is configured with `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, and `DATABASE_URL`. Put the Supabase Postgres pooler or direct connection string in `DATABASE_URL`; the backend uses it for application queries and LangGraph/Postgres checkpoint persistence. The secret key is loaded only from `.env` and is never logged or committed.

The Google GenAI SDK uses `GEMINI_API_KEY` and `GEMINI_MODEL=gemini-3.5-flash`. Ollama Cloud uses `OLLAMA_API_KEY`, `OLLAMA_HOST=https://ollama.com`, and `OLLAMA_MODEL=gpt-oss:120b-cloud`. Create the Ollama key in your Ollama account; do not commit `.env`.

Ollama Cloud requires authentication and the model must be available to the account. The direct cloud API endpoint is `https://ollama.com/api/chat`, using model `gpt-oss:120b`. The `gpt-oss:120b-cloud` name is for requests routed through a local Ollama installation.

## Test layout

Tests are organized as `test/<feature-or-function>/scripts/<test_script>.py`. Current areas include `model_providers` and `document_processing`; add new feature folders under `test/` as the project grows.
