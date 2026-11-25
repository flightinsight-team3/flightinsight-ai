"""Ollama client and the embed_asrs batch loop, with fake HTTP / Cosmos. No network."""

import pytest

from app.asrs.embeddings import DIMENSIONS, OllamaEmbedder
from scripts import embed_asrs


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload, self.status_code, self.text = payload, status, str(payload)

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSession:
    def __init__(self, dims=DIMENSIONS, status=200):
        self.dims, self.status, self.calls = dims, status, []

    def post(self, url, json, timeout):
        self.calls.append((url, json))
        vectors = [[0.01] * self.dims for _ in json["input"]]
        return FakeResponse({"embeddings": vectors}, self.status)


def embedder(session):
    return OllamaEmbedder("http://ollama:11434/", "nomic-embed-text", session=session)


def test_embed_posts_batch_with_full_context():
    session = FakeSession()
    vectors = embedder(session).embed(["a", "b"])

    url, body = session.calls[0]
    assert url == "http://ollama:11434/api/embed"
    assert body["model"] == "nomic-embed-text"
    assert body["input"] == ["a", "b"]
    assert body["options"]["num_ctx"] == 8192
    assert len(vectors) == 2 and len(vectors[0]) == DIMENSIONS


def test_embed_query_adds_query_prefix():
    session = FakeSession()
    embedder(session).embed_query("  rushed crews ")
    assert session.calls[0][1]["input"] == ["search_query: rushed crews"]


def test_wrong_dimensions_are_rejected():
    with pytest.raises(RuntimeError, match="768"):
        embedder(FakeSession(dims=384)).embed(["a"])


def test_missing_model_explains_pull():
    with pytest.raises(RuntimeError, match="ollama pull"):
        embedder(FakeSession(status=404)).embed(["a"])


class FakeContainer:
    def __init__(self):
        self.items = []

    def upsert_item(self, doc):
        self.items.append(dict(doc))


def docs(n):
    return [{"id": str(i), "synopsis": "S", "narrative": "N"} for i in range(n)]


def test_run_embeds_in_batches_and_upserts_each_document():
    session, container = FakeSession(), FakeContainer()
    written = embed_asrs.run(docs(5), embedder(session), container, batch_size=2)

    assert written == 5
    assert [len(body["input"]) for _, body in session.calls] == [2, 2, 1]
    assert session.calls[0][1]["input"][0] == "search_document: S\n\nN"
    assert all(len(item["narrative_vector"]) == DIMENSIONS for item in container.items)


def test_run_without_container_writes_nothing():
    batch = docs(3)
    assert embed_asrs.run(batch, embedder(FakeSession()), None) == 0
    assert all("narrative_vector" in doc for doc in batch)
