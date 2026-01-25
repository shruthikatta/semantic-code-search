from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.core.es_client import get_es
from app.core.index_schema import drop_index, ensure_index
from app.indexer.github import index_github_user
from app.indexer.service import index_repository
from app.models.schemas import (
    GitHubIndexRequest,
    GitHubIndexResponse,
    IndexRequest,
    IndexResponse,
)

log = logging.getLogger(__name__)
router = APIRouter(tags=["indexing"])

_OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
_REPO_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")


def _resolve_under_samples(raw_path: str) -> Path:
    """Resolve a caller-supplied path and require it to live under ``samples_dir``.

    Prevents the indexer from being pointed at arbitrary files on the host
    (e.g. ``/etc``) and exfiltrating their contents through ``/search``.
    """
    settings = get_settings()
    samples_root = Path(settings.samples_dir).resolve()
    candidate = Path(raw_path).resolve()
    try:
        candidate.relative_to(samples_root)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"path must live under samples_dir ({samples_root})",
        ) from exc
    return candidate


@router.post("/index", response_model=IndexResponse)
def post_index(req: IndexRequest) -> IndexResponse:
    if not _REPO_NAME_RE.match(req.repo):
        raise HTTPException(status_code=400, detail="invalid repo name")
    safe_path = _resolve_under_samples(req.path)
    try:
        stats = index_repository(str(safe_path), req.repo, drop_existing=req.drop_existing)
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception:  # noqa: BLE001
        log.exception("Indexing failed")
        raise HTTPException(status_code=500, detail="indexing failed; see server logs")
    return IndexResponse(
        repo=stats.repo,
        files_scanned=stats.files_scanned,
        files_parsed=stats.files_parsed,
        files_failed=stats.files_failed,
        chunks_indexed=stats.chunks_indexed,
        total_loc=stats.total_loc,
        duration_seconds=stats.duration_seconds,
    )


@router.post("/index/github", response_model=GitHubIndexResponse)
def post_index_github(req: GitHubIndexRequest) -> GitHubIndexResponse:
    if not _OWNER_RE.match(req.owner):
        raise HTTPException(status_code=400, detail="invalid GitHub owner")
    if req.repos is not None:
        for name in req.repos:
            if not _REPO_NAME_RE.match(name):
                raise HTTPException(status_code=400, detail=f"invalid repo name: {name!r}")
    settings = get_settings()
    samples_root = Path(settings.samples_dir).resolve()
    try:
        result = index_github_user(
            req.owner,
            samples_root,
            repos=req.repos,
            include_non_python=req.include_non_python,
            drop_existing=req.drop_existing,
        )
    except Exception:  # noqa: BLE001
        log.exception("GitHub indexing failed")
        raise HTTPException(status_code=500, detail="github indexing failed; see server logs")
    return GitHubIndexResponse(**result)


@router.delete("/index")
def delete_index() -> dict:
    settings = get_settings()
    es = get_es()
    dropped = drop_index(es, settings.es_index)
    ensure_index(es, settings.es_index, settings.embedding_dim)
    return {"dropped": dropped, "recreated": True, "index": settings.es_index}


@router.get("/index/stats")
def index_stats() -> dict:
    settings = get_settings()
    es = get_es()
    if not es.indices.exists(index=settings.es_index):
        return {"index": settings.es_index, "exists": False}
    count = es.count(index=settings.es_index).get("count", 0)
    repos: list[str] = []
    try:
        agg = es.search(
            index=settings.es_index,
            size=0,
            aggs={"repos": {"terms": {"field": "repo", "size": 50}}},
        )
        repos = [b["key"] for b in agg["aggregations"]["repos"]["buckets"]]
    except Exception:  # noqa: BLE001
        repos = []
    return {"index": settings.es_index, "exists": True, "doc_count": count, "repos": repos}
