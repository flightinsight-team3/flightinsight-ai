"""Model selection and Gemini fallbacks. No network: make_llm is replaced."""

import pytest

from app.agent import llm


@pytest.fixture
def made(monkeypatch):
    names = []
    monkeypatch.setattr(llm, "make_llm", lambda provider, model=None: names.append(model) or model)
    monkeypatch.setattr(llm, "load_dotenv", lambda: None)
    return names


def test_gemini_fallbacks_skip_the_main_model(made, monkeypatch):
    monkeypatch.setenv("GEMINI_FALLBACK_MODELS", "lite-a, main ,lite-b")
    assert llm.fallback_llms("gemini", "main") == ["lite-a", "lite-b"]


def test_ollama_has_no_fallbacks(made):
    assert llm.fallback_llms("ollama", "qwen2.5:7b") == []
    assert made == []


def test_default_model_reads_env(monkeypatch):
    monkeypatch.setattr(llm, "load_dotenv", lambda: None)
    monkeypatch.setenv("OLLAMA_CHAT_MODEL", "qwen2.5:3b")
    assert llm.default_model("ollama") == "qwen2.5:3b"
    with pytest.raises(ValueError, match="provider"):
        llm.default_model("openai")
