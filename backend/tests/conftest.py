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
    # Default the filesystem master-resume discovery root to a fresh empty
    # directory so tests don't pick up the repo's real
    # ``candidate_context/master_resumes/`` folder. Tests that exercise
    # discovery override this with their own root via monkeypatch.
    master_resumes_dir = tempfile.mkdtemp(prefix="jobapply-master-resumes-")
    os.environ["JOBAPPLY_MASTER_RESUMES_ROOT"] = master_resumes_dir

    # Reload modules so the engine picks up the new env var.
    for mod_name in [
        "app.main",
        "app.routers.activity",
        "app.routers.applications",
        "app.routers.captures",
        "app.routers.evidence_banks",
        "app.routers.evidence_sources",
        "app.routers.files",
        "app.routers.gmail",
        "app.routers.jobs",
        "app.routers.llm_providers",
        "app.routers.local_llm",
        "app.routers.master_resumes",
        "app.routers.prompts",
        "app.routers.resume_versions",
        "app.routers.runs",
        "app.routers.settings",
        "app.routers",
        "app.prompt_harness",
        "app.run_directory",
        "app.evidence_source_discovery",
        "app.master_resume_discovery",
        "app.file_import",
        "app.local_reset",
        "app.run_import",
        "app.claude_worker",
        "app.llm_providers",
        "app.local_llm",
        "app.gmail_client",
        "app.settings",
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
    import shutil

    shutil.rmtree(master_resumes_dir, ignore_errors=True)
