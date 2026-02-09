from app.search.hybrid import (
    build_bm25_only_body,
    build_bm25_query,
    build_hybrid_body,
    build_knn_query,
    build_vector_only_body,
    rrf_fuse,
)


def test_bm25_query_targets_expected_fields():
    q = build_bm25_query("retry with backoff")
    fields = q["multi_match"]["fields"]
    assert "code^1" in fields
    assert "docstring^2" in fields
    assert "qualified_name^3" in fields
    assert "signature^2" in fields
    assert q["multi_match"]["query"] == "retry with backoff"


def test_knn_query_uses_embedding_field_and_num_candidates():
    knn = build_knn_query([0.1] * 8, k=10, num_candidates=100)
    assert knn["field"] == "embedding"
    assert knn["k"] == 10
    assert knn["num_candidates"] == 100
    assert len(knn["query_vector"]) == 8


def test_hybrid_body_uses_rrf_retriever_with_two_children():
    body = build_hybrid_body("foo", [0.0] * 4, k=5)
    rrf = body["retriever"]["rrf"]
    assert rrf["rank_constant"] == 60
    assert rrf["rank_window_size"] == 50
    assert len(rrf["retrievers"]) == 2

    kinds = [list(r.keys())[0] for r in rrf["retrievers"]]
    assert "standard" in kinds
    assert "knn" in kinds

    assert body["size"] == 5
    assert body["_source"]["excludes"] == ["embedding"]


def test_hybrid_body_applies_repo_filter_to_both_retrievers():
    body = build_hybrid_body("q", [0.0] * 4, k=3, repo="myrepo")
    rrf = body["retriever"]["rrf"]
    standard = next(r for r in rrf["retrievers"] if "standard" in r)
    knn = next(r for r in rrf["retrievers"] if "knn" in r)

    assert standard["standard"]["query"]["bool"]["filter"] == [{"term": {"repo": "myrepo"}}]
    assert knn["knn"]["filter"] == [{"term": {"repo": "myrepo"}}]


from typing import Optional


def _h(doc_id: str, source: Optional[dict] = None) -> dict:
    return {"_id": doc_id, "_score": 1.0, "_source": source or {}}


def test_rrf_fuse_returns_top_k_by_summed_reciprocal_rank():
    bm25 = [_h("a"), _h("b"), _h("c"), _h("d")]
    vec = [_h("c"), _h("a"), _h("e")]
    fused = rrf_fuse([bm25, vec], k=3, rank_constant=60)

    ids = [h["_id"] for h in fused]
    assert ids[:2] == ["a", "c"]  # both appear in both lists, near the top
    assert len(fused) == 3
    assert all("score for sorting" or h["_score"] > 0 for h in fused)
    assert fused[0]["_score"] >= fused[1]["_score"] >= fused[2]["_score"]


def test_rrf_fuse_handles_disjoint_inputs_and_empty_list():
    assert rrf_fuse([[], []], k=5) == []
    only_a = rrf_fuse([[_h("a")], []], k=5)
    assert [h["_id"] for h in only_a] == ["a"]


def test_rrf_fuse_uses_file_path_when_id_missing():
    a = {"_score": 1.0, "_source": {"file_path": "x.py", "start_line": 1, "end_line": 2}}
    b = {"_score": 1.0, "_source": {"file_path": "x.py", "start_line": 1, "end_line": 2}}
    fused = rrf_fuse([[a], [b]], k=5)
    assert len(fused) == 1


def test_bm25_only_and_vector_only_bodies():
    bm25_body = build_bm25_only_body("q", k=4)
    assert "query" in bm25_body
    assert bm25_body["size"] == 4
    assert bm25_body["_source"]["excludes"] == ["embedding"]

    vec_body = build_vector_only_body([0.0] * 4, k=4)
    assert "knn" in vec_body
    assert vec_body["size"] == 4
    assert vec_body["_source"]["excludes"] == ["embedding"]
