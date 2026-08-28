"""MCP machine interface for driving the same POC flow as the UI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from .analysis import answer_question
from .api import _run_payload, get_storage, get_workflow, manager
from .config import get_settings
from .demo import seed_demo
from .embeddings import embed_text

server = MCPServer(name="projectlens", version="0.1.0")


@server.tool(description="Create a ProjectLens project.")
def create_project(name: str, root_path: str = "") -> dict[str, Any]:
    return get_storage().create_project(name, root_path)


@server.tool(description="List every ProjectLens project available to the machine client.")
def list_projects() -> list[dict[str, Any]]:
    return get_storage().list_projects()


@server.tool(description="List all parsed source documents in a ProjectLens project.")
def list_documents(project_id: str) -> list[dict[str, Any]]:
    if not get_storage().get_project(project_id):
        raise KeyError(f"unknown project: {project_id}")
    return get_storage().list_documents(project_id)


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


@server.tool(description="Start a durable initial or incremental analysis run, synchronously or in the background.")
def start_run(
    project_id: str,
    mode: str = "initial",
    provider: str = "auto",
    source_path: str = "",
    source_ids: list[str] | None = None,
    base_run_id: str = "",
    background: bool = False,
) -> dict[str, Any]:
    base = get_storage().latest_committed_run(project_id) if mode == "incremental" and not base_run_id else None
    run = get_storage().create_run(
        project_id,
        mode=mode,
        llm_provider=provider,
        source_path=source_path,
        source_ids=source_ids or [],
        base_run_id=base_run_id or (base["id"] if base else None),
    )
    if background:
        manager.submit(run["id"])
    else:
        get_workflow().execute(run["id"])
    return _run_payload(run["id"])


@server.tool(description="Read every stage, event, source, claim, conflict, finding, review item, and deliverable for a run.")
def get_run(run_id: str) -> dict[str, Any]:
    return _run_payload(run_id)


@server.tool(description="Resume a paused or recoverable run through the durable background worker.")
def resume_run(run_id: str) -> dict[str, Any]:
    if not get_storage().get_run(run_id):
        raise KeyError(f"unknown run: {run_id}")
    manager.submit(run_id)
    return _run_payload(run_id)


@server.tool(description="Request a safe pause; the workflow stops at the next persisted stage boundary.")
def pause_run(run_id: str) -> dict[str, Any]:
    if not get_storage().get_run(run_id):
        raise KeyError(f"unknown run: {run_id}")
    get_storage().update_run(run_id, stop_requested=1)
    get_storage().add_event(run_id, "pause_requested", "A pause was requested; the worker will stop at the next stage boundary")
    return _run_payload(run_id)


@server.tool(description="Retry a failed run from its persisted failed stage.")
def retry_run(run_id: str, background: bool = False) -> dict[str, Any]:
    if background:
        get_workflow().request_retry(run_id)
        manager.submit(run_id)
    else:
        get_workflow().retry(run_id)
    return _run_payload(run_id)


@server.tool(description="Scan a watched local folder and create an incremental run for only new or changed sources.")
def scan_watch_folder(project_id: str, source_path: str, provider: str = "auto", background: bool = False) -> dict[str, Any]:
    if not source_path:
        raise ValueError("source_path is required for a watch scan")
    base = get_storage().latest_committed_run(project_id)
    run = get_storage().create_run(
        project_id,
        mode="incremental",
        llm_provider=provider,
        source_path=source_path,
        base_run_id=base["id"] if base else None,
    )
    if background:
        manager.submit(run["id"])
    else:
        get_workflow().execute(run["id"])
    return _run_payload(run["id"])


@server.tool(description="Read the latest committed deliverable, or an explicit not-committed state.")
def get_deliverable(project_id: str) -> dict[str, Any]:
    if not get_storage().get_project(project_id):
        raise KeyError(f"unknown project: {project_id}")
    deliverable = get_storage().latest_deliverable(project_id)
    return deliverable or {"project_id": project_id, "status": "not_committed", "deliverable": None}


@server.tool(description="Create or reuse the synthetic stakeholder demo and run its durable workflow.")
def bootstrap_demo() -> dict[str, Any]:
    storage = get_storage()
    project, documents = seed_demo(storage)
    run = storage.latest_run(project["id"])
    if not run:
        run = storage.create_run(project["id"], llm_provider="auto", source_ids=[document["id"] for document in documents])
        for document in documents:
            storage.add_run_document(run["id"], document["id"])
        get_workflow().execute(run["id"])
    return {"project": project, "documents": storage.list_documents(project["id"]), "run": _run_payload(run["id"])}


@server.tool(description="Approve one pending conflict or finding. The workflow resumes automatically when all items are decided.")
def approve_review_item(run_id: str, item_id: str, decided_by: str = "machine", note: str = "") -> dict[str, Any]:
    get_workflow().approve_item(run_id, item_id, decided_by=decided_by, note=note)
    return _run_payload(run_id)


@server.tool(description="Reject one pending conflict or finding. Other review decisions remain intact.")
def reject_review_item(run_id: str, item_id: str, decided_by: str = "machine", note: str = "") -> dict[str, Any]:
    get_workflow().reject_item(run_id, item_id, decided_by=decided_by, note=note)
    return _run_payload(run_id)


@server.tool(description="Ask a grounded question against the latest deliverable and source context, with citations.")
def ask(project_id: str, question: str) -> dict[str, Any]:
    storage = get_storage()
    deliverable = storage.latest_deliverable(project_id)
    latest_run = storage.latest_run(project_id)
    claims = storage.list_claims(latest_run["id"]) if latest_run else []
    settings = get_settings()
    retrieved_chunks = storage.search_chunks(project_id, embed_text(question, settings).values)
    return answer_question(
        question,
        deliverable.get("content") if deliverable else None,
        documents=storage.list_documents(project_id),
        claims=claims,
        retrieved_chunks=retrieved_chunks,
    )


if __name__ == "__main__":
    server.run("stdio")
