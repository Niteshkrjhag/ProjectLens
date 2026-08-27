"""Opt-in smoke tests for the configured Supabase, Gemini, and Ollama services.

These tests are intentionally opt-in because they use external services and may
consume provider quota. They never print credentials or response bodies.
"""

from __future__ import annotations

import os

import psycopg
import pytest
from projectlens.config import get_settings
from projectlens.model_providers import extraction_prompt, provider_for

pytestmark = pytest.mark.live


def _enabled() -> bool:
    return os.getenv("PROJECTLENS_RUN_LIVE_TESTS", "").lower() in {"1", "true", "yes"}


def _settings():
    if not _enabled():
        pytest.skip("set PROJECTLENS_RUN_LIVE_TESTS=1 to run external smoke tests")
    return get_settings()


def test_supabase_postgres_and_pgvector_are_reachable() -> None:
    settings = _settings()
    with psycopg.connect(settings.database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        assert cursor.fetchone()[0] == 1
        cursor.execute(
            "SELECT '[0.1,0.2]'::extensions.vector <=> '[0.1,0.3]'::extensions.vector"
        )
        distance = cursor.fetchone()[0]
        assert 0 <= float(distance) <= 1


@pytest.mark.parametrize(
    ("provider_name", "required_key"),
    [("gemini", "gemini_api_key"), ("ollama", "ollama_api_key")],
)
def test_live_model_provider(provider_name: str, required_key: str) -> None:
    settings = _settings()
    if not getattr(settings, required_key):
        pytest.skip(f"{required_key.upper()} is not configured")
    provider = provider_for(provider_name, settings)
    try:
        response = provider.generate(extraction_prompt("Status: smoke test is ready.", "smoke.txt"))
    except Exception as exc:
        # A configured provider can be temporarily unavailable; keep the smoke
        # suite honest without treating an external 503 as a code regression.
        message = str(exc).lower()
        if "503" in message or "high demand" in message or "429" in message:
            pytest.skip(f"{provider_name} temporarily unavailable: {type(exc).__name__}")
        raise
    assert response.model
    assert response.text
    assert response.latency_ms >= 0
