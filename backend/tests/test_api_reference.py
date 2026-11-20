"""Keep the published API reference aligned with FastAPI's active routes."""

import re
from pathlib import Path

from app.main import app


API_REFERENCE = Path(__file__).resolve().parents[2] / "docs" / "API_REFERENCE.md"
API_PREFIX = "/api/v1"


def _canonical_path(path: str) -> str:
    path = path.rstrip("/") or "/"
    return re.sub(r"\{[^}/]+\}", "{}", path)


def _documented_operations(markdown: str) -> set[tuple[str, str]]:
    operations = set()
    for line in markdown.splitlines():
        match = re.match(r"\|\s*([^|]+)\|\s*`([^`]+)`", line)
        if not match:
            continue
        path = match.group(2).split("?", 1)[0]
        methods = re.findall(r"`(GET|POST|PUT|DELETE|PATCH)`", match.group(1))
        operations.update((method, _canonical_path(path)) for method in methods)
    return operations


def test_api_reference_lists_every_active_versioned_operation():
    openapi = app.openapi()
    reference = API_REFERENCE.read_text(encoding="utf-8")
    active_operations = {
        (method.upper(), _canonical_path(path.removeprefix(API_PREFIX)))
        for path, methods in openapi["paths"].items()
        if path.startswith(f"{API_PREFIX}/")
        for method in methods
    }
    documented_operations = _documented_operations(reference)
    extra_paths = {"/", "/health"}
    documented_paths = {"GET /", "GET /health"}
    for method_path in documented_paths:
        method, path = method_path.split(" ", 1)
        assert (method, _canonical_path(path)) in {
            (operation.upper(), _canonical_path(openapi_path))
            for openapi_path, methods in openapi["paths"].items()
            for operation in methods
        }
        assert re.search(rf"`{method}`\s*\|\s*`{re.escape(path)}`", reference)

    missing = active_operations - documented_operations
    stale = documented_operations - active_operations - {
        ("GET", _canonical_path(path)) for path in extra_paths
    }
    assert not missing, f"Active API operations missing from API_REFERENCE.md: {sorted(missing)}"
    assert not stale, f"API_REFERENCE.md operations absent from OpenAPI: {sorted(stale)}"
