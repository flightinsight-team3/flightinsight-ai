"""Embeddings from a local Ollama server (nomic-embed-text, 768 dimensions).

nomic-embed-text needs task prefixes: "search_document: " for reports and "search_query: " for
questions. Reports and questions must use the same model, or the vectors are not comparable.
"""

from __future__ import annotations

import requests

from app.settings import setting

DOCUMENT_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "
DIMENSIONS = 768
DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "nomic-embed-text"
# Ollama's default context is 2048 tokens; nomic-embed-text supports 8192. Without this, long
# narratives are silently cut off.
NUM_CTX = 8192


class OllamaEmbedder:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 300,
        session: requests.Session | None = None,
    ):
        self.base_url = (base_url or setting("OLLAMA_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
        self.model = model or setting("EMBEDDING_MODEL", DEFAULT_MODEL)
        self.timeout = timeout
        self.session = session or requests.Session()

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts as given (callers add the prefix). Returns one 768-d vector per text."""
        if not texts:
            return []
        try:
            response = self.session.post(
                f"{self.base_url}/api/embed",
                json={
                    "model": self.model,
                    "input": texts,
                    "truncate": True,
                    "options": {"num_ctx": NUM_CTX},
                },
                timeout=self.timeout,
            )
        except requests.ConnectionError as exc:
            raise RuntimeError(
                f"Cannot reach Ollama at {self.base_url}. Is it running (`ollama serve`)?"
            ) from exc
        if response.status_code == 404:
            raise RuntimeError(
                f"Ollama has no model {self.model!r}. Run `ollama pull {self.model}`. "
                f"({response.text.strip()})"
            )
        response.raise_for_status()
        vectors = response.json()["embeddings"]
        if len(vectors) != len(texts):
            raise RuntimeError(f"Ollama returned {len(vectors)} vectors for {len(texts)} texts")
        for vector in vectors:
            if len(vector) != DIMENSIONS:
                raise RuntimeError(
                    f"{self.model} returned {len(vector)} dimensions; the asrs_reports "
                    f"vector index expects {DIMENSIONS}"
                )
        return vectors

    def embed_query(self, question: str) -> list[float]:
        return self.embed([QUERY_PREFIX + question.strip()])[0]
