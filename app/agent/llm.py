"""Chat models the agent can run on: Gemini (cloud) or a local Ollama model.

Settings (.env): GOOGLE_API_KEY, GEMINI_MODEL, GEMINI_FALLBACK_MODELS (comma-separated),
OLLAMA_BASE_URL, OLLAMA_CHAT_MODEL.
Embeddings always stay on Ollama + nomic-embed-text, whichever chat model is used.
"""

from __future__ import annotations

from app.asrs.embeddings import DEFAULT_BASE_URL
from app.settings import load_dotenv, setting

PROVIDERS = ("gemini", "ollama")
DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"
DEFAULT_OLLAMA_MODEL = "qwen2.5:7b"
# Tried in order when the Gemini model fails, e.g. 503 "model is experiencing high demand".
DEFAULT_GEMINI_FALLBACKS = "gemini-3.5-flash-lite,gemini-3.1-flash-lite"
GEMINI_TIMEOUT = 45  # seconds; an overloaded model hangs, so give up and use a fallback
OLLAMA_NUM_CTX = 16384  # tool results (report narratives) are long; Ollama's default is 4096


def default_model(provider: str) -> str:
    load_dotenv()
    if provider == "gemini":
        return setting("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    if provider == "ollama":
        return setting("OLLAMA_CHAT_MODEL", DEFAULT_OLLAMA_MODEL)
    raise ValueError(f"Unknown provider {provider!r}; choose one of {PROVIDERS}")


def make_llm(provider: str, model: str | None = None):
    """A LangChain chat model that supports tool calling."""
    model = model or default_model(provider)
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        # Temperature is left at Gemini's default: Google advises against lowering it for
        # Gemini 3+ models (it can cause looping).
        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=setting("GOOGLE_API_KEY"),
            max_retries=0,
            timeout=GEMINI_TIMEOUT,
        )
    from langchain_ollama import ChatOllama

    return ChatOllama(
        model=model,
        base_url=setting("OLLAMA_BASE_URL", DEFAULT_BASE_URL),
        temperature=0,
        num_ctx=OLLAMA_NUM_CTX,
        keep_alive="30m",
    )


def fallback_llms(provider: str, model: str | None = None) -> list:
    """Models to try when the main one fails. Gemini only; a local Ollama model has no
    capacity errors to fall back from."""
    if provider != "gemini":
        return []
    model = model or default_model(provider)
    names = setting("GEMINI_FALLBACK_MODELS", DEFAULT_GEMINI_FALLBACKS)
    return [make_llm("gemini", n.strip()) for n in names.split(",") if n.strip() not in ("", model)]
