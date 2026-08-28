# ADR 0001: deterministic vertical slice with opt-in model verification

- Status: accepted
- Date: 2026-08-28

## Context

The brief requires visible agentic stages, restart recovery, human approval,
machine control, honest grounding, concurrency, and runnable tests without a
live key. A model-only demo would make the most important behaviors expensive,
slow, and difficult to verify.

## Decision

Use LangGraph for stage orchestration and a small storage service shared by
FastAPI, MCP, and React. Use deterministic line-aware extraction as the source
of truth. Treat Gemini 3.5 Flash and Ollama Cloud GPT OSS 120B
(`gpt-oss:120b-cloud`) calls as opt-in,
bounded extraction verification advisories. Store source claims, conflicts,
findings, review decisions, deliverable versions, events, costs, and retrieval
chunks in SQLite or PostgreSQL/pgvector. Enable LangGraph Postgres checkpointing
when the configured storage is PostgreSQL.

## Why this trade-off

This buys reproducibility, zero-cost tests, clear evidence, and a reliable
fallback when a provider or network is unavailable. It costs some model
flexibility: the POC does not let a model silently invent or resolve a fact,
and semantic retrieval quality is not treated as proven merely because a
vector exists. The architecture leaves room to replace the extractor or
embedding implementation without changing the review contract.

## Rejected alternatives

- A fixed script with labels would not provide durable stage decisions,
  retries, or a machine-operable human gate.
- Making the LLM authoritative would violate the brief's no-bluff rule and
  make prompt-injection and unsupported-claim tests weak.
- A hosted-only database would make a fresh clone depend on credentials and
  network access, so SQLite is retained as the test and demo baseline.

## Consequences

Successful runs expose a real path through seven persisted stages. Unresolved
conflicts or rule findings pause the run before commit. Rejected findings do
not discard approved items, and rejected conflicts remain visible as open
questions. Live spend is reported from Gemini token usage and configured rates;
Ollama cost remains provider-unreported unless the provider supplies pricing.
