from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    elasticsearch_url: str = "http://localhost:9200"
    es_index: str = "code_chunks"

    embedding_model: str = "jinaai/jina-embeddings-v2-base-code"
    embedding_dim: int = 768
    embedding_batch_size: int = 16
    embedding_max_seq_length: int = 1024
    embedding_max_chars: int = 6000
    embedding_device: str = "auto"
    embedding_trust_remote_code: bool = False

    indexer_max_file_bytes: int = 2 * 1024 * 1024
    search_query_max_length: int = 2000

    index_bulk_chunk_size: int = 100

    samples_dir: str = "/samples"

    cors_origins: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
