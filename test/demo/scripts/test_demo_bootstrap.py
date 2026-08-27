"""Tests for the stakeholder demo workspace bootstrap."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parents[3] / "backend" / "src"))

from projectlens.api import app, get_storage, get_workflow
from projectlens.config import get_settings


def test_demo_bootstrap_is_preloaded_and_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROJECTLENS_STORAGE_URL", f"sqlite:///{tmp_path / 'demo.db'}")
    monkeypatch.setenv("PROJECTLENS_LLM_MODE", "offline")
    get_settings.cache_clear()
    get_storage.cache_clear()
    get_workflow.cache_clear()
    try:
        with TestClient(app) as client:
            first = client.post("/demo/bootstrap").json()
            second = client.post("/demo/bootstrap").json()

        assert first["project"]["name"] == "Atlas migration · stakeholder demo"
        assert first["project"]["id"] == second["project"]["id"]
        assert first["run"]["id"] == second["run"]["id"]
        assert len(first["documents"]) == 6
        assert first["run"]["status"] == "awaiting_review"
        assert len(first["run"]["review_items"]) > 0
        project = client.post("/projects", json={"name": "Provider routing test"}).json()
        routed = client.post(f"/projects/{project['id']}/runs", json={"provider": "ollama", "background": False}).json()
        assert routed["llm_provider"] == "ollama"
    finally:
        get_settings.cache_clear()
        get_storage.cache_clear()
        get_workflow.cache_clear()
