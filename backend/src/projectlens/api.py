"""FastAPI transport for the ProjectLens first proof of concept."""

from __future__ import annotations

import os
import threading
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .analysis import answer_question
from .config import get_settings
from .demo import seed_demo
from .document_policy import DocumentCategory
from .document_processing import parse_bytes
from .storage import Storage
from .workflow import ProjectLensWorkflow


@lru_cache(maxsize=1)
def get_storage() -> Storage:
    configured = os.getenv("PROJECTLENS_STORAGE_URL")
    if not configured:
        try:
            configured = get_settings().database_url
        except Exception:  # noqa: BLE001 - missing configuration should fall back to offline defaults
            configured = ""
    return Storage(url=configured or None)


@lru_cache(maxsize=1)
def get_workflow() -> ProjectLensWorkflow:
    return ProjectLensWorkflow(get_storage())


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    root_path: str = ""


class RunCreate(BaseModel):
    mode: Literal["initial", "incremental"] = "initial"
    provider: Literal["auto", "gemini", "ollama"] = "auto"
    source_path: str = ""
    source_ids: list[str] = Field(default_factory=list)
    base_run_id: str | None = None
    background: bool = True


class DecisionRequest(BaseModel):
    decided_by: str = Field(default="human", min_length=1, max_length=120)
    note: str = Field(default="", max_length=500)


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class RunManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active: set[str] = set()

    def submit(self, run_id: str) -> None:
        with self._lock:
            if run_id in self._active:
                return
            self._active.add(run_id)
        thread = threading.Thread(target=self._execute, args=(run_id,), daemon=True)
        thread.start()

    def _execute(self, run_id: str) -> None:
        try:
            get_workflow().execute(run_id)
        finally:
            with self._lock:
                self._active.discard(run_id)


manager = RunManager()


@asynccontextmanager
async def lifespan(_: FastAPI):
    for run_id in get_storage().recover_incomplete_runs():
        manager.submit(run_id)
    yield


