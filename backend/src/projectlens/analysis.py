"""Deterministic extraction and review logic for the first POC.

The POC deliberately treats language-model output as optional.  Facts are
extracted from explicit labelled lines and tightly-scoped sentence patterns,
then every generated sentence is assembled from those stored facts.  This
keeps the offline path grounded and makes it possible to test the safety
properties without a live model key.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from .document_policy import DocumentCategory, DocumentSource, preferred_source


FIELD_ALIASES = {
    "owner": "owner",
    "delivery owner": "owner",
    "workstream": "workstream",
    "delivery window": "delivery_window",
    "target date": "delivery_window",
    "expected measure": "success_measure",
    "success measure": "success_measure",
    "dependency": "dependency",
    "open dependency": "dependency",
    "commercial context": "budget",
    "budget": "budget",
    "scope change": "scope_change",
    "decision date": "decision_date",
    "captured": "captured_date",
}


def _normalise_key(label: str) -> str:
    label = re.sub(r"[^a-z0-9 ]", "", label.casefold()).strip()
    return FIELD_ALIASES.get(label, re.sub(r"\s+", "_", label))


def _clean_value(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().strip("`*_\"'"))


def _add(claims: list[dict[str, Any]], document: dict[str, Any], key: str, label: str, value: str, line: int, *, confidence: float = 1.0, metadata: dict[str, Any] | None = None) -> None:
    value = _clean_value(value)
    if not value or len(value) > 500:
        return
    claims.append({
        "document_id": document["id"],
        "claim_key": key,
        "label": label,
        "value": value,
        "confidence": confidence,
        "line_start": line,
        "line_end": line,
        "evidence_text": document["content"].splitlines()[line - 1].strip(),
        "metadata": metadata or {},
    })


def extract_claims(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract reviewable facts with exact one-based source line ranges."""
    claims: list[dict[str, Any]] = []
    lines = document["content"].splitlines()
    last_heading = ""
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue
        heading = re.sub(r"^[#\-\d.)\s]+", "", line).strip()
        if line.startswith("#") or (len(line) < 50 and not ":" in line and not line.endswith(".")):
            last_heading = heading

        field_match = re.match(r"^(?:[-*]\s*)?([^:]{2,36}):\s*(.+)$", line)
        if field_match:
            label, value = field_match.groups()
            key = _normalise_key(label)
            if key in {"owner", "workstream", "delivery_window", "success_measure", "dependency", "budget", "scope_change", "decision_date", "captured_date"}:
                _add(claims, document, key, label.strip(), value, line_number)

        patterns: tuple[str, str, str] = (
            (r"objective is (.+?)(?:\.\s+Success is measured|\.$)", "objective", "Objective"),
            (r"success is measured by (.+?)(?:\.$|\.)", "success_measure", "Success measure"),
            (r"reports?\s+(\d+%)\s+completion", "completion_percent", "Completion"),
            (r"(?:protect|target|for) the (20\d{2}-\d{2}-\d{2}) delivery window", "delivery_window", "Delivery window"),
            (r"remains (?:the )?(?:only )?dependency worth tracking", "dependency_status", "Dependency status"),
            (r"plan remains inside (\$[\d,]+)", "budget", "Budget"),
        )
        for pattern, key, label in patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                value = match.group(1) if match.lastindex else match.group(0)
                _add(claims, document, key, label, value, line_number, confidence=0.92)

        if re.search(r"failed handoff|missing attachment|unresolved", line, re.IGNORECASE):
            _add(claims, document, "operational_anomaly", "Operational anomaly", line, line_number, confidence=0.95)
        if re.search(r"\b(?:green|red|blocked|at risk|complete|completed)\b", line, re.IGNORECASE):
            _add(claims, document, "status_signal", "Status signal", line, line_number, confidence=0.75)

    if not claims:
        first = next((line for line in lines if line.strip()), "No extractable fact")
        _add(claims, document, "document_summary", last_heading or "Document summary", first, 1, confidence=0.65)

    if document.get("metadata", {}).get("prompt_injection_detected"):
        for line_number in document["metadata"].get("anomaly_lines", []):
            _add(
                claims,
                document,
                "document_instruction_anomaly",
                "Instruction-like text in source",
                lines[line_number - 1],
                line_number,
                confidence=1.0,
                metadata={"instruction_like": True, "execute_as_data": True},
            )
    deduped: dict[tuple[str, str, int], dict[str, Any]] = {}
    for claim in claims:
        deduped[(claim["claim_key"], claim["value"], claim["line_start"])] = claim
    return list(deduped.values())


def _parse_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=UTC)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=UTC)


