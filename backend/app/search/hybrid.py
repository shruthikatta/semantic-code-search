"""BM25, dense-vector kNN, and rank fusion helpers.

The live API runs hybrid search as two Elasticsearch queries plus
``rrf_fuse`` so results stay consistent on single-node / Basic clusters.
``build_hybrid_body`` is still handy when you have an ES build that exposes
the native ``rrf`` retriever and want to push fusion down into the cluster.
"""

from __future__ import annotations

from typing import Iterable, Literal


def build_bm25_query(q: str) -> dict:
    return {
        "multi_match": {
            "query": q,
            "fields": [
                "code^1",
                "docstring^2",
                "qualified_name^3",
                "signature^2",
            ],
            "type": "best_fields",
        }
    }


def build_knn_query(vector: list[float], *, k: int, num_candidates: int) -> dict:
    return {
        "field": "embedding",
        "query_vector": vector,
        "k": k,
        "num_candidates": num_candidates,
    }


def build_hybrid_body(
    q: str,
    vector: list[float],
    *,
    k: int = 10,
    rank_window_size: int = 50,
    rank_constant: int = 60,
    repo: str | None = None,
) -> dict:
    """Build the request body for the Elasticsearch ``_search`` endpoint.

    Uses the native RRF retriever to fuse BM25 and kNN results into a single
    ranked list. ``embedding`` is excluded from ``_source`` to keep responses
    small.
    """
    bm25 = build_bm25_query(q)
    knn = build_knn_query(vector, k=k, num_candidates=max(50, k * 10))

    if repo:
        bm25 = {
            "bool": {
                "must": [bm25],
                "filter": [{"term": {"repo": repo}}],
            }
        }
        knn["filter"] = [{"term": {"repo": repo}}]

    return {
        "retriever": {
            "rrf": {
                "retrievers": [
                    {"standard": {"query": bm25}},
                    {"knn": knn},
                ],
                "rank_window_size": rank_window_size,
                "rank_constant": rank_constant,
            }
        },
        "size": k,
        "_source": {"excludes": ["embedding"]},
    }


def build_bm25_only_body(q: str, *, k: int = 10, repo: str | None = None) -> dict:
    query = build_bm25_query(q)
    if repo:
        query = {
            "bool": {
                "must": [query],
                "filter": [{"term": {"repo": repo}}],
            }
        }
    return {
        "query": query,
        "size": k,
        "_source": {"excludes": ["embedding"]},
    }


def build_vector_only_body(
    vector: list[float],
    *,
    k: int = 10,
    repo: str | None = None,
) -> dict:
    knn = build_knn_query(vector, k=k, num_candidates=max(50, k * 10))
    if repo:
        knn["filter"] = [{"term": {"repo": repo}}]
    return {
        "knn": knn,
        "size": k,
        "_source": {"excludes": ["embedding"]},
    }


SearchMode = Literal["hybrid", "bm25", "vector"]


def _hit_id(hit: dict) -> str:
    """Stable identifier for a hit. Falls back to (file_path, lines) if no _id."""
    if "_id" in hit and hit["_id"]:
        return str(hit["_id"])
    src = hit.get("_source", {})
    return f"{src.get('file_path','?')}:{src.get('start_line','?')}-{src.get('end_line','?')}"


def rrf_fuse(
    hit_lists: Iterable[list[dict]],
    *,
    k: int,
    rank_constant: int = 60,
) -> list[dict]:
    """Reciprocal Rank Fusion of multiple ranked hit lists.

    Each input is an Elasticsearch ``hits.hits`` array. The score for an item
    appearing at rank ``r`` (1-based) in a list contributes ``1 / (rank_constant + r)``.
    The returned hits have their ``_score`` overwritten with the RRF score so the
    rest of the pipeline can treat the result like any other ES response.
    """
    scores: dict[str, float] = {}
    payloads: dict[str, dict] = {}

    for hits in hit_lists:
        for rank, hit in enumerate(hits, start=1):
            hid = _hit_id(hit)
            scores[hid] = scores.get(hid, 0.0) + 1.0 / (rank_constant + rank)
            if hid not in payloads:
                payloads[hid] = hit

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:k]
    out: list[dict] = []
    for hid, score in ranked:
        hit = dict(payloads[hid])
        hit["_score"] = score
        out.append(hit)
    return out
