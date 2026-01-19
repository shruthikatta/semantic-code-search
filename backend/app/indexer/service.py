"""Repository indexing pipeline: walk -> chunk -> embed -> bulk-index."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

import pathspec
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

from app.chunker.python_ast import chunk_file
from app.core.config import get_settings
from app.core.es_client import get_es
from app.core.index_schema import drop_index, ensure_index
from app.embeddings.local import LocalEmbedder, get_embedder
from app.models.schemas import CodeChunk

log = logging.getLogger(__name__)

DEFAULT_IGNORES = [
    ".git/",
    "__pycache__/",
    "*.pyc",
    ".venv/",
    "venv/",
    "node_modules/",
    ".mypy_cache/",
    ".pytest_cache/",
    ".ruff_cache/",
    "dist/",
    "build/",
    "*.egg-info/",
]


@dataclass
class IndexStats:
    repo: str
    files_scanned: int = 0
    files_parsed: int = 0
    files_failed: int = 0
    chunks_indexed: int = 0
    total_loc: int = 0
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)


def _load_gitignore(root: Path) -> pathspec.PathSpec:
    patterns = list(DEFAULT_IGNORES)
    gi = root / ".gitignore"
    if gi.exists():
        try:
            patterns.extend(gi.read_text(encoding="utf-8", errors="ignore").splitlines())
        except OSError:
            pass
    return pathspec.PathSpec.from_lines("gitwildmatch", patterns)


def iter_python_files(root: Path) -> Iterator[Path]:
    spec = _load_gitignore(root)
    for path in root.rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        if spec.match_file(rel):
            continue
        if path.is_file():
            yield path


def _chunk_to_action(chunk: CodeChunk, embedding: list[float], index: str) -> dict:
    return {
        "_op_type": "index",
        "_index": index,
        "_id": chunk.doc_id(),
        "_source": {
            "repo": chunk.repo,
            "file_path": chunk.file_path,
            "symbol_kind": chunk.symbol_kind,
            "qualified_name": chunk.qualified_name,
            "signature": chunk.signature,
            "docstring": chunk.docstring,
            "code": chunk.code,
            "start_line": chunk.start_line,
            "end_line": chunk.end_line,
            "loc": chunk.loc,
            "embedding": embedding,
        },
    }


def _embedding_text(chunk: CodeChunk) -> str:
    """Text fed to the embedder. Includes signature + docstring + code so the
    semantic vector captures both natural-language intent and implementation."""
    parts = [chunk.signature]
    if chunk.docstring:
        parts.append(chunk.docstring)
    parts.append(chunk.code)
    return "\n".join(parts).strip()


def _batched(iterable: Iterable[CodeChunk], size: int) -> Iterator[list[CodeChunk]]:
    batch: list[CodeChunk] = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def index_repository(
    repo_path: str | Path,
    repo_name: str,
    *,
    drop_existing: bool = False,
    es: Elasticsearch | None = None,
    embedder: LocalEmbedder | None = None,
) -> IndexStats:
    """Walk ``repo_path`` and index every Python chunk into Elasticsearch."""
    settings = get_settings()
    es = es or get_es()
    embedder = embedder or get_embedder()

    root = Path(repo_path).resolve()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"Repository path does not exist or is not a directory: {root}")

    if drop_existing:
        drop_index(es, settings.es_index)
    ensure_index(es, settings.es_index, settings.embedding_dim)

    if not es.indices.exists(index=settings.es_index):
        ensure_index(es, settings.es_index, settings.embedding_dim)

    start = time.perf_counter()
    stats = IndexStats(repo=repo_name)

    max_bytes = settings.indexer_max_file_bytes

    def chunk_iter() -> Iterator[CodeChunk]:
        for f in iter_python_files(root):
            stats.files_scanned += 1
            try:
                chunks = chunk_file(f, repo=repo_name, repo_root=root, max_bytes=max_bytes)
            except Exception as exc:  # noqa: BLE001
                stats.files_failed += 1
                stats.errors.append(f"{f}: {exc}")
                continue
            if chunks:
                stats.files_parsed += 1
                for c in chunks:
                    stats.total_loc += c.loc
                    yield c

    batch_size = settings.index_bulk_chunk_size
    for batch in _batched(chunk_iter(), batch_size):
        texts = [_embedding_text(c) for c in batch]
        vectors = embedder.encode(texts)
        actions = [_chunk_to_action(c, vec.tolist(), settings.es_index) for c, vec in zip(batch, vectors)]
        success, errors = bulk(es, actions, raise_on_error=False, request_timeout=120)
        stats.chunks_indexed += success
        if errors:
            for err in errors[:5]:
                stats.errors.append(str(err))

    es.indices.refresh(index=settings.es_index)
    stats.duration_seconds = round(time.perf_counter() - start, 3)
    log.info(
        "Indexed repo=%s files=%d chunks=%d loc=%d in %.2fs",
        repo_name,
        stats.files_parsed,
        stats.chunks_indexed,
        stats.total_loc,
        stats.duration_seconds,
    )
    return stats
