from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Iterator

import pytest

# Ensure the backend package is importable when pytest is run from any cwd.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def client() -> Iterator:
    """Return a fresh TestClient backed by a temporary SQLite file.

    Each test gets a clean DB so tests do not leak state into each other.
    """
    from fastapi.testclient import TestClient

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    os.environ["JOBAPPLY_DATABASE_URL"] = f"sqlite:///{tmp.name}"

    # Reload modules so the engine picks up the new env var.
    for mod_name in [
        "app.main",
        "app.routers.applications",
        "app.routers.captures",
        "app.routers.evidence_banks",
        "app.routers.jobs",
        "app.routers.master_resumes",
        "app.routers",
        "app.schemas",
        "app.models",
        "app.db",
        "app",
    ]:
        sys.modules.pop(mod_name, None)

    from app.main import app  # noqa: E402  (deliberate post-env import)

    with TestClient(app) as c:
        yield c

    try:
        os.unlink(tmp.name)
    except FileNotFoundError:
        pass
