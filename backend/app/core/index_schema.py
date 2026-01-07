from __future__ import annotations

from elasticsearch import Elasticsearch

from app.core.config import get_settings


def build_mapping(embedding_dim: int) -> dict:
    return {
        "settings": {
            "analysis": {
                "analyzer": {
                    "code_text": {
                        "type": "standard",
                    }
                }
            }
        },
        "mappings": {
            "properties": {
                "repo": {"type": "keyword"},
                "file_path": {"type": "keyword"},
                "symbol_kind": {"type": "keyword"},
                "qualified_name": {
                    "type": "text",
                    "fields": {"kw": {"type": "keyword", "ignore_above": 512}},
                },
                "signature": {"type": "text"},
                "docstring": {"type": "text"},
                "code": {"type": "text", "analyzer": "code_text"},
                "start_line": {"type": "integer"},
                "end_line": {"type": "integer"},
                "loc": {"type": "integer"},
                "embedding": {
                    "type": "dense_vector",
                    "dims": embedding_dim,
                    "index": True,
                    "similarity": "cosine",
                },
            }
        },
    }


def ensure_index(es: Elasticsearch, index: str | None = None, embedding_dim: int | None = None) -> bool:
    """Create the index if it does not already exist. Returns True when created."""
    settings = get_settings()
    index = index or settings.es_index
    embedding_dim = embedding_dim or settings.embedding_dim

    if es.indices.exists(index=index):
        return False

    es.indices.create(index=index, body=build_mapping(embedding_dim))
    return True


def drop_index(es: Elasticsearch, index: str | None = None) -> bool:
    settings = get_settings()
    index = index or settings.es_index
    if not es.indices.exists(index=index):
        return False
    es.indices.delete(index=index)
    return True
