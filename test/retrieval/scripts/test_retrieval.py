"""Behavioral coverage for chunk persistence and offline/vector retrieval."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3] / "backend" / "src"))

from projectlens.embeddings import chunk_text, embed_text
from projectlens.storage import Storage


def test_chunking_is_stable_and_overlapping() -> None:
    content = "\n".join(f"Line {index}: the migration retains a source citation." for index in range(80))
    chunks = chunk_text(content, size=240, overlap=40)

    assert len(chunks) > 1
    assert chunks == chunk_text(content, size=240, overlap=40)
    assert any(chunks[index][-30:] in chunks[index + 1] for index in range(len(chunks) - 1))


def test_offline_embedding_and_storage_return_relevant_source_chunk(tmp_path: Path) -> None:
    store = Storage(data_dir=tmp_path / "state")
    project = store.create_project("Retrieval test")
    content = "Release readiness requires an approved security checklist before production deploy."
    document = store.upsert_document(project["id"], {
        "filename": "release-checklist.md",
        "relative_path": "mandatory/rules/release-checklist.md",
        "content_type": "text/markdown",
        "content": content,
        "sha256": hashlib.sha256(content.encode()).hexdigest(),
        "size_bytes": len(content.encode()),
        "category": "rules",
    })
    embedding = embed_text(content)
    store.replace_document_chunks(document["id"], [{"chunk_index": 0, "content": content, "embedding": embedding.values}])

    results = store.search_chunks(project["id"], embed_text("approved security checklist for production deploy").values)

    assert results
    assert results[0]["document_id"] == document["id"]
    assert results[0]["relative_path"] == "mandatory/rules/release-checklist.md"
    assert results[0]["distance"] < 1
