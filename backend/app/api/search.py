import logging
import time
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.core.config import get_settings
from app.core.es_client import get_es
from app.embeddings.local import get_embedder
from app.models.schemas import SearchHit, SearchResponse
from app.search.hybrid import (
    build_bm25_only_body,
    build_vector_only_body,
    rrf_fuse,
)

log = logging.getLogger(__name__)
router = APIRouter(tags=["search"])

_REPO_FILTER_PATTERN = r"^[A-Za-z0-9._-]{1,100}$"


def _hit_to_model(h: dict) -> SearchHit:
    src = h.get("_source", {})
    return SearchHit(
        score=float(h.get("_score") or 0.0),
        repo=src.get("repo", ""),
        file_path=src.get("file_path", ""),
        symbol_kind=src.get("symbol_kind", "function"),
        qualified_name=src.get("qualified_name", ""),
        signature=src.get("signature", ""),
        docstring=src.get("docstring", ""),
        code=src.get("code", ""),
        start_line=int(src.get("start_line", 0)),
        end_line=int(src.get("end_line", 0)),
    )


@router.get("/search", response_model=SearchResponse)
def get_search(
    q: str = Query(
        ...,
        min_length=1,
        max_length=2000,
        description="Natural-language or code-like query.",
    ),
    k: int = Query(10, ge=1, le=100),
    mode: str = Query("hybrid", pattern="^(hybrid|bm25|vector)$"),
    repo: Optional[str] = Query(
        None,
        pattern=_REPO_FILTER_PATTERN,
        description="Optional repo filter.",
    ),
) -> SearchResponse:
    settings = get_settings()
    es = get_es()

    if not es.indices.exists(index=settings.es_index):
        raise HTTPException(status_code=404, detail=f"Index '{settings.es_index}' does not exist. Run /index first.")

    started = time.perf_counter()

    try:
        if mode == "bm25":
            body = build_bm25_only_body(q, k=k, repo=repo)
            resp = es.search(index=settings.es_index, body=body)
            es_hits = resp.get("hits", {}).get("hits", [])
            took_ms = int(resp.get("took", 0))

        elif mode == "vector":
            vec = get_embedder().encode_one(q)
            body = build_vector_only_body(vec, k=k, repo=repo)
            resp = es.search(index=settings.es_index, body=body)
            es_hits = resp.get("hits", {}).get("hits", [])
            took_ms = int(resp.get("took", 0))

        else:  # hybrid: client-side RRF over two independent searches
            vec = get_embedder().encode_one(q)
            window = max(50, k * 5)
            bm25_body = build_bm25_only_body(q, k=window, repo=repo)
            vec_body = build_vector_only_body(vec, k=window, repo=repo)
            bm25_resp = es.search(index=settings.es_index, body=bm25_body)
            vec_resp = es.search(index=settings.es_index, body=vec_body)
            took_ms = int(bm25_resp.get("took", 0)) + int(vec_resp.get("took", 0))
            es_hits = rrf_fuse(
                [
                    bm25_resp.get("hits", {}).get("hits", []),
                    vec_resp.get("hits", {}).get("hits", []),
                ],
                k=k,
            )

    except HTTPException:
        raise
    except Exception:  # noqa: BLE001
        log.exception("Search failed")
        raise HTTPException(status_code=500, detail="search failed; see server logs")

    hits: List[SearchHit] = [_hit_to_model(h) for h in es_hits]

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return SearchResponse(
        query=q,
        k=k,
        mode=mode,  # type: ignore[arg-type]
        hits=hits,
        took_ms=max(took_ms, elapsed_ms),
    )