app = FastAPI(title="ProjectLens POC API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _project_or_404(project_id: str) -> dict[str, Any]:
    project = get_storage().get_project(project_id)
    if not project:
        raise HTTPException(404, "project not found")
    return project


def _run_payload(run_id: str) -> dict[str, Any]:
    run = get_storage().get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    return {
        **run,
        "stages": get_storage().list_stages(run_id),
        "documents": get_storage().list_run_documents(run_id),
        "conflicts": get_storage().list_conflicts(run_id),
        "findings": get_storage().list_findings(run_id),
        "review_items": get_storage().list_review_items(run_id),
        "deliverable": get_storage().get_deliverable(run_id),
        "events": get_storage().list_events(run_id),
    }


@app.get("/health")
def health() -> dict[str, Any]:
    storage = get_storage()
    return {"ok": True, "service": "projectlens", "storage": storage.backend, "database": str(storage.path)}


@app.get("/projects")
def list_projects() -> list[dict[str, Any]]:
    return get_storage().list_projects()


@app.post("/projects", status_code=201)
def create_project(request: ProjectCreate) -> dict[str, Any]:
    return get_storage().create_project(request.name, request.root_path)


@app.get("/projects/{project_id}")
def get_project(project_id: str) -> dict[str, Any]:
    return _project_or_404(project_id)


@app.get("/projects/{project_id}/documents")
def list_documents(project_id: str) -> list[dict[str, Any]]:
    _project_or_404(project_id)
    return get_storage().list_documents(project_id)


@app.post("/projects/{project_id}/documents", status_code=201)
async def upload_document(
    project_id: str,
    file: UploadFile = File(...),  # noqa: B008 - FastAPI requires dependency declarations here
    category: str | None = Form(default=None),
) -> dict[str, Any]:
    _project_or_404(project_id)
    filename = Path(file.filename or "upload.txt").name
    raw = await file.read()
    try:
        parsed = parse_bytes(filename, raw)
        resolved_category = DocumentCategory(category) if category else parsed.category
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc
    document = get_storage().upsert_document(project_id, {
        "filename": parsed.filename,
        "relative_path": parsed.relative_path,
        "content_type": parsed.content_type,
        "content": parsed.content,
        "sha256": parsed.sha256,
        "size_bytes": parsed.size_bytes,
        "category": resolved_category.value,
        "metadata": parsed.metadata,
    })
    return document


@app.post("/projects/{project_id}/runs", status_code=202)
def create_run(project_id: str, request: RunCreate) -> dict[str, Any]:
    _project_or_404(project_id)
    base_run_id = request.base_run_id
    if request.mode == "incremental" and not base_run_id:
        base = get_storage().latest_committed_run(project_id)
        base_run_id = base["id"] if base else None
    run = get_storage().create_run(project_id, mode=request.mode, llm_provider=request.provider, source_path=request.source_path, source_ids=request.source_ids, base_run_id=base_run_id)
    if request.background:
        manager.submit(run["id"])
        return _run_payload(run["id"])
    get_workflow().execute(run["id"])
    return _run_payload(run["id"])


@app.get("/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    return _run_payload(run_id)


@app.post("/runs/{run_id}/resume")
def resume_run(run_id: str) -> dict[str, Any]:
    if not get_storage().get_run(run_id):
        raise HTTPException(404, "run not found")
    manager.submit(run_id)
    return _run_payload(run_id)


@app.post("/runs/{run_id}/pause")
def pause_run(run_id: str) -> dict[str, Any]:
    if not get_storage().get_run(run_id):
        raise HTTPException(404, "run not found")
    get_storage().update_run(run_id, stop_requested=1)
    get_storage().add_event(run_id, "pause_requested", "A pause was requested; the worker will stop at the next stage boundary")
    return _run_payload(run_id)


@app.post("/runs/{run_id}/retry")
def retry_run(run_id: str) -> dict[str, Any]:
    if not get_storage().get_run(run_id):
        raise HTTPException(404, "run not found")
    manager.submit(run_id)
    return _run_payload(run_id)


@app.post("/runs/{run_id}/review/{item_id}/approve")
def approve_item(run_id: str, item_id: str, request: DecisionRequest) -> dict[str, Any]:
    try:
        get_workflow().approve_item(run_id, item_id, decided_by=request.decided_by, note=request.note)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    return _run_payload(run_id)


@app.post("/runs/{run_id}/review/{item_id}/reject")
def reject_item(run_id: str, item_id: str, request: DecisionRequest) -> dict[str, Any]:
    try:
        get_workflow().reject_item(run_id, item_id, decided_by=request.decided_by, note=request.note)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    return _run_payload(run_id)


@app.get("/projects/{project_id}/deliverable")
def get_deliverable(project_id: str) -> dict[str, Any]:
    _project_or_404(project_id)
    deliverable = get_storage().latest_deliverable(project_id)
    if not deliverable:
        raise HTTPException(404, "no committed deliverable")
    return deliverable


@app.post("/projects/{project_id}/ask")
def ask_project(project_id: str, request: QuestionRequest) -> dict[str, Any]:
    _project_or_404(project_id)
    storage = get_storage()
    deliverable = storage.latest_deliverable(project_id)
    latest_run = storage.latest_run(project_id)
    claims = storage.list_claims(latest_run["id"]) if latest_run else []
    return answer_question(
        request.question,
        deliverable.get("content") if deliverable else None,
        documents=storage.list_documents(project_id),
        claims=claims,
    )


@app.post("/projects/{project_id}/watch/scan", status_code=202)
def scan_watch_folder(project_id: str, request: RunCreate) -> dict[str, Any]:
    _project_or_404(project_id)
    if not request.source_path:
        raise HTTPException(400, "source_path is required for a watch scan")
    base = get_storage().latest_committed_run(project_id)
    run = get_storage().create_run(project_id, mode="incremental", llm_provider=request.provider, source_path=request.source_path, base_run_id=base["id"] if base else None)
    manager.submit(run["id"])
    return _run_payload(run["id"])


@app.post("/demo/bootstrap")
def bootstrap_demo() -> dict[str, Any]:
    """Create or reuse the synthetic stakeholder demo workspace."""
    storage = get_storage()
    project, documents = seed_demo(storage)
    run = storage.latest_run(project["id"])
    if not run:
        run = storage.create_run(project["id"], llm_provider="auto", source_ids=[document["id"] for document in documents])
        for document in documents:
            storage.add_run_document(run["id"], document["id"])
        get_workflow().execute(run["id"])
    return {"project": project, "documents": storage.list_documents(project["id"]), "run": _run_payload(run["id"])}
