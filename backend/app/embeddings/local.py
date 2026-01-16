"""Local sentence-transformers embedder.

The model is loaded lazily on first use so test imports and the ``/health``
endpoint don't pay the model-load cost. Output vectors are L2-normalized to
match the cosine similarity used by the Elasticsearch dense_vector field.
"""

from __future__ import annotations

import logging
import threading
from functools import lru_cache
from typing import Iterable, Sequence

import numpy as np

from app.core.config import get_settings

log = logging.getLogger(__name__)

_LOCK = threading.Lock()


class LocalEmbedder:
    def __init__(
        self,
        model_name: str,
        *,
        batch_size: int = 16,
        max_seq_length: int = 1024,
        max_chars: int = 6000,
        device: str = "auto",
        trust_remote_code: bool = False,
    ) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        self.max_seq_length = max_seq_length
        self.max_chars = max_chars
        self.device = device
        self.trust_remote_code = trust_remote_code
        self._model = None  # lazy

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        with _LOCK:
            if self._model is not None:
                return
            log.info(
                "Loading sentence-transformer: %s (trust_remote_code=%s)",
                self.model_name,
                self.trust_remote_code,
            )
            from sentence_transformers import SentenceTransformer

            kwargs: dict = {"trust_remote_code": self.trust_remote_code}
            if self.device and self.device != "auto":
                kwargs["device"] = self.device
            self._model = SentenceTransformer(self.model_name, **kwargs)

            # Cap sequence length. Jina v2 base code defaults to 8192, which
            # blows up MPS memory at moderate batch sizes.
            try:
                self._model.max_seq_length = self.max_seq_length
            except Exception:  # noqa: BLE001
                pass

            log.info(
                "Loaded sentence-transformer: %s (device=%s, max_seq_length=%s, batch=%s)",
                self.model_name,
                getattr(self._model, "device", "?"),
                getattr(self._model, "max_seq_length", "?"),
                self.batch_size,
            )

    @property
    def dim(self) -> int:
        self._ensure_loaded()
        assert self._model is not None
        return int(self._model.get_sentence_embedding_dimension())

    def _clip(self, text: str) -> str:
        if self.max_chars and len(text) > self.max_chars:
            return text[: self.max_chars]
        return text

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((self.dim,), dtype=np.float32).reshape(0, -1)
        self._ensure_loaded()
        assert self._model is not None
        clipped = [self._clip(t) for t in texts]
        vecs = self._model.encode(
            clipped,
            batch_size=self.batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vecs.astype(np.float32, copy=False)

    def encode_one(self, text: str) -> list[float]:
        return self.encode([text])[0].tolist()

    def encode_iter(self, texts: Iterable[str]) -> Iterable[list[float]]:
        buf: list[str] = []
        for t in texts:
            buf.append(t)
            if len(buf) >= self.batch_size:
                for v in self.encode(buf):
                    yield v.tolist()
                buf.clear()
        if buf:
            for v in self.encode(buf):
                yield v.tolist()


@lru_cache
def get_embedder() -> LocalEmbedder:
    settings = get_settings()
    return LocalEmbedder(
        settings.embedding_model,
        batch_size=settings.embedding_batch_size,
        max_seq_length=settings.embedding_max_seq_length,
        max_chars=settings.embedding_max_chars,
        device=settings.embedding_device,
        trust_remote_code=settings.embedding_trust_remote_code,
    )
