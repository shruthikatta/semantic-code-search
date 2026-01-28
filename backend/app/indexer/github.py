"""Clone GitHub repositories and feed them to the local indexer.

The HTTP endpoint mounts ``./samples`` inside the backend container, and the
native runner uses the same layout. Anything cloned into ``samples/`` is
reachable from either mode.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlparse

from app.indexer.service import index_repository

log = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
GITHUB_API_HOST = "api.github.com"
GITHUB_CLONE_HOST = "github.com"
PRIMARY_PYTHON_LANGS = {"Python", "Jupyter Notebook"}


@dataclass
class GitHubRepo:
    name: str
    clone_url: str
    language: Optional[str]


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Treat any 3xx as an error so attacker-controlled redirects can't slip past
    the host allow-list enforced in :func:`_http_get_json`."""

    def http_error_301(self, req, fp, code, msg, headers):  # noqa: D401
        raise urllib.error.HTTPError(req.full_url, code, f"redirect blocked: {msg}", headers, fp)

    http_error_302 = http_error_301
    http_error_303 = http_error_301
    http_error_307 = http_error_301
    http_error_308 = http_error_301


_OPENER = urllib.request.build_opener(_NoRedirectHandler())


def _http_get_json(url: str, *, timeout: int = 30) -> object:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != GITHUB_API_HOST:
        raise ValueError(f"refusing to fetch non-GitHub URL: {url!r}")
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "semantic-code-search",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with _OPENER.open(req, timeout=timeout) as resp:  # noqa: S310 - host validated, redirects blocked
        return json.loads(resp.read().decode())


def _is_safe_clone_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.hostname == GITHUB_CLONE_HOST


def _hardened_git_env() -> dict[str, str]:
    """Environment that disables git features a malicious repo could abuse."""
    env = os.environ.copy()
    env.update(
        {
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": "/bin/true",
            "GIT_LFS_SKIP_SMUDGE": "1",
            "GIT_CONFIG_NOSYSTEM": "1",
        }
    )
    return env


def list_user_repos(owner: str) -> list[GitHubRepo]:
    out: list[GitHubRepo] = []
    page = 1
    while True:
        data = _http_get_json(f"{GITHUB_API}/users/{owner}/repos?per_page=100&page={page}&sort=updated")
        if not isinstance(data, list) or not data:
            break
        for r in data:
            if r.get("fork") or r.get("archived"):
                continue
            out.append(
                GitHubRepo(
                    name=r["name"],
                    clone_url=r["clone_url"],
                    language=r.get("language"),
                )
            )
        if len(data) < 100:
            break
        page += 1
    return out


def clone_or_pull(repo: GitHubRepo, dest_root: Path) -> Path:
    if not _is_safe_clone_url(repo.clone_url):
        raise ValueError(f"refusing to clone non-GitHub URL: {repo.clone_url!r}")
    dest_root = dest_root.resolve()
    target = (dest_root / repo.name).resolve()
    try:
        target.relative_to(dest_root)
    except ValueError as exc:
        raise ValueError(f"repo name escapes samples dir: {repo.name!r}") from exc
    if target.exists():
        log.info("repo already cloned: %s", target)
        return target
    log.info("cloning %s -> %s", repo.clone_url, target)
    subprocess.run(
        [
            "git",
            "-c", "protocol.allow=never",
            "-c", "protocol.https.allow=always",
            "-c", "core.symlinks=false",
            "-c", "filter.lfs.smudge=git-lfs smudge --skip -- %f",
            "clone",
            "--depth", "1",
            "--no-tags",
            "--no-recurse-submodules",
            "--config", "core.hooksPath=/dev/null",
            "--",
            repo.clone_url,
            str(target),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=_hardened_git_env(),
        timeout=300,
    )
    return target


def _has_python(path: Path) -> bool:
    for p in path.rglob("*.py"):
        if ".git" in p.parts:
            continue
        return True
    return False


def index_github_user(
    owner: str,
    samples_root: Path,
    *,
    repos: Optional[Iterable[str]] = None,
    include_non_python: bool = False,
    drop_existing: bool = False,
) -> dict:
    samples_root.mkdir(parents=True, exist_ok=True)

    available = list_user_repos(owner)
    if repos is not None:
        wanted = set(repos)
        available = [r for r in available if r.name in wanted]

    indexed: list[dict] = []
    skipped: list[dict] = []
    drop = drop_existing
    total_chunks = 0
    total_loc = 0

    for r in available:
        if (
            not include_non_python
            and r.language
            and r.language not in PRIMARY_PYTHON_LANGS
        ):
            skipped.append({"repo": r.name, "reason": f"primary language is {r.language}"})
            continue

        try:
            target = clone_or_pull(r, samples_root)
        except subprocess.CalledProcessError as e:
            skipped.append({"repo": r.name, "reason": f"git clone failed: {e.stderr.strip() or e}"})
            continue

        if not _has_python(target):
            skipped.append({"repo": r.name, "reason": "no .py files found"})
            continue

        try:
            stats = index_repository(target, r.name, drop_existing=drop)
        except Exception as e:  # noqa: BLE001
            skipped.append({"repo": r.name, "reason": f"index_repository failed: {e}"})
            continue

        drop = False  # only drop once, on the first successfully-indexed repo
        indexed.append(
            {
                "repo": r.name,
                "chunks_indexed": stats.chunks_indexed,
                "files_parsed": stats.files_parsed,
                "total_loc": stats.total_loc,
                "duration_seconds": stats.duration_seconds,
            }
        )
        total_chunks += stats.chunks_indexed
        total_loc += stats.total_loc

    return {
        "owner": owner,
        "indexed": indexed,
        "skipped": skipped,
        "total_chunks_indexed": total_chunks,
        "total_loc": total_loc,
    }


__all__ = [
    "GitHubRepo",
    "list_user_repos",
    "clone_or_pull",
    "index_github_user",
    "PRIMARY_PYTHON_LANGS",
]
