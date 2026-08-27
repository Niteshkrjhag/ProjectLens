"""MCP machine interface for driving the same POC flow as the UI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from .analysis import answer_question
from .api import _run_payload, get_storage, get_workflow, manager


server = MCPServer(name="projectlens", version="0.1.0")


@server.tool(description="Create a ProjectLens project.")
def create_project(name: str, root_path: str = "") -> dict[str, Any]:
    return get_storage().create_project(name, root_path)


@server.tool(description="Upload a UTF-8 text, Markdown, PDF, DOCX, RTF, or HTML document from a local path.")
def ingest_document(project_id: str, path: str, category: str | None = None) -> dict[str, Any]:
    from .document_processing import parse_file

    file_path = Path(path).expanduser().resolve()
    parsed = parse_file(file_path)
    document = get_storage().upsert_document(project_id, {
        "filename": parsed.filename,
        "relative_path": parsed.relative_path,
        "content_type": parsed.content_type,
        "content": parsed.content,
        "sha256": parsed.sha256,
        "size_bytes": parsed.size_bytes,
        "category": category or parsed.category.value,
        "metadata": parsed.metadata,
    })
    return document


@server.tool(description="Start a durable initial or incremental analysis run.")
def start_run(project_id: str, mode: str = "initial", source_path: str = "", background: bool = False) -> dict[str, Any]:
    base = get_storage().latest_committed_run(project_id) if mode == "incremental" else None
    run = get_storage().create_run(project_id, mode=mode, source_path=source_path, base_run_id=base["id"] if base else None)
    if background:
        manager.submit(run["id"])
    else:
        get_workflow().execute(run["id"])
    return _run_payload(run["id"])


@server.tool(description="Read every stage, event, source, claim, conflict, finding, review item, and deliverable for a run.")
def get_run(run_id: str) -> dict[str, Any]:
    return _run_payload(run_id)


@server.tool(description="Approve one pending conflict or finding. The workflow resumes automatically when all items are decided.")
def approve_review_item(run_id: str, item_id: str, decided_by: str = "machine", note: str = "") -> dict[str, Any]:
    get_workflow().approve_item(run_id, item_id, decided_by=decided_by, note=note)
    return _run_payload(run_id)


@server.tool(description="Reject one pending conflict or finding. Other review decisions remain intact.")
def reject_review_item(run_id: str, item_id: str, decided_by: str = "machine", note: str = "") -> dict[str, Any]:
    get_workflow().reject_item(run_id, item_id, decided_by=decided_by, note=note)
    return _run_payload(run_id)


@server.tool(description="Ask a grounded question against the latest committed deliverable.")
def ask(project_id: str, question: str) -> dict[str, Any]:
    deliverable = get_storage().latest_deliverable(project_id)
    return answer_question(question, deliverable.get("content") if deliverable else None)


if __name__ == "__main__":
    server.run("stdio")
