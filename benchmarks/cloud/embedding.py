"""Embedding client for competitor benchmarks.

Moss uses its built-in embedding model and does NOT need this module.
This provides embedding for competitors that require BYO embedding
(Pinecone, Qdrant, Chroma).

Supported providers (set EMBEDDING_PROVIDER in .env):
  - "openai"  — OpenAI text-embedding-3-small (default, most common)
  - "custom"  — any HTTP endpoint that accepts POST {texts: [...]}
                 and returns {embeddings: [[...], ...]}
"""

import os
import requests
from openai import OpenAI


class EmbeddingClient:
    def __init__(self):
        self.provider = os.getenv("EMBEDDING_PROVIDER", "openai")

        if self.provider == "openai":
            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            self.model = os.getenv(
                "OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"
            )
            self.dimension = int(os.getenv("EMBEDDING_DIMENSION", "1536"))
        elif self.provider == "custom":
            self.endpoint = os.getenv("EMBEDDING_ENDPOINT")
            if not self.endpoint:
                raise ValueError(
                    "EMBEDDING_ENDPOINT must be set when EMBEDDING_PROVIDER=custom"
                )
            self.dimension = int(os.getenv("EMBEDDING_DIMENSION", "768"))
            # TEI commonly defaults to a max client batch size of 32.
            self.max_batch_size = int(os.getenv("EMBEDDING_MAX_BATCH_SIZE", "32"))
        else:
            raise ValueError(f"Unknown EMBEDDING_PROVIDER: {self.provider}")

    def embed(self, text: str) -> list[float]:
        """Embed a single text. Returns a list of floats."""
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Returns list of embedding vectors."""
        if self.provider == "openai":
            resp = self.client.embeddings.create(
                model=self.model, input=texts
            )
            return [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]

        elif self.provider == "custom":
            return self._embed_custom_batched(texts)

    def _embed_custom_batched(
        self, texts: list[str]
    ) -> list[list[float]]:
        """Embed via custom endpoint, splitting into fixed-size batches."""
        if not texts:
            return []

        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), self.max_batch_size):
            chunk = texts[i : i + self.max_batch_size]
            resp = requests.post(
                self.endpoint,
                json={"texts": chunk},
                timeout=30,
            )
            resp.raise_for_status()
            all_embeddings.extend(resp.json()["embeddings"])
        return all_embeddings
