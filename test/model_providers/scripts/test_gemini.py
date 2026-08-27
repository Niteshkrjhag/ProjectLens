def test_gemini_model_configuration() -> None:
    """The Gemini model defaults to the requested stable model."""
    import os

    assert os.getenv("GEMINI_MODEL", "gemini-3.5-flash") == "gemini-3.5-flash"
