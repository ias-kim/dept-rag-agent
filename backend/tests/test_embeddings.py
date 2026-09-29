from types import SimpleNamespace

import pytest

from app.core.embeddings import OpenAIEmbedder
from app.db.models import EMBEDDING_DIM


class FakeClient:
    def __init__(self, dim=EMBEDDING_DIM):
        self.dim = dim
        self.batches = []
        self.embeddings = SimpleNamespace(create=self._create)

    def _create(self, *, model, input):
        self.batches.append(list(input))
        return SimpleNamespace(data=[SimpleNamespace(embedding=[float(len(t))] * self.dim) for t in input])


def test_batches_and_preserves_order():
    client = FakeClient()
    texts = ["a" * (i % 5 + 1) for i in range(130)]
    vectors = OpenAIEmbedder(client, "m", batch_size=64).embed(texts)
    assert [len(b) for b in client.batches] == [64, 64, 2]
    assert [v[0] for v in vectors] == [float(len(t)) for t in texts]


def test_empty_input_makes_no_call():
    client = FakeClient()
    assert OpenAIEmbedder(client, "m").embed([]) == []
    assert client.batches == []


def test_wrong_dimension_is_rejected():
    with pytest.raises(ValueError, match="dimension"):
        OpenAIEmbedder(FakeClient(dim=3), "m").embed(["x"])
