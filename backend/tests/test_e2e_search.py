"""End-to-end test that hits a running compose stack.

Run with::

    docker compose up -d
    cd backend && RUN_E2E=1 pytest tests/test_e2e_search.py -m e2e
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

if not os.getenv("RUN_E2E"):
    pytest.skip("Set RUN_E2E=1 to run end-to-end tests against a live stack.", allow_module_level=True)


import time
import urllib.error
import urllib.request
import json

API = os.getenv("API_BASE", "http://localhost:8000")
REPO_PATH = os.getenv("E2E_REPO_PATH", str(Path(__file__).parent / "fixtures"))
REPO_NAME = os.getenv("E2E_REPO_NAME", "fixture")


def _get(path: str) -> dict:
    with urllib.request.urlopen(f"{API}{path}", timeout=30) as r:
        return json.loads(r.read().decode())


def _post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode())


def _wait_for_health(retries: int = 60) -> None:
    for _ in range(retries):
        try:
            data = _get("/health")
            if data.get("elasticsearch"):
                return
        except (urllib.error.URLError, ConnectionError):
            pass
        time.sleep(2)
    raise RuntimeError("backend did not become healthy")


def test_index_and_search_round_trip():
    _wait_for_health()
    stats = _post("/index", {"path": REPO_PATH, "repo": REPO_NAME, "drop_existing": True})
    assert stats["chunks_indexed"] >= 1

    resp = _get(f"/search?q=add+two+numbers&k=5")
    assert resp["mode"] == "hybrid"
    assert len(resp["hits"]) >= 1
    qnames = [h["qualified_name"] for h in resp["hits"]]
    assert any("add" in q for q in qnames)
