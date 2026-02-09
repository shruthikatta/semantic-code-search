from pathlib import Path

from app.chunker.python_ast import chunk_file, chunk_source

FIXTURE = Path(__file__).parent / "fixtures" / "sample_module.py"


def test_chunk_fixture_module_has_expected_symbols():
    chunks = chunk_file(FIXTURE, repo="fix", repo_root=FIXTURE.parent)
    by_qname = {(c.symbol_kind, c.qualified_name): c for c in chunks}

    assert ("function", "add") in by_qname
    assert ("function", "fetch") in by_qname
    assert ("class", "Calculator") in by_qname
    assert ("method", "Calculator.__init__") in by_qname
    assert ("method", "Calculator.add") in by_qname
    assert ("class", "Calculator.Inner") in by_qname
    assert ("method", "Calculator.Inner.ping") in by_qname
    assert ("function", "sum_iter") in by_qname
    assert ("module", "sample_module.<module>") in by_qname


def test_chunk_function_signature_and_docstring():
    chunks = chunk_file(FIXTURE, repo="fix", repo_root=FIXTURE.parent)
    by_qname = {c.qualified_name: c for c in chunks if c.symbol_kind == "function"}

    add_chunk = by_qname["add"]
    assert add_chunk.signature == "def add(a: int, b: int = 0) -> int"
    assert add_chunk.docstring == "Return the sum of a and b."
    assert add_chunk.start_line >= 1
    assert add_chunk.end_line >= add_chunk.start_line
    assert "return a + b" in add_chunk.code


def test_async_function_signature_starts_with_async():
    chunks = chunk_file(FIXTURE, repo="fix", repo_root=FIXTURE.parent)
    fetch = next(c for c in chunks if c.qualified_name == "fetch")
    assert fetch.signature.startswith("async def fetch(")
    assert "timeout: float = 1.0" in fetch.signature
    assert "-> str" in fetch.signature


def test_class_signature_and_methods():
    chunks = chunk_file(FIXTURE, repo="fix", repo_root=FIXTURE.parent)
    cls = next(c for c in chunks if c.qualified_name == "Calculator" and c.symbol_kind == "class")
    assert cls.signature == "class Calculator"
    assert cls.docstring == "A toy calculator."

    method = next(c for c in chunks if c.qualified_name == "Calculator.add")
    assert method.symbol_kind == "method"
    assert method.signature == "def add(self, x: float) -> float"


def test_module_residue_chunk_captures_top_level():
    chunks = chunk_file(FIXTURE, repo="fix", repo_root=FIXTURE.parent)
    residue = next(c for c in chunks if c.symbol_kind == "module")
    assert "PI = 3.14159" in residue.code
    assert "import math" in residue.code


def test_chunk_source_handles_syntax_error():
    chunks = chunk_source("def !!!", repo="r", file_path="bad.py")
    assert chunks == []


def test_doc_id_is_stable_and_unique():
    chunks = chunk_file(FIXTURE, repo="fix", repo_root=FIXTURE.parent)
    ids = [c.doc_id() for c in chunks]
    assert len(ids) == len(set(ids))