def reconcile(claims: list[dict[str, Any]], documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group incompatible values and select a visible preferred source."""
    document_by_id = {document["id"]: document for document in documents}
    by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for claim in claims:
        by_key[claim["claim_key"]].append(claim)
    conflicts: list[dict[str, Any]] = []
    for key, candidates in by_key.items():
        values = {re.sub(r"\s+", " ", item["value"].casefold()).strip() for item in candidates}
        if len(values) < 2:
            continue
        sources = [
            DocumentSource(
                source_id=claim["document_id"],
                category=DocumentCategory(document_by_id[claim["document_id"]]["category"]),
                title=document_by_id[claim["document_id"]]["filename"],
                updated_at=_parse_datetime(document_by_id[claim["document_id"]].get("updated_at")),
                authoritative=bool(document_by_id[claim["document_id"]].get("authoritative")),
            )
            for claim in candidates
        ]
        source = preferred_source(sources)
        preferred_claim = next(claim for claim in candidates if claim["document_id"] == source.source_id)
        conflicts.append({
            "claim_key": key,
            "claim_ids": [claim.get("id", "") for claim in candidates],
            "preferred_claim_id": preferred_claim.get("id"),
            "description": f"Sources disagree on {key}: " + "; ".join(f"{claim['value']} ({document_by_id[claim['document_id']]['filename']})" for claim in candidates),
        })
    return conflicts


def build_deliverable(
    claims: list[dict[str, Any]],
    documents: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
    findings: list[dict[str, Any]] | None = None,
    *,
    base_content: dict[str, Any] | None = None,
    affected_keys: set[str] | None = None,
) -> dict[str, Any]:
    """Build a JSON report where each fact carries its source quote and line."""
    document_by_id = {document["id"]: document for document in documents}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for claim in claims:
        grouped[claim["claim_key"]].append(claim)
    previous_sections = (base_content or {}).get("sections", {})
    sections: dict[str, dict[str, Any]] = {}
    all_keys = sorted(set(grouped) | set(previous_sections))
    for key in all_keys:
        if base_content and affected_keys is not None and key not in affected_keys and key in previous_sections:
            sections[key] = previous_sections[key]
            continue
        candidates = grouped.get(key, [])
        entries = []
        for claim in candidates:
            doc = document_by_id[claim["document_id"]]
            entries.append({
                "value": claim["value"],
                "source_id": claim["document_id"],
                "source": doc["relative_path"],
                "line_start": claim["line_start"],
                "line_end": claim["line_end"],
                "quote": claim["evidence_text"],
                "confidence": claim["confidence"],
            })
        sections[key] = {"key": key, "label": candidates[0]["label"] if candidates else key, "entries": entries}

    conflict_keys = {item["claim_key"] for item in conflicts}
    return {
        "title": "ProjectLens grounded project brief",
        "grounding": "Every reported fact is copied from a source quote; unsupported facts are omitted.",
        "sections": sections,
        "conflicts": [
            {"claim_key": item["claim_key"], "description": item["description"], "requires_human_decision": True}
            for item in conflicts
        ],
        "findings": findings or [],
        "open_questions": [f"Human decision required for conflicting {key}." for key in sorted(conflict_keys)],
    }


def examine(
    claims: list[dict[str, Any]],
    documents: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
    deliverable: dict[str, Any],
) -> list[dict[str, Any]]:
    """Apply the built-in engineering/release/security checks."""
    findings: list[dict[str, Any]] = []
    categories = {document["category"] for document in documents}
    if "rules" not in categories:
        findings.append({
            "rule_key": "rules-source-required",
            "title": "Rules source was not supplied",
            "severity": "high",
            "description": "The mandatory engineering/release/security checklist is absent, so a rules-based clean result cannot be claimed.",
            "source_ids": [],
        })
    for document in documents:
        metadata = document.get("metadata", {})
        if metadata.get("prompt_injection_detected"):
            findings.append({
                "rule_key": "document-instructions-are-data",
                "title": f"Instruction-like text in {document['filename']}",
                "severity": "high",
                "description": "The source contains text addressed to the analyst. It was recorded as evidence and was not executed.",
                "source_ids": [document["id"]],
            })
    for conflict in conflicts:
        findings.append({
            "rule_key": "conflicting-source-values",
            "title": f"Conflict requires a human decision: {conflict['claim_key']}",
            "severity": "medium",
            "description": conflict["description"],
            "source_ids": [],
        })
    if not claims:
        findings.append({
            "rule_key": "grounded-claim-required",
            "title": "No grounded claims extracted",
            "severity": "high",
            "description": "The deliverable cannot be committed because the sources yielded no reviewable facts.",
            "source_ids": [],
        })
    return findings


def answer_question(question: str, deliverable: dict[str, Any] | None) -> dict[str, Any]:
    """Answer only from the committed deliverable, with explicit unknowns."""
    if not deliverable:
        return {"answer": "I do not have a committed deliverable to answer from.", "citations": [], "grounded": False}
    stop_words = {"the", "and", "for", "with", "what", "who", "where", "when", "why", "how", "does", "is", "are", "was", "were", "can", "could", "would", "should"}
    tokens = {token for token in re.findall(r"[a-z0-9]{3,}", question.casefold()) if token not in stop_words}
    matches: list[tuple[int, str, dict[str, Any]]] = []
    for key, section in deliverable.get("sections", {}).items():
        haystack = f"{key} {section.get('label', '')}".casefold()
        label_tokens = set(re.findall(r"[a-z0-9]{3,}", haystack))
        for entry in section.get("entries", []):
            score = len(tokens & set(re.findall(r"[a-z0-9]{3,}", f"{haystack} {entry.get('value','')}".casefold())))
            label_score = len(tokens & label_tokens)
            if score and (label_score or score >= 2):
                matches.append((score, key, entry))
    if not matches:
        return {"answer": "I cannot find support for that in the committed sources.", "citations": [], "grounded": False}
    matches.sort(key=lambda item: item[0], reverse=True)
    top = matches[:3]
    citations = [
        {"source": entry["source"], "line_start": entry["line_start"], "line_end": entry["line_end"], "quote": entry["quote"]}
        for _, _, entry in top
    ]
    answer = "; ".join(f"{key.replace('_', ' ').title()}: {entry['value']}" for _, key, entry in top)
    return {"answer": answer, "citations": citations, "grounded": True}
