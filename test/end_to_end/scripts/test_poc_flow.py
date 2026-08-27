"""Behavior tests for the offline ProjectLens POC."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import sys

sys.path.insert(0, str(Path(__file__).parents[3] / "backend" / "src"))

from projectlens.analysis import answer_question  # noqa: E402
from projectlens.mcp_server import server  # noqa: E402
from projectlens.storage import Storage  # noqa: E402
from projectlens.workflow import ProjectLensWorkflow  # noqa: E402


FIXTURE_ROOT = Path(__file__).parents[3] / "testing dataset"


def _storage(tmp_path: Path) -> Storage:
    return Storage(data_dir=tmp_path / "state")


def _approve_all(store: Storage, workflow: ProjectLensWorkflow, run_id: str) -> None:
    for item in list(store.pending_review_items(run_id)):
        workflow.approve_item(run_id, item["id"], decided_by="test")


def test_full_run_requires_item_level_gate_and_commits_grounded_report(tmp_path: Path) -> None:
    store = _storage(tmp_path)
    workflow = ProjectLensWorkflow(store)
    project = store.create_project("Atlas test")
    run = store.create_run(project["id"], source_path=str(FIXTURE_ROOT / "simple" / "general"))

    workflow.execute(run["id"])
    waiting = store.get_run(run["id"])
    assert waiting["status"] == "awaiting_review"
    assert [stage["stage_name"] for stage in store.list_stages(run["id"])] == [
        "discover", "extract", "reconcile", "draft", "examine", "human_gate"
    ]
    assert store.pending_review_items(run["id"])
    draft = store.get_deliverable(run["id"])
    assert draft["status"] == "draft"
    assert all(entry["source"] and entry["line_start"] > 0 for section in draft["content"]["sections"].values() for entry in section["entries"])

    _approve_all(store, workflow, run["id"])
    committed = store.get_run(run["id"])
    assert committed["status"] == "committed"
    assert store.get_deliverable(run["id"])["status"] == "committed"


def test_interrupted_run_resumes_from_persisted_stage_boundary(tmp_path: Path) -> None:
    store = _storage(tmp_path)
    workflow = ProjectLensWorkflow(store)
    project = store.create_project("Restart test")
    run = store.create_run(project["id"], source_path=str(FIXTURE_ROOT / "simple" / "general"))

    workflow.execute(run["id"], stop_after_stage="extract")
    paused = store.get_run(run["id"])
    assert paused["status"] == "paused"
    assert [stage["stage_name"] for stage in store.list_stages(run["id"])] == ["discover", "extract"]
    assert store.recover_incomplete_runs() == [run["id"]]

    workflow.execute(run["id"])
    resumed = store.get_run(run["id"])
    assert resumed["status"] == "awaiting_review"
    stages = {stage["stage_name"]: stage for stage in store.list_stages(run["id"])}
    assert stages["discover"]["attempt"] == 1
    assert stages["extract"]["attempt"] == 1
    assert stages["reconcile"]["status"] == "completed"


def test_two_runs_can_process_same_project_without_corrupting_state(tmp_path: Path) -> None:
    store = _storage(tmp_path)
    project = store.create_project("Concurrency test")
    source_path = str(FIXTURE_ROOT / "medium" / "general")
    runs = [store.create_run(project["id"], source_path=source_path) for _ in range(2)]

    def execute(run_id: str) -> str:
        return ProjectLensWorkflow(store).execute(run_id)["status"]

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(execute, [run["id"] for run in runs]))
    assert statuses == ["awaiting_review", "awaiting_review"]
    for run in runs:
        assert len(store.list_run_documents(run["id"])) == 3
        assert len(store.list_claims(run["id"])) > 0
        assert len(store.list_events(run["id"])) > 0


def test_instruction_like_document_text_is_reported_and_never_executed(tmp_path: Path) -> None:
    store = _storage(tmp_path)
    workflow = ProjectLensWorkflow(store)
    project = store.create_project("Safety test")
    run = store.create_run(project["id"], source_path=str(FIXTURE_ROOT / "simple" / "odd"))

    workflow.execute(run["id"])
    findings = store.list_findings(run["id"])
    assert any(finding["rule_key"] == "document-instructions-are-data" for finding in findings)
    assert any(claim["claim_key"] == "document_instruction_anomaly" for claim in store.list_claims(run["id"]))
    assert not any(event["event_type"] == "document_instruction_executed" for event in store.list_events(run["id"]))


def test_incremental_run_preserves_unaffected_sections_byte_for_byte(tmp_path: Path) -> None:
    source_root = tmp_path / "watch"
    source_root.mkdir()
    (source_root / "requirements.md").write_text(
        "# Atlas\nDocument type: Requirements / PRD\nOwner: Maya Chen\nDelivery window: 2026-09-07\nExpected measure: under 90 seconds\n",
        encoding="utf-8",
    )
    store = _storage(tmp_path)
    workflow = ProjectLensWorkflow(store)
    project = store.create_project("Incremental test")
    initial = store.create_run(project["id"], source_path=str(source_root))
    workflow.execute(initial["id"])
    _approve_all(store, workflow, initial["id"])
    before = store.get_deliverable(initial["id"])["content"]

    (source_root / "status.txt").write_text(
        "Atlas status update\nDocument type: Sprint / Project Status Report\nA status check reports 42% completion and one dependency at risk.\n",
        encoding="utf-8",
    )
    incremental = store.create_run(project["id"], mode="incremental", source_path=str(source_root), base_run_id=initial["id"])
    workflow.execute(incremental["id"])
    draft = store.get_deliverable(incremental["id"])["content"]
    assert store.get_run(incremental["id"])["status"] == "awaiting_review"
    assert draft["sections"]["owner"] == before["sections"]["owner"]
    assert draft["sections"]["delivery_window"] == before["sections"]["delivery_window"]
    assert store.get_stage(incremental["id"], "draft")["detail"]["preserved_sections"]
    _approve_all(store, workflow, incremental["id"])
    assert store.get_run(incremental["id"])["status"] == "committed"


def test_grounded_answer_refuses_unsupported_claim(tmp_path: Path) -> None:
    store = _storage(tmp_path)
    workflow = ProjectLensWorkflow(store)
    project = store.create_project("Question test")
    run = store.create_run(project["id"], source_path=str(FIXTURE_ROOT / "light-day" / "general"))
    workflow.execute(run["id"])
    _approve_all(store, workflow, run["id"])
    answer = answer_question("Who approved the unrecoverable production outage?", store.latest_deliverable(project["id"])["content"])
    assert answer["grounded"] is False
    assert answer["citations"] == []
    assert "cannot find support" in answer["answer"].casefold()


def test_mcp_registers_machine_drivable_tools() -> None:
    async def names() -> list[str]:
        return [tool.name for tool in await server.list_tools()]

    assert asyncio.run(names()) == [
        "create_project", "ingest_document", "start_run", "get_run", "approve_review_item", "reject_review_item", "ask"
    ]


def test_fastapi_can_drive_upload_run_gate_and_grounded_question(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROJECTLENS_STORAGE_URL", f"sqlite:///{tmp_path / 'api.db'}")
    from projectlens.api import app, get_storage, get_workflow

    get_workflow.cache_clear()
    get_storage.cache_clear()
    source = FIXTURE_ROOT / "simple" / "general" / "version 1" / "baseline.md"
    with TestClient(app) as client:
        project = client.post("/projects", json={"name": "HTTP test"}).json()
        with source.open("rb") as handle:
            document = client.post(f"/projects/{project['id']}/documents", files={"file": ("requirements.md", handle, "text/markdown")}).json()
        run = client.post(f"/projects/{project['id']}/runs", json={"source_ids": [document["id"]], "background": False}).json()
        assert run["status"] == "awaiting_review"
        for item in run["review_items"]:
            run = client.post(f"/runs/{run['id']}/review/{item['id']}/approve", json={"decided_by": "api-test"}).json()
        assert run["status"] == "committed"
        answer = client.post(f"/projects/{project['id']}/ask", json={"question": "What is the expected measure?"}).json()
        assert answer["grounded"] is True
        assert answer["citations"]
    get_workflow.cache_clear()
    get_storage.cache_clear()
