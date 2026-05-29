"""Embedding service using sentence-transformers + FAISS for concept similarity search."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import faiss
import numpy as np

from core.exceptions import EmbeddingError
from core.logging import get_logger
from domain.concept import I14YConcept

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

log = get_logger(__name__)
_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


class EmbeddingService:
    def __init__(self, index_path: Path) -> None:
        self._index_path = index_path
        self._model: SentenceTransformer | None = None
        self._index: faiss.IndexFlatIP | None = None
        self._concepts: list[I14YConcept] = []

    def _load_model(self) -> "SentenceTransformer":
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer  # noqa: PLC0415
                log.info("loading_embedding_model", model=_MODEL_NAME)
                self._model = SentenceTransformer(_MODEL_NAME)
            except Exception as exc:
                raise EmbeddingError(f"Failed to load model {_MODEL_NAME}: {exc}") from exc
        return self._model

    def encode(self, texts: list[str]) -> np.ndarray:
        model = self._load_model()
        vectors: np.ndarray = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return vectors.astype(np.float32)

    def build_index(self, concepts: list[I14YConcept]) -> None:
        """Build FAISS index from concept searchable texts."""
        if not concepts:
            return
        self._concepts = concepts
        texts = [c.searchable_text for c in concepts]
        vectors = self.encode(texts)
        dim = vectors.shape[1]
        self._index = faiss.IndexFlatIP(dim)  # inner product = cosine (vectors are L2-normalised)
        self._index.add(vectors)
        log.info("faiss_index_built", n_concepts=len(concepts), dim=dim)
        self._save_index()

    def search(self, query: str, top_k: int = 5) -> list[tuple[I14YConcept, float]]:
        """Return top-k (concept, score) pairs for a query string."""
        if self._index is None or not self._concepts:
            return []
        vec = self.encode([query])
        scores, indices = self._index.search(vec, min(top_k, len(self._concepts)))
        results: list[tuple[I14YConcept, float]] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx >= 0:
                results.append((self._concepts[idx], float(score)))
        return results

    def _save_index(self) -> None:
        if self._index is not None:
            self._index_path.parent.mkdir(parents=True, exist_ok=True)
            faiss.write_index(self._index, str(self._index_path))

    def load_index(self, concepts: list[I14YConcept]) -> bool:
        """Load pre-built FAISS index from disk if available."""
        if not self._index_path.exists():
            return False
        try:
            self._index = faiss.read_index(str(self._index_path))
            self._concepts = concepts
            log.info("faiss_index_loaded", path=str(self._index_path))
            return True
        except Exception:
            return False
