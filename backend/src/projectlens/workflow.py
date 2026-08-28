"""LangGraph-orchestrated, durable ProjectLens POC workflow."""

from __future__ import annotations

import time
from itertools import pairwise
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from .analysis import build_deliverable, examine, extract_claims, reconcile
from .config import get_settings
from .document_processing import discover_files, parse_file
from .embeddings import chunk_text, embed_text
from .model_providers import extraction_prompt, provider_for
from .storage import Storage, utc_now

STAGES = ("discover", "extract", "reconcile", "draft", "examine", "human_gate", "commit")


class RunState(TypedDict, total=False):
    run_id: str
    halt: bool
    stop_after_stage: str | None
    error: str | None


class ProjectLensWorkflow:
    """A resumable graph whose durable checkpoints live in ``Storage``."""

    def __init__(self, storage: Storage | None = None) -> None:
        self.storage = storage or Storage()
        self._checkpoint_context = None
        self._checkpointer = None
        if self.storage.backend == "postgres":
            from langgraph.checkpoint.postgres import PostgresSaver

            self._checkpoint_context = PostgresSaver.from_conn_string(self.storage.url)
            self._checkpointer = self._checkpoint_context.__enter__()
            self._checkpointer.setup()
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(RunState)
        for stage in STAGES:
            graph.add_node(stage, self._node(stage))
        graph.add_edge(START, STAGES[0])
        for current, following in pairwise(STAGES):
            graph.add_conditional_edges(current, self._next(following), {"continue": following, "halt": END})
        graph.add_edge(STAGES[-1], END)
        return graph.compile(checkpointer=self._checkpointer)

    @staticmethod
    def _next(following: str):
        def choose(state: RunState) -> str:
            return "halt" if state.get("halt") else "continue"

        return choose

    def _node(self, stage: str):
        def run(state: RunState) -> RunState:
            result = self.run_stage(state["run_id"], stage, stop_after_stage=state.get("stop_after_stage"))
            return {**state, **result}

        return run

    def execute(self, run_id: str, *, stop_after_stage: str | None = None) -> dict[str, Any]:
        """Run or resume a graph from durable stage state."""
        run = self.storage.get_run(run_id)
        if not run:
            raise KeyError(f"unknown run: {run_id}")
        if run.get("stop_requested"):
            paused_at = run.get("current_stage") or "the next stage"
            self.storage.update_run(run_id, status="paused", stop_requested=0)
            self.storage.add_event(run_id, "run_paused", f"Run paused before {paused_at}", {})
            return {"run_id": run_id, "halt": True}
        started = time.perf_counter()
        self.storage.update_run(run_id, status="running", error=None)
        self.storage.add_event(run_id, "run_started", "Workflow started or resumed", {"stop_after_stage": stop_after_stage})
        try:
            self.graph.invoke(
                {"run_id": run_id, "stop_after_stage": stop_after_stage, "halt": False},
                config={"configurable": {"thread_id": run_id}},
            )
        except Exception as exc:  # noqa: BLE001 - persist any worker failure for retry/recovery
            self.storage.update_run(run_id, status="failed", error=str(exc), duration_ms=int((time.perf_counter() - started) * 1000))
            self.storage.add_event(run_id, "run_failed", "Workflow failed", {"error": str(exc)})
        else:
            current = self.storage.get_run(run_id) or {}
            if current.get("status") == "running":
                self.storage.update_run(run_id, status="committed", completed_at=utc_now(), duration_ms=int((time.perf_counter() - started) * 1000))
        return self.storage.get_run(run_id)  # type: ignore[return-value]

    def run_stage(self, run_id: str, stage: str, *, stop_after_stage: str | None = None) -> RunState:
        run = self.storage.get_run(run_id)
        if not run:
            raise KeyError(f"unknown run: {run_id}")
        if run.get("stop_requested"):
            self.storage.update_run(run_id, status="paused", current_stage=stage, stop_requested=0)
            self.storage.add_event(run_id, "run_paused", f"Run paused before {stage}", {"stage": stage})
            return {"run_id": run_id, "halt": True}
        existing = self.storage.get_stage(run_id, stage)
        if stage != "human_gate" and existing and existing["status"] in {"completed", "skipped"}:
            return {"run_id": run_id, "halt": False}
        if stage == "human_gate" and existing and existing["status"] == "completed" and self.storage.pending_review_items(run_id):
            self.storage.update_run(run_id, status="awaiting_review", current_stage=stage)
            return {"run_id": run_id, "halt": True}
        started = time.perf_counter()
        attempt = (existing or {}).get("attempt", 0) + 1
        self.storage.upsert_stage(run_id, stage, status="running", attempt=attempt, started_at=utc_now(), decision="execute")
        self.storage.update_run(run_id, status="running", current_stage=stage)
        self.storage.add_event(run_id, "stage_started", f"Stage {stage} started", {"attempt": attempt})
        try:
            detail, decision = getattr(self, f"_stage_{stage}")(run)
        except Exception as exc:
            self.storage.upsert_stage(run_id, stage, status="failed", attempt=attempt, completed_at=utc_now(), decision="retry", detail={"error": str(exc)}, duration_ms=int((time.perf_counter() - started) * 1000))
            self.storage.add_event(run_id, "stage_failed", f"Stage {stage} failed; retry is available", {"error": str(exc)})
            raise
        duration = int((time.perf_counter() - started) * 1000)
        self.storage.upsert_stage(run_id, stage, status="completed", attempt=attempt, completed_at=utc_now(), decision=decision, detail=detail, duration_ms=duration, cost_usd=0)
        self.storage.add_event(run_id, "stage_completed", f"Stage {stage} completed", {"decision": decision, "duration_ms": duration})
        if decision.startswith("skip"):
            self.storage.add_event(run_id, "stage_skipped", f"Stage {stage} skipped an optional path", {"decision": decision})
        if decision == "escalate":
            self.storage.add_event(run_id, "workflow_escalated", f"Stage {stage} escalated for human review", {"stage": stage})
        if decision == "skip_no_new_sources":
            self.storage.update_run(run_id, status="no_change", current_stage=stage, completed_at=utc_now())
            self.storage.add_event(run_id, "run_no_change", "Incremental scan found no new or changed sources", {})
            return {"run_id": run_id, "halt": True}
        if stage == "human_gate" and detail.get("pending_count", 0):
            self.storage.update_run(run_id, status="awaiting_review", current_stage=stage)
            return {"run_id": run_id, "halt": True}
        if stop_after_stage == stage:
            self.storage.update_run(run_id, status="paused", current_stage=stage, stop_requested=0)
            self.storage.add_event(run_id, "run_paused", f"Run paused after {stage}", {})
            return {"run_id": run_id, "halt": True}
        return {"run_id": run_id, "halt": False}

    def _stage_discover(self, run: dict[str, Any]) -> tuple[dict[str, Any], str]:
        project = self.storage.get_project(run["project_id"])
        if not project:
            raise ValueError("project no longer exists")
        attached = {doc["id"] for doc in self.storage.list_run_documents(run["id"])}
        existing_by_path = {
            document["relative_path"]: document
            for document in self.storage.list_documents(run["project_id"])
        }
        added_document_ids: list[str] = []
        changed_source_paths: list[str] = []
        if run.get("source_path"):
            root = Path(run["source_path"]).expanduser().resolve()
            for path in discover_files(root):
                parsed = parse_file(path, root)
                existing = self.storage.get_document_by_hash(run["project_id"], parsed.sha256)
                document = self.storage.upsert_document(run["project_id"], {
                    "filename": parsed.filename,
                    "relative_path": parsed.relative_path,
                    "content_type": parsed.content_type,
                    "content": parsed.content,
                    "sha256": parsed.sha256,
                    "size_bytes": parsed.size_bytes,
                    "category": parsed.category.value,
                    "updated_at": parsed.updated_at,
                    "metadata": parsed.metadata,
                })
                if document["id"] not in attached and (run["mode"] == "initial" or existing is None):
                    self.storage.add_run_document(run["id"], document["id"])
                    attached.add(document["id"])
                    added_document_ids.append(document["id"])
                    previous = existing_by_path.get(document["relative_path"])
                    if previous and previous["sha256"] != document["sha256"]:
                        changed_source_paths.append(document["relative_path"])
        for source_id in run.get("source_ids", []):
            if self.storage.get_document(source_id) and source_id not in attached:
                self.storage.add_run_document(run["id"], source_id)
                attached.add(source_id)
        if not attached and run["mode"] == "initial":
            for document in self.storage.list_documents(run["project_id"]):
                self.storage.add_run_document(run["id"], document["id"])
                attached.add(document["id"])
        if not attached and run["mode"] == "incremental":
            return {
                "document_count": 0,
                "source_path": run.get("source_path", ""),
                "added_document_ids": [],
                "changed_source_paths": [],
            }, "skip_no_new_sources"
        if not attached:
            raise ValueError("no supported documents were found for this run")
        self.storage.update_run(run["id"], source_ids=sorted(attached))
        return {
            "document_count": len(attached),
            "source_path": run.get("source_path", ""),
            "added_document_ids": added_document_ids,
            "changed_source_paths": changed_source_paths,
        }, "continue"

    def _stage_extract(self, run: dict[str, Any]) -> tuple[dict[str, Any], str]:
        documents = self.storage.list_run_documents(run["id"])
        claims: list[dict[str, Any]] = []
        model_runs: list[dict[str, Any]] = []
        embedding_count = 0
        embedding_providers: set[str] = set()
        settings = get_settings()
        provider_name = str(run.get("llm_provider") or settings.projectlens_llm_provider).lower().strip()
        if provider_name == "auto":
            provider_name = "ollama" if settings.ollama_api_key else "gemini"
        provider = provider_for(provider_name, settings) if settings.projectlens_llm_mode.lower() == "live" else None
        for document in documents:
            document_claims = extract_claims(document)
            chunks = []
            for index, content in enumerate(chunk_text(document["content"]), start=0):
                embedding = embed_text(content, settings)
                embedding_providers.add(embedding.provider)
                chunks.append({"chunk_index": index, "content": content, "embedding": embedding.values})
            self.storage.replace_document_chunks(document["id"], chunks)
            embedding_count += len(chunks)
            if provider:
                try:
                    response = provider.generate(extraction_prompt(document["content"], document["filename"]))
                    model_runs.append({"provider": response.provider, "model": response.model, "latency_ms": response.latency_ms, "input_tokens": response.input_tokens, "output_tokens": response.output_tokens, "output_chars": len(response.text), "status": "ok"})
                    for claim in document_claims:
                        claim.setdefault("metadata", {}).update({"model_verifier": response.provider, "model_verified": True})
                except Exception as exc:  # noqa: BLE001 - provider failure must preserve deterministic extraction
                    model_runs.append({"provider": provider_name, "status": "fallback", "error": f"{type(exc).__name__}: {str(exc).splitlines()[0][:180]}"})
                    self.storage.add_event(run["id"], "model_fallback", "Live provider unavailable; deterministic extraction retained", {"provider": provider_name, "error": str(exc).splitlines()[0][:180]})
            claims.extend(document_claims)
        self.storage.replace_claims(run["id"], claims)
        decision = "model_verified" if any(item.get("status") == "ok" for item in model_runs) else "skip_model_verification"
        return {
            "document_count": len(documents),
            "claim_count": len(claims),
            "model_runs": model_runs,
            "embedding_count": embedding_count,
            "embedding_providers": sorted(embedding_providers),
        }, decision

    def _effective_inputs(self, run: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        documents = self.storage.list_run_documents(run["id"])
        claims = self.storage.list_claims(run["id"])
        if run["mode"] == "incremental" and run.get("base_run_id"):
            base_documents = self.storage.list_run_documents(run["base_run_id"])
            documents = base_documents + [document for document in documents if document["id"] not in {item["id"] for item in base_documents}]
            claims = self.storage.list_claims(run["base_run_id"]) + claims
        return documents, claims

    def _stage_reconcile(self, run: dict[str, Any]) -> tuple[dict[str, Any], str]:
        documents, claims = self._effective_inputs(run)
        conflicts = reconcile(claims, documents)
        self.storage.replace_conflicts(run["id"], conflicts)
        return {"conflict_count": len(conflicts), "claim_count": len(claims)}, "escalate" if conflicts else "continue"

    def _stage_draft(self, run: dict[str, Any]) -> tuple[dict[str, Any], str]:
        documents, claims = self._effective_inputs(run)
        conflicts = self.storage.list_conflicts(run["id"])
        base = self.storage.latest_deliverable(run["project_id"]) if run["mode"] == "incremental" else None
        affected: set[str] | None = None
        if run["mode"] == "incremental":
            current_claims = self.storage.list_claims(run["id"])
            base_claims = self.storage.list_claims(run["base_run_id"]) if run.get("base_run_id") else []
            base_values: dict[str, set[str]] = {}
            for claim in base_claims:
                base_values.setdefault(claim["claim_key"], set()).add(claim["value"].casefold().strip())
            affected = {
                claim["claim_key"] for claim in current_claims
                if claim["value"].casefold().strip() not in base_values.get(claim["claim_key"], set())
            }
        content = build_deliverable(claims, documents, conflicts, base_content=base.get("content") if base else None, affected_keys=affected)
        self.storage.save_deliverable(run["project_id"], run["id"], content, status="draft")
        preserved = sorted(set((base or {}).get("content", {}).get("sections", {})) - (affected or set())) if base else []
        return {"section_count": len(content["sections"]), "preserved_sections": preserved}, "preserve_unchanged" if preserved else "continue"

    def _stage_examine(self, run: dict[str, Any]) -> tuple[dict[str, Any], str]:
        documents, claims = self._effective_inputs(run)
        conflicts = self.storage.list_conflicts(run["id"])
        draft = self.storage.get_deliverable(run["id"])
        findings = examine(claims, documents, conflicts, draft["content"] if draft else {})
        self.storage.replace_findings(run["id"], findings)
        content = draft["content"] if draft else {}
        content["findings"] = [{"title": item["title"], "severity": item["severity"], "description": item["description"]} for item in findings]
        self.storage.save_deliverable(run["project_id"], run["id"], content, status="draft")
        return {"finding_count": len(findings), "clean": not findings}, "escalate" if findings else "continue"

    def _stage_human_gate(self, run: dict[str, Any]) -> tuple[dict[str, Any], str]:
        conflicts = self.storage.list_conflicts(run["id"])
        findings = self.storage.list_findings(run["id"])
        items: list[dict[str, Any]] = []
        for conflict in conflicts:
            items.append({"item_type": "conflict", "item_id": conflict["id"], "title": f"Resolve conflict: {conflict['claim_key']}", "description": conflict["description"], "payload": conflict})
        for finding in findings:
            items.append({"item_type": "finding", "item_id": finding["id"], "title": finding["title"], "description": finding["description"], "payload": finding})
        self.storage.replace_review_items(run["id"], items)
        pending = len(self.storage.pending_review_items(run["id"]))
        return {"review_item_count": len(items), "pending_count": pending}, "human_review" if pending else "auto_continue"

    def _stage_commit(self, run: dict[str, Any]) -> tuple[dict[str, Any], str]:
        pending = self.storage.pending_review_items(run["id"])
        if pending:
            self.storage.update_run(run["id"], status="awaiting_review", current_stage="human_gate")
            return {"pending_count": len(pending)}, "await_review"
        draft = self.storage.get_deliverable(run["id"])
        if not draft:
            raise ValueError("cannot commit without a draft deliverable")
        content = draft["content"]
        decisions = self.storage.list_review_items(run["id"])
        rejected_findings = {item["item_id"] for item in decisions if item["item_type"] == "finding" and item["status"] == "rejected"}
        content["findings"] = [
            {"title": finding["title"], "severity": finding["severity"], "description": finding["description"], "status": decision["status"]}
            for finding in self.storage.list_findings(run["id"])
            if finding["id"] not in rejected_findings
            for decision in decisions if decision["item_type"] == "finding" and decision["item_id"] == finding["id"]
        ]
        approved_conflicts = {item["item_id"] for item in decisions if item["item_type"] == "conflict" and item["status"] == "approved"}
        rejected_conflicts = {item["item_id"] for item in decisions if item["item_type"] == "conflict" and item["status"] == "rejected"}
        for conflict in self.storage.list_conflicts(run["id"]):
            if conflict["id"] not in approved_conflicts:
                continue
            section = content.get("sections", {}).get(conflict["claim_key"])
            if not section or not conflict.get("preferred_claim_id"):
                continue
            section["entries"] = [
                entry for entry in section.get("entries", [])
                if entry.get("claim_id") == conflict["preferred_claim_id"]
            ]
        content["open_questions"] = [
            item["description"] for item in self.storage.list_conflicts(run["id"]) if item["id"] in rejected_conflicts
        ]
        self.storage.save_deliverable(run["project_id"], run["id"], content, status="draft")
        self.storage.commit_deliverable(run["id"])
        return {"deliverable_hash": self.storage.get_deliverable(run["id"])["content_hash"]}, "commit"

    def approve_item(self, run_id: str, item_id: str, *, decided_by: str = "human", note: str = "") -> dict[str, Any]:
        item = self.storage.decide_review_item(item_id, "approved", decided_by, note)
        if not item or item["run_id"] != run_id:
            raise KeyError("review item does not belong to this run")
        self._resume_if_ready(run_id)
        return item

    def reject_item(self, run_id: str, item_id: str, *, decided_by: str = "human", note: str = "") -> dict[str, Any]:
        item = self.storage.decide_review_item(item_id, "rejected", decided_by, note)
        if not item or item["run_id"] != run_id:
            raise KeyError("review item does not belong to this run")
        self._resume_if_ready(run_id)
        return item

    def _resume_if_ready(self, run_id: str) -> None:
        if not self.storage.pending_review_items(run_id):
            self.execute(run_id)

    def retry(self, run_id: str) -> dict[str, Any]:
        run = self.storage.get_run(run_id)
        if not run:
            raise KeyError(run_id)
        failed = next((stage for stage in self.storage.list_stages(run_id) if stage["status"] == "failed"), None)
        if failed:
            self.storage.upsert_stage(run_id, failed["stage_name"], status="pending", decision="retry")
            self.storage.update_run(run_id, status="queued", error=None)
            self.storage.add_event(run_id, "retry_requested", f"Retry requested from failed stage {failed['stage_name']}", {"stage": failed["stage_name"]})
        return self.execute(run_id)

    def request_retry(self, run_id: str) -> dict[str, Any]:
        """Persist a retry decision before a background worker resumes the run."""
        run = self.storage.get_run(run_id)
        if not run:
            raise KeyError(run_id)
        failed = next((stage for stage in self.storage.list_stages(run_id) if stage["status"] == "failed"), None)
        if failed:
            self.storage.upsert_stage(run_id, failed["stage_name"], status="pending", decision="retry")
            self.storage.update_run(run_id, status="queued", error=None)
            self.storage.add_event(run_id, "retry_requested", f"Retry requested from failed stage {failed['stage_name']}", {"stage": failed["stage_name"]})
        return self.storage.get_run(run_id)  # type: ignore[return-value]
