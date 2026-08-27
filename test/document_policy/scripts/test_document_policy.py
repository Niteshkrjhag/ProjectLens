import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[3] / "backend" / "src"))

from projectlens.document_policy import (  # noqa: E402
    DocumentCategory,
    DocumentSource,
    classify_document,
    preferred_source,
    precedence_for,
)


def test_rules_are_higher_priority_than_required_documents() -> None:
    assert precedence_for(DocumentCategory.RULES) > precedence_for(DocumentCategory.REQUIREMENTS)


def test_classification_prioritizes_checklists() -> None:
    assert classify_document(filename="release_security_checklist.md") is DocumentCategory.RULES


def test_required_document_wins_over_optional_document() -> None:
    winner = preferred_source(
        [
            DocumentSource("notes", DocumentCategory.MEETING_NOTES),
            DocumentSource("prd", DocumentCategory.REQUIREMENTS),
        ]
    )
    assert winner.source_id == "prd"


@pytest.mark.parametrize(
    ("scenario", "filename", "expected"),
    [
        ("simple PRD upload", "requirements.md", DocumentCategory.REQUIREMENTS),
        ("medium architecture review", "technical-design.docx", DocumentCategory.ARCHITECTURE),
        ("complex release gate", "engineering-release-security-checklist.pdf", DocumentCategory.RULES),
        ("day-to-day planning", "sprint-status-report.md", DocumentCategory.STATUS),
        ("rush-day incident triage", "critical-bug-issue-report.txt", DocumentCategory.ISSUE),
        ("light-day context enrichment", "meeting-notes.md", DocumentCategory.MEETING_NOTES),
        ("QA verification", "qa-test-report.pdf", DocumentCategory.QA_REPORT),
        ("security review", "security-review.md", DocumentCategory.SECURITY_REVIEW),
        ("release handoff", "release-notes.md", DocumentCategory.RELEASE_NOTES),
        ("unknown upload", "project-context.txt", DocumentCategory.UNKNOWN),
    ],
)
def test_real_world_document_scenarios(
    scenario: str, filename: str, expected: DocumentCategory
) -> None:
    """Classify representative light, normal, and high-pressure workflows."""
    assert scenario
    assert classify_document(filename=filename) is expected


def test_rules_beat_urgent_issue_reports() -> None:
    """A rush-day bug cannot override a mandatory release/security checklist."""
    winner = preferred_source(
        [
            DocumentSource("urgent-bug", DocumentCategory.ISSUE),
            DocumentSource("release-gate", DocumentCategory.RULES),
        ]
    )
    assert winner.source_id == "release-gate"


def test_newer_optional_notes_do_not_override_an_authoritative_prd() -> None:
    """Recency is a tie-breaker only after category precedence and authority."""
    from datetime import datetime, timezone

    winner = preferred_source(
        [
            DocumentSource(
                "authoritative-prd",
                DocumentCategory.REQUIREMENTS,
                authoritative=True,
                updated_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            ),
            DocumentSource(
                "new-notes",
                DocumentCategory.MEETING_NOTES,
                updated_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
            ),
        ]
    )
    assert winner.source_id == "authoritative-prd"


def test_synthetic_dataset_covers_every_scenario_mode_and_version() -> None:
    """The offline corpus stays complete and does not collapse into duplicates."""
    dataset_root = Path(__file__).parents[3] / "testing dataset"
    scenarios = {"simple", "medium", "complex", "day-to-day", "rush-day", "light-day"}
    modes = {"general", "odd", "even"}
    versions = {"version 1", "version 2", "version 3"}
    files = [path for path in dataset_root.rglob("*") if path.is_file() and path.name != "README.md"]

    assert len(files) == 54
    assert {(path.parts[-4], path.parts[-3], path.parts[-2]) for path in files} == {
        (scenario, mode, version)
        for scenario in scenarios
        for mode in modes
        for version in versions
    }
    assert len({path.read_text(encoding="utf-8") for path in files}) == len(files)
    assert {path.suffix for path in files} == {".md", ".txt"}
