"""Document taxonomy and precedence rules used by ProjectLens retrieval.

The policy is deliberately deterministic: source documents with a higher
precedence may constrain or contradict lower-precedence sources, but lower-
precedence sources must never silently override them.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import re


class DocumentCategory(StrEnum):
    """Supported document categories, ordered independently from priority."""

    RULES = "rules"
    REQUIREMENTS = "requirements_prd"
    ARCHITECTURE = "architecture_technical_design"
    STATUS = "sprint_project_status"
    ISSUE = "issue_bug"
    ADR = "adr"
    MEETING_NOTES = "meeting_notes"
    QA_REPORT = "qa_test_report"
    RELEASE_NOTES = "release_notes"
    CHANGELOG = "changelog"
    SECURITY_REVIEW = "security_review"
    DEPLOYMENT_REPORT = "deployment_report"
    API_DOCUMENTATION = "api_documentation"
    ROADMAP = "roadmap"
    RETROSPECTIVE = "retrospective"
    UNKNOWN = "unknown"


# Higher values win retrieval and conflict resolution. Rules are highest
# because they represent mandatory engineering, release, or security checks.
PRECEDENCE: dict[DocumentCategory, int] = {
    DocumentCategory.RULES: 100,
    DocumentCategory.REQUIREMENTS: 90,
    DocumentCategory.ARCHITECTURE: 80,
    DocumentCategory.STATUS: 70,
    DocumentCategory.ISSUE: 60,
    DocumentCategory.ADR: 50,
    DocumentCategory.MEETING_NOTES: 40,
    DocumentCategory.QA_REPORT: 40,
    DocumentCategory.RELEASE_NOTES: 40,
    DocumentCategory.CHANGELOG: 40,
    DocumentCategory.SECURITY_REVIEW: 40,
    DocumentCategory.DEPLOYMENT_REPORT: 40,
    DocumentCategory.API_DOCUMENTATION: 40,
    DocumentCategory.ROADMAP: 40,
    DocumentCategory.RETROSPECTIVE: 40,
    DocumentCategory.UNKNOWN: 0,
}


@dataclass(frozen=True, slots=True)
class DocumentSource:
    """Metadata required to rank a collected document."""

    source_id: str
    category: DocumentCategory
    title: str = ""
    updated_at: datetime | None = None
    authoritative: bool = False


_CATEGORY_PATTERNS: tuple[tuple[DocumentCategory, tuple[str, ...]], ...] = (
    (DocumentCategory.RULES, ("engineering checklist", "release checklist", "security checklist", "checklist")),
    (DocumentCategory.REQUIREMENTS, ("requirements", "prd", "product requirements")),
    (DocumentCategory.ARCHITECTURE, ("architecture", "technical design", "system design")),
    (DocumentCategory.STATUS, ("sprint", "project status", "status report", "progress report")),
    (DocumentCategory.ISSUE, ("bug report", "issue report", "bug", "issue")),
    (DocumentCategory.ADR, ("adr", "architecture decision record")),
    (DocumentCategory.MEETING_NOTES, ("meeting notes", "meeting minutes")),
    (DocumentCategory.QA_REPORT, ("qa report", "test report", "qa")),
    (DocumentCategory.RELEASE_NOTES, ("release notes",)),
    (DocumentCategory.CHANGELOG, ("changelog", "change log")),
    (DocumentCategory.SECURITY_REVIEW, ("security review",)),
    (DocumentCategory.DEPLOYMENT_REPORT, ("deployment report",)),
    (DocumentCategory.API_DOCUMENTATION, ("api documentation", "api docs")),
    (DocumentCategory.ROADMAP, ("roadmap",)),
    (DocumentCategory.RETROSPECTIVE, ("retrospective", "retro")),
)


def classify_document(filename: str = "", title: str = "") -> DocumentCategory:
    """Classify a document from its filename and title.

    Explicit rules/checklists are checked first. Unknown documents remain
    ``UNKNOWN`` and should be presented for user confirmation during ingestion.
    """

    haystack = re.sub(r"[_-]+", " ", f"{title} {filename}").casefold()
    for category, patterns in _CATEGORY_PATTERNS:
        if any(pattern in haystack for pattern in patterns):
            return category
    return DocumentCategory.UNKNOWN


def precedence_for(category: DocumentCategory) -> int:
    """Return the retrieval/conflict precedence for a category."""

    return PRECEDENCE[category]


def rank_source(source: DocumentSource) -> tuple[int, int, datetime]:
    """Return a stable sort key: precedence, authority, then recency."""

    return (
        precedence_for(source.category),
        int(source.authoritative),
        source.updated_at or datetime.min,
    )


def preferred_source(sources: list[DocumentSource]) -> DocumentSource:
    """Choose the highest-ranked source for a conflict review.

    This does not hide conflicts; callers should still report all competing
    source IDs when two documents make incompatible claims.
    """

    if not sources:
        raise ValueError("at least one document source is required")
    return max(sources, key=rank_source)
