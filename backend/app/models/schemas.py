from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

SymbolKind = Literal["function", "method", "class", "module"]


class CodeChunk(BaseModel):
    repo: str
    file_path: str
    symbol_kind: SymbolKind
    qualified_name: str
    signature: str = ""
    docstring: str = ""
    code: str
    start_line: int
    end_line: int

    @property
    def loc(self) -> int:
        return max(0, self.end_line - self.start_line + 1)

    def doc_id(self) -> str:
        return f"{self.repo}:{self.file_path}:{self.symbol_kind}:{self.qualified_name}:{self.start_line}-{self.end_line}"


class IndexRequest(BaseModel):
    path: str = Field(
        ...,
        description=(
            "Absolute path to a Python repository on the backend filesystem. "
            "Must resolve to a location inside SAMPLES_DIR (default /samples)."
        ),
    )
    repo: str = Field(..., description="Logical repository name used for filtering and display.")
    drop_existing: bool = Field(False, description="Drop the index before reindexing.")


class GitHubIndexRequest(BaseModel):
    owner: str = Field(..., description="GitHub username or organization.")
    repos: Optional[List[str]] = Field(
        None,
        description="Optional explicit list of repo names. If omitted, all non-fork, non-archived public repos are considered.",
    )
    include_non_python: bool = Field(
        False,
        description="Also clone repos whose primary language is not Python. Only .py files are ever indexed.",
    )
    drop_existing: bool = Field(False, description="Drop the index before reindexing the first repo.")


class GitHubIndexedRepo(BaseModel):
    repo: str
    chunks_indexed: int
    files_parsed: int
    total_loc: int
    duration_seconds: float


class GitHubSkippedRepo(BaseModel):
    repo: str
    reason: str


class GitHubIndexResponse(BaseModel):
    owner: str
    indexed: List[GitHubIndexedRepo]
    skipped: List[GitHubSkippedRepo]
    total_chunks_indexed: int
    total_loc: int


class IndexResponse(BaseModel):
    repo: str
    files_scanned: int
    files_parsed: int
    files_failed: int
    chunks_indexed: int
    total_loc: int
    duration_seconds: float


class SearchHit(BaseModel):
    score: float
    repo: str
    file_path: str
    symbol_kind: SymbolKind
    qualified_name: str
    signature: str
    docstring: str
    code: str
    start_line: int
    end_line: int


class SearchResponse(BaseModel):
    query: str
    k: int
    mode: Literal["hybrid", "bm25", "vector"]
    hits: list[SearchHit]
    took_ms: int
