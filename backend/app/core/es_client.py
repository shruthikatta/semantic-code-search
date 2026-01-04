from functools import lru_cache

from elasticsearch import Elasticsearch

from app.core.config import get_settings


@lru_cache
def get_es() -> Elasticsearch:
    settings = get_settings()
    return Elasticsearch(
        hosts=[settings.elasticsearch_url],
        request_timeout=60,
        retry_on_timeout=True,
        max_retries=3,
    )
