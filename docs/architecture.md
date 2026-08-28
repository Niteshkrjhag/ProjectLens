# ProjectLens architecture

ProjectLens is a document-grounded analyst for a synthetic Atlas migration
portfolio. The declared input domain is software-project evidence: PRDs,
architecture notes, status reports, issues, release/security rules, and the
optional supporting document types listed in the repository. Supported source
formats are Markdown, TXT, RTF, HTML, PDF, and DOCX.

## Runtime flow

```text
upload/watch folder
        │
        ▼
discover → extract → reconcile → draft → examine → human_gate → commit
    │         │          │          │          │          │          │
    │         │          │          │          │          │          └─ versioned cited brief
    │         │          │          │          │          └─ item-level approve/reject
    │         │          │          │          └─ rule findings
    │         │          │          └─ grounded sections with claim IDs
    │         │          └─ conflicting values grouped by claim key
    │         └─ line-level claims + persisted retrieval chunks
    └─ source hash, category, and watch-change detection
```

Every stage is a LangGraph node. Stage state, attempts, decisions, errors,
timings, costs, and events are written to storage. A run has a stable
`thread_id` equal to its run ID. PostgreSQL deployments also initialize the
LangGraph Postgres checkpointer; SQLite provides the no-key deterministic test
path.

## Grounding and retrieval

The deterministic extractor remains authoritative: it only promotes facts
that have an exact source line. Live Gemini or Ollama calls are bounded
verification advisories and cannot create claims. Each source is chunked and
stored with a 1536-dimensional embedding. In live mode, Gemini embeddings are
used when configured; offline mode uses a stable local hashing embedding. The
question path combines semantic chunk retrieval with lexical/source matching,
then returns citations or an explicit unsupported answer.

Questions can preview the current source corpus before a deliverable is
committed. After commit, the committed deliverable remains the answer's
primary contract. A source document containing instructions aimed at the agent
is treated as data and recorded as an anomaly; it is never executed.

## Storage choices

- SQLite is the default for a fresh clone: zero setup, deterministic tests, and
  useful local demos.
- PostgreSQL/Supabase is the shared deployment path. The application creates
  relational tables, the `extensions.vector(1536)` chunk column, and a cosine
  HNSW index. Set `PROJECTLENS_STORAGE_URL` to the server-side pooler URL.
- The Supabase secret key is kept for server-side integration configuration;
  it is not a PostgreSQL password and is not used in the connection string.
- LangGraph persistence is enabled on the PostgreSQL path. SQLite stage rows
  and event rows still provide restart recovery for the offline POC.

## Interfaces

FastAPI and MCP call the same workflow and storage services. React is a review
surface, not a second implementation of the agent. The MCP surface includes
project/source discovery, ingestion, start, pause, resume, retry, watched
folder scans, demo bootstrap, deliverable retrieval, grounded questions, and
item-level review decisions.

## Failure and concurrency behavior

Provider failures record a fallback event and preserve deterministic claims.
Stage failures persist the failed stage and a retry decision; retry resumes
from that stage. A requested pause is honored at the next stage boundary.
Independent runs use run-scoped tables and SQLite locking/PostgreSQL
transactions, so two runs do not share claims, review decisions, or
deliverable versions. Incremental runs attach only new/changed sources, retain
unaffected sections byte-for-byte, and surface contradictions as new review
items.

## Deliberate POC cuts

This slice does not claim production authentication, tenant isolation, object
storage, a scheduler daemon, streaming responses, ZIP ingestion, embedding
quality benchmarking, or a full observability platform. Those are follow-on
work, not hidden assumptions.
