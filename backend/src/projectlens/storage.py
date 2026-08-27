"""Durable storage for the offline-first ProjectLens proof of concept.

The POC uses SQLite by default so a fresh clone can exercise the entire flow
without a database account.  The schema is intentionally relational and keeps
the storage boundary small; it can be moved to Supabase/PostgreSQL without
changing the workflow contract.  A PostgreSQL adapter is added in the next
milestone, while the existing :mod:`projectlens.database` module remains the
connection helper for Supabase deployments.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    root_path TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    content_type TEXT NOT NULL,
    content TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    category TEXT NOT NULL,
    authoritative INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(project_id, sha256)
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    mode TEXT NOT NULL DEFAULT 'initial',
    status TEXT NOT NULL,
    current_stage TEXT,
    source_path TEXT NOT NULL DEFAULT '',
    source_ids_json TEXT NOT NULL DEFAULT '[]',
    base_run_id TEXT,
    stop_requested INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    cost_usd REAL NOT NULL DEFAULT 0,
    duration_ms INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS run_documents (
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    PRIMARY KEY(run_id, document_id)
);

CREATE TABLE IF NOT EXISTS run_stages (
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    stage_name TEXT NOT NULL,
    status TEXT NOT NULL,
    attempt INTEGER NOT NULL DEFAULT 0,
    decision TEXT NOT NULL DEFAULT '',
    detail_json TEXT NOT NULL DEFAULT '{}',
    started_at TEXT,
    completed_at TEXT,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    PRIMARY KEY(run_id, stage_name)
);

CREATE TABLE IF NOT EXISTS claims (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    claim_key TEXT NOT NULL,
    label TEXT NOT NULL,
    value TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1,
    line_start INTEGER NOT NULL,
    line_end INTEGER NOT NULL,
    evidence_text TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(run_id, document_id, claim_key, value, line_start)
);

CREATE TABLE IF NOT EXISTS conflicts (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    claim_key TEXT NOT NULL,
    description TEXT NOT NULL,
    claim_ids_json TEXT NOT NULL,
    preferred_claim_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS findings (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    rule_key TEXT NOT NULL,
    title TEXT NOT NULL,
    severity TEXT NOT NULL,
    description TEXT NOT NULL,
    source_ids_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS review_items (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    item_type TEXT NOT NULL,
    item_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    decision_note TEXT NOT NULL DEFAULT '',
    decided_by TEXT,
    decided_at TEXT,
    UNIQUE(run_id, item_type, item_id)
);

CREATE TABLE IF NOT EXISTS deliverables (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    status TEXT NOT NULL,
    content_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    committed_at TEXT,
    UNIQUE(project_id, version)
);

CREATE TABLE IF NOT EXISTS run_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_documents_project ON documents(project_id);
CREATE INDEX IF NOT EXISTS idx_runs_project ON runs(project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_claims_run ON claims(run_id);
CREATE INDEX IF NOT EXISTS idx_review_run_status ON review_items(run_id, status);
CREATE INDEX IF NOT EXISTS idx_events_run ON run_events(run_id, id);
"""


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def decode_json(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


class Storage:
    """Small transactional repository used by the workflow and API."""

    def __init__(self, url: str | None = None, data_dir: str | Path = "data") -> None:
        configured = url or os.getenv("PROJECTLENS_STORAGE_URL", "")
        if configured and not configured.startswith("sqlite://"):
            raise ValueError(
                "The POC storage adapter currently supports sqlite:// only. "
                "Set PROJECTLENS_STORAGE_URL=sqlite:///./data/projectlens.db for an "
                "offline run; Supabase/PostgreSQL wiring remains the deployment adapter."
            )
        if configured.startswith("sqlite:///"):
            raw_path = configured.removeprefix("sqlite:///")
            self.path = Path(raw_path)
        else:
            self.path = Path(data_dir) / "projectlens.db"
        if not self.path.is_absolute():
            self.path = Path.cwd() / self.path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            connection = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 30000")
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

    def initialize(self) -> None:
        with self.connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(SCHEMA)

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row else None

    def create_project(self, name: str, root_path: str = "") -> dict[str, Any]:
        project_id = new_id("prj")
        now = utc_now()
        with self.connection() as connection:
            connection.execute(
                "INSERT INTO projects(id,name,root_path,created_at,updated_at) VALUES (?,?,?,?,?)",
                (project_id, name, root_path, now, now),
            )
        return self.get_project(project_id)  # type: ignore[return-value]

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            return self._row(connection.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone())

    def list_projects(self) -> list[dict[str, Any]]:
        with self.connection() as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM projects ORDER BY created_at DESC")]

    def update_project(self, project_id: str, **fields: str) -> dict[str, Any] | None:
        allowed = {"name", "root_path"}
        updates = [(key, value) for key, value in fields.items() if key in allowed]
        if not updates:
            return self.get_project(project_id)
        updates.append(("updated_at", utc_now()))
        clause = ", ".join(f"{key}=?" for key, _ in updates)
        with self.connection() as connection:
            connection.execute(f"UPDATE projects SET {clause} WHERE id=?", [v for _, v in updates] + [project_id])
        return self.get_project(project_id)

    def upsert_document(self, project_id: str, document: dict[str, Any]) -> dict[str, Any]:
        document_id = new_id("doc")
        with self.connection() as connection:
            connection.execute(
                """INSERT OR IGNORE INTO documents
                (id,project_id,filename,relative_path,content_type,content,sha256,size_bytes,
                 category,authoritative,updated_at,metadata_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    document_id,
                    project_id,
                    document["filename"],
                    document.get("relative_path", document["filename"]),
                    document.get("content_type", "text/plain"),
                    document["content"],
                    document["sha256"],
                    document.get("size_bytes", len(document["content"].encode())),
                    document["category"],
                    int(document.get("authoritative", False)),
                    document.get("updated_at", utc_now()),
                    _json(document.get("metadata", {})),
                ),
            )
        inserted = self.get_document(document_id)
        if inserted:
            return inserted
        return self.get_document_by_hash(project_id, document["sha256"])  # type: ignore[return-value]

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = self._row(connection.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone())
        if row:
            row["metadata"] = decode_json(row.pop("metadata_json", None), {})
        return row

    def get_document_by_hash(self, project_id: str, sha256: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = self._row(
                connection.execute("SELECT * FROM documents WHERE project_id=? AND sha256=?", (project_id, sha256)).fetchone()
            )
        if row:
            row["metadata"] = decode_json(row.pop("metadata_json", None), {})
        return row

    def list_documents(self, project_id: str) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = [dict(row) for row in connection.execute("SELECT * FROM documents WHERE project_id=? ORDER BY relative_path", (project_id,))]
        for row in rows:
            row["metadata"] = decode_json(row.pop("metadata_json", None), {})
        return rows

    def create_run(
        self,
        project_id: str,
        *,
        mode: str = "initial",
        source_path: str = "",
        source_ids: list[str] | None = None,
        base_run_id: str | None = None,
    ) -> dict[str, Any]:
        run_id = new_id("run")
        now = utc_now()
        with self.connection() as connection:
            connection.execute(
                """INSERT INTO runs
                (id,project_id,mode,status,source_path,source_ids_json,base_run_id,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (run_id, project_id, mode, "queued", source_path, _json(source_ids or []), base_run_id, now, now),
            )
        return self.get_run(run_id)  # type: ignore[return-value]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = self._row(connection.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone())
        if row:
            row["source_ids"] = decode_json(row.pop("source_ids_json", None), [])
        return row

    def update_run(self, run_id: str, **fields: Any) -> dict[str, Any] | None:
        allowed = {
            "status", "current_stage", "source_path", "base_run_id", "stop_requested", "error",
            "completed_at", "cost_usd", "duration_ms",
        }
        updates = [(key, value) for key, value in fields.items() if key in allowed]
        if "source_ids" in fields:
            updates.append(("source_ids_json", _json(fields["source_ids"])))
        updates.append(("updated_at", utc_now()))
        clause = ", ".join(f"{key}=?" for key, _ in updates)
        with self.connection() as connection:
            connection.execute(f"UPDATE runs SET {clause} WHERE id=?", [v for _, v in updates] + [run_id])
        return self.get_run(run_id)

    def add_run_document(self, run_id: str, document_id: str) -> None:
        with self.connection() as connection:
            connection.execute("INSERT OR IGNORE INTO run_documents(run_id,document_id) VALUES (?,?)", (run_id, document_id))

    def list_run_documents(self, run_id: str) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = [dict(row) for row in connection.execute(
                """SELECT d.* FROM documents d JOIN run_documents rd ON rd.document_id=d.id
                WHERE rd.run_id=? ORDER BY d.relative_path""", (run_id,)
            )]
        for row in rows:
            row["metadata"] = decode_json(row.pop("metadata_json", None), {})
        return rows

    def latest_committed_run(self, project_id: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = self._row(connection.execute(
                "SELECT * FROM runs WHERE project_id=? AND status='committed' ORDER BY completed_at DESC LIMIT 1", (project_id,)
            ).fetchone())
        if row:
            row["source_ids"] = decode_json(row.pop("source_ids_json", None), [])
        return row

    def upsert_stage(self, run_id: str, stage_name: str, **fields: Any) -> dict[str, Any]:
        existing = self.get_stage(run_id, stage_name)
        if existing:
            updates = dict(fields)
            if "detail" in updates:
                updates["detail_json"] = _json(updates.pop("detail"))
            updates["attempt"] = existing["attempt"] + (1 if fields.get("status") == "running" else 0)
            clause = ", ".join(f"{key}=?" for key in updates)
            with self.connection() as connection:
                connection.execute(f"UPDATE run_stages SET {clause} WHERE run_id=? AND stage_name=?", list(updates.values()) + [run_id, stage_name])
        else:
            with self.connection() as connection:
                connection.execute(
                    """INSERT INTO run_stages(run_id,stage_name,status,attempt,decision,detail_json,started_at,completed_at,duration_ms,cost_usd)
                    VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (
                        run_id, stage_name, fields.get("status", "pending"), fields.get("attempt", 0),
                        fields.get("decision", ""), _json(fields.get("detail", {})), fields.get("started_at"),
                        fields.get("completed_at"), fields.get("duration_ms", 0), fields.get("cost_usd", 0),
                    ),
                )
        return self.get_stage(run_id, stage_name)  # type: ignore[return-value]

    def get_stage(self, run_id: str, stage_name: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = self._row(connection.execute("SELECT * FROM run_stages WHERE run_id=? AND stage_name=?", (run_id, stage_name)).fetchone())
        if row:
            row["detail"] = decode_json(row.pop("detail_json", None), {})
        return row

    def list_stages(self, run_id: str) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = [dict(row) for row in connection.execute("SELECT * FROM run_stages WHERE run_id=? ORDER BY rowid", (run_id,))]
        for row in rows:
            row["detail"] = decode_json(row.pop("detail_json", None), {})
        return rows

    def replace_claims(self, run_id: str, claims: list[dict[str, Any]]) -> None:
        with self.connection() as connection:
            connection.execute("DELETE FROM claims WHERE run_id=?", (run_id,))
            for claim in claims:
                connection.execute(
                    """INSERT OR IGNORE INTO claims
                    (id,run_id,document_id,claim_key,label,value,confidence,line_start,line_end,evidence_text,metadata_json)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        claim.get("id", new_id("clm")), run_id, claim["document_id"], claim["claim_key"], claim["label"],
                        claim["value"], claim.get("confidence", 1), claim["line_start"], claim["line_end"],
                        claim["evidence_text"], _json(claim.get("metadata", {})),
                    ),
                )

    def list_claims(self, run_id: str) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = [dict(row) for row in connection.execute("SELECT * FROM claims WHERE run_id=? ORDER BY document_id,line_start", (run_id,))]
        for row in rows:
            row["metadata"] = decode_json(row.pop("metadata_json", None), {})
        return rows

    def list_project_claims(self, run_id: str) -> list[dict[str, Any]]:
        """Return claims from a run with source metadata attached."""
        with self.connection() as connection:
            rows = [dict(row) for row in connection.execute(
                """SELECT c.*, d.filename, d.relative_path, d.category, d.authoritative, d.updated_at AS document_updated_at,
                c.metadata_json AS claim_metadata_json, d.metadata_json AS document_metadata_json
                FROM claims c JOIN documents d ON d.id=c.document_id WHERE c.run_id=? ORDER BY c.line_start""", (run_id,)
            )]
        for row in rows:
            row["metadata"] = decode_json(row.pop("document_metadata_json", None), {})
            row["claim_metadata"] = decode_json(row.pop("claim_metadata_json", None), {})
            row.pop("metadata_json", None)
        return rows

    def replace_conflicts(self, run_id: str, conflicts: list[dict[str, Any]]) -> None:
        with self.connection() as connection:
            connection.execute("DELETE FROM conflicts WHERE run_id=?", (run_id,))
            for item in conflicts:
                item_id = item.setdefault("id", new_id("cnf"))
                connection.execute(
                    "INSERT INTO conflicts(id,run_id,claim_key,description,claim_ids_json,preferred_claim_id,status) VALUES (?,?,?,?,?,?,?)",
                    (item_id, run_id, item["claim_key"], item["description"], _json(item["claim_ids"]), item.get("preferred_claim_id"), "pending"),
                )

    def list_conflicts(self, run_id: str) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = [dict(row) for row in connection.execute("SELECT * FROM conflicts WHERE run_id=? ORDER BY claim_key", (run_id,))]
        for row in rows:
            row["claim_ids"] = decode_json(row.pop("claim_ids_json", None), [])
        return rows

    def replace_findings(self, run_id: str, findings: list[dict[str, Any]]) -> None:
        with self.connection() as connection:
            connection.execute("DELETE FROM findings WHERE run_id=?", (run_id,))
            for item in findings:
                item_id = item.setdefault("id", new_id("fnd"))
                connection.execute(
                    "INSERT INTO findings(id,run_id,rule_key,title,severity,description,source_ids_json,status) VALUES (?,?,?,?,?,?,?,?)",
                    (item_id, run_id, item["rule_key"], item["title"], item["severity"], item["description"], _json(item.get("source_ids", [])), "pending"),
                )

    def list_findings(self, run_id: str) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = [dict(row) for row in connection.execute("SELECT * FROM findings WHERE run_id=? ORDER BY severity DESC,title", (run_id,))]
        for row in rows:
            row["source_ids"] = decode_json(row.pop("source_ids_json", None), [])
        return rows

    def replace_review_items(self, run_id: str, items: list[dict[str, Any]]) -> None:
        with self.connection() as connection:
            for item in items:
                connection.execute(
                    """INSERT OR IGNORE INTO review_items
                    (id,run_id,item_type,item_id,title,description,payload_json,status)
                    VALUES (?,?,?,?,?,?,?,?)""",
                    (item.get("id", new_id("rev")), run_id, item["item_type"], item["item_id"], item["title"], item["description"], _json(item.get("payload", {})), "pending"),
                )

    def list_review_items(self, run_id: str) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = [dict(row) for row in connection.execute("SELECT * FROM review_items WHERE run_id=? ORDER BY item_type,title", (run_id,))]
        for row in rows:
            row["payload"] = decode_json(row.pop("payload_json", None), {})
        return rows

    def decide_review_item(self, item_id: str, status: str, decided_by: str, note: str = "") -> dict[str, Any] | None:
        if status not in {"approved", "rejected"}:
            raise ValueError("review status must be approved or rejected")
        with self.connection() as connection:
            connection.execute(
                "UPDATE review_items SET status=?,decision_note=?,decided_by=?,decided_at=? WHERE id=? AND status='pending'",
                (status, note, decided_by, utc_now(), item_id),
            )
            row = self._row(connection.execute("SELECT * FROM review_items WHERE id=?", (item_id,)).fetchone())
        if row:
            row["payload"] = decode_json(row.pop("payload_json", None), {})
        return row

    def pending_review_items(self, run_id: str) -> list[dict[str, Any]]:
        return [item for item in self.list_review_items(run_id) if item["status"] == "pending"]

    def save_deliverable(self, project_id: str, run_id: str, content: dict[str, Any], status: str = "draft") -> dict[str, Any]:
        import hashlib

        payload = _json(content)
        content_hash = hashlib.sha256(payload.encode()).hexdigest()
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM deliverables WHERE run_id=?", (run_id,)).fetchone()
            if row:
                connection.execute("UPDATE deliverables SET content_json=?,content_hash=?,status=? WHERE run_id=?", (payload, content_hash, status, run_id))
            else:
                next_version = connection.execute("SELECT COALESCE(MAX(version),0)+1 FROM deliverables WHERE project_id=?", (project_id,)).fetchone()[0]
                connection.execute(
                    "INSERT INTO deliverables(id,project_id,run_id,version,status,content_json,content_hash,created_at,committed_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (new_id("del"), project_id, run_id, next_version, status, payload, content_hash, utc_now(), utc_now() if status == "committed" else None),
                )
        return self.get_deliverable(run_id)  # type: ignore[return-value]

    def commit_deliverable(self, run_id: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            connection.execute("UPDATE deliverables SET status='committed',committed_at=? WHERE run_id=?", (utc_now(), run_id))
            row = self._row(connection.execute("SELECT * FROM deliverables WHERE run_id=?", (run_id,)).fetchone())
        if row:
            row["content"] = decode_json(row.pop("content_json", None), {})
        return row

    def get_deliverable(self, run_id: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = self._row(connection.execute("SELECT * FROM deliverables WHERE run_id=?", (run_id,)).fetchone())
        if row:
            row["content"] = decode_json(row.pop("content_json", None), {})
        return row

    def latest_deliverable(self, project_id: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = self._row(connection.execute("SELECT * FROM deliverables WHERE project_id=? AND status='committed' ORDER BY version DESC LIMIT 1", (project_id,)).fetchone())
        if row:
            row["content"] = decode_json(row.pop("content_json", None), {})
        return row

    def add_event(self, run_id: str, event_type: str, message: str, payload: dict[str, Any] | None = None) -> None:
        with self.connection() as connection:
            connection.execute("INSERT INTO run_events(run_id,event_type,message,payload_json,created_at) VALUES (?,?,?,?,?)", (run_id, event_type, message, _json(payload or {}), utc_now()))

    def list_events(self, run_id: str) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = [dict(row) for row in connection.execute("SELECT * FROM run_events WHERE run_id=? ORDER BY id", (run_id,))]
        for row in rows:
            row["payload"] = decode_json(row.pop("payload_json", None), {})
        return rows

    def recover_incomplete_runs(self) -> list[str]:
        """Make a process restart safe by re-queuing interrupted runs."""
        with self.connection() as connection:
            rows = [row[0] for row in connection.execute("SELECT id FROM runs WHERE status IN ('running','paused')")]
            if rows:
                connection.executemany("UPDATE runs SET status='queued',stop_requested=0,updated_at=? WHERE id=?", [(utc_now(), run_id) for run_id in rows])
                connection.execute("UPDATE run_stages SET status='pending',started_at=NULL WHERE status='running'")
        return rows
