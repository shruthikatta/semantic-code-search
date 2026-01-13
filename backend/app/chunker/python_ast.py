"""AST-aware chunking for Python source files.

Each top-level function, method, async function, and class becomes its own
``CodeChunk``. Top-level statements that aren't inside any class/function are
collected into a single "module residue" chunk so that imports, constants, and
script-level code remain searchable.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Union

from app.models.schemas import CodeChunk, SymbolKind

DefNode = Union[ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef]


@dataclass
class _Parent:
    name: str
    is_class: bool


def _kind(node: DefNode, parents: list[_Parent]) -> SymbolKind:
    if isinstance(node, ast.ClassDef):
        return "class"
    if parents and parents[-1].is_class:
        return "method"
    return "function"


def _qualname(node: DefNode, parents: list[_Parent]) -> str:
    parts = [p.name for p in parents] + [node.name]
    return ".".join(parts)


def _format_args(args: ast.arguments) -> str:
    pieces: list[str] = []

    posonly = list(args.posonlyargs)
    regular = list(args.args)
    defaults = list(args.defaults)

    pos_total = posonly + regular
    n_defaults = len(defaults)
    n_no_default = len(pos_total) - n_defaults

    for i, a in enumerate(pos_total):
        s = a.arg
        if a.annotation is not None:
            s += f": {ast.unparse(a.annotation)}"
        if i >= n_no_default:
            d = defaults[i - n_no_default]
            s += f" = {ast.unparse(d)}"
        pieces.append(s)
        if posonly and i == len(posonly) - 1:
            pieces.append("/")

    if args.vararg is not None:
        v = "*" + args.vararg.arg
        if args.vararg.annotation is not None:
            v += f": {ast.unparse(args.vararg.annotation)}"
        pieces.append(v)
    elif args.kwonlyargs:
        pieces.append("*")

    for a, d in zip(args.kwonlyargs, args.kw_defaults):
        s = a.arg
        if a.annotation is not None:
            s += f": {ast.unparse(a.annotation)}"
        if d is not None:
            s += f" = {ast.unparse(d)}"
        pieces.append(s)

    if args.kwarg is not None:
        k = "**" + args.kwarg.arg
        if args.kwarg.annotation is not None:
            k += f": {ast.unparse(args.kwarg.annotation)}"
        pieces.append(k)

    return ", ".join(pieces)


def _signature(node: DefNode) -> str:
    if isinstance(node, ast.ClassDef):
        bases = ", ".join(ast.unparse(b) for b in node.bases)
        return f"class {node.name}({bases})" if bases else f"class {node.name}"

    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    args = _format_args(node.args)
    sig = f"{prefix} {node.name}({args})"
    if node.returns is not None:
        sig += f" -> {ast.unparse(node.returns)}"
    return sig


def _iter_defs(node: ast.AST) -> Iterable[DefNode]:
    for child in getattr(node, "body", []):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            yield child


def _walk(
    node: ast.AST,
    source: str,
    parents: list[_Parent],
    repo: str,
    file_path: str,
    out: list[CodeChunk],
) -> None:
    for child in _iter_defs(node):
        code = ast.get_source_segment(source, child) or ""
        chunk = CodeChunk(
            repo=repo,
            file_path=file_path,
            symbol_kind=_kind(child, parents),
            qualified_name=_qualname(child, parents),
            signature=_signature(child),
            docstring=ast.get_docstring(child) or "",
            code=code,
            start_line=child.lineno,
            end_line=child.end_lineno or child.lineno,
        )
        out.append(chunk)
        parents.append(_Parent(name=child.name, is_class=isinstance(child, ast.ClassDef)))
        try:
            _walk(child, source, parents, repo, file_path, out)
        finally:
            parents.pop()


def _module_residue(tree: ast.Module, source: str, repo: str, file_path: str) -> CodeChunk | None:
    """Collect top-level statements that aren't function/class definitions."""
    residue_nodes: list[ast.stmt] = [
        n for n in tree.body if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    if not residue_nodes:
        return None

    segments: list[str] = []
    start_line = residue_nodes[0].lineno
    end_line = residue_nodes[0].end_lineno or residue_nodes[0].lineno
    for n in residue_nodes:
        seg = ast.get_source_segment(source, n)
        if seg:
            segments.append(seg)
        if n.end_lineno and n.end_lineno > end_line:
            end_line = n.end_lineno
        if n.lineno < start_line:
            start_line = n.lineno

    code = "\n\n".join(s for s in segments if s).strip()
    if not code:
        return None

    docstring = ast.get_docstring(tree) or ""
    module_name = Path(file_path).stem
    return CodeChunk(
        repo=repo,
        file_path=file_path,
        symbol_kind="module",
        qualified_name=f"{module_name}.<module>",
        signature=f"module {module_name}",
        docstring=docstring,
        code=code,
        start_line=start_line,
        end_line=end_line,
    )


def chunk_source(source: str, *, repo: str, file_path: str) -> list[CodeChunk]:
    """Parse ``source`` and return the list of code chunks for it."""
    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError:
        return []

    chunks: list[CodeChunk] = []
    _walk(tree, source, [], repo, file_path, chunks)

    residue = _module_residue(tree, source, repo, file_path)
    if residue is not None:
        chunks.append(residue)

    return chunks


def chunk_file(
    path: Path,
    *,
    repo: str,
    repo_root: Path,
    max_bytes: int | None = None,
) -> list[CodeChunk]:
    """Read ``path`` and return its code chunks. ``file_path`` is stored relative to ``repo_root``.

    Files larger than ``max_bytes`` are skipped to keep a single huge ``.py`` file
    from OOMing the backend.
    """
    try:
        if max_bytes is not None and path.stat().st_size > max_bytes:
            return []
        source = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []

    rel = path.relative_to(repo_root).as_posix() if path.is_absolute() else path.as_posix()
    return chunk_source(source, repo=repo, file_path=rel)
