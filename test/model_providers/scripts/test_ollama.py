def test_ollama_cloud_model_configuration() -> None:
    """The Ollama default targets the hosted 120B model."""
    import os

    assert os.getenv("OLLAMA_MODEL", "gpt-oss:120b-cloud") == "gpt-oss:120b-cloud"
