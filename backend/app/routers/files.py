from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Iterable

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ResumeVersion
from ..run_directory import default_resume_versions_root, default_runs_root
from ..schemas import FileOpenRequest

router = APIRouter(prefix="/files", tags=["files"])


def _spawn_open_command(path: Path) -> None:
    """Ask the host OS to open ``path`` in its default application.

    Wrapped in a dedicated function so tests can monkeypatch it instead of
    actually launching a GUI app.
    """
    if sys.platform == "darwin":
        cmd = ["open", str(path)]
    elif sys.platform.startswith("win"):
        cmd = ["cmd", "/c", "start", "", str(path)]
    else:
        cmd = ["xdg-open", str(path)]
    subprocess.Popen(cmd, close_fds=True)


def _allowed_roots() -> list[Path]:
    return [default_runs_root().resolve(), default_resume_versions_root().resolve()]


def _is_inside_allowed_root(resolved: Path, roots: Iterable[Path]) -> bool:
    for root in roots:
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        return True
    return False


@router.post("/open", status_code=status.HTTP_204_NO_CONTENT)
def open_file(payload: FileOpenRequest, db: Session = Depends(get_db)) -> Response:
    if payload.resume_version_id is None and not payload.path:
        raise HTTPException(
            status_code=422,
            detail="must provide either path or resume_version_id",
        )

    if payload.resume_version_id is not None:
        version = db.get(ResumeVersion, payload.resume_version_id)
        if version is None or not version.docx_path:
            raise HTTPException(status_code=404, detail="resume version not found")
        candidate = Path(version.docx_path)
    else:
        candidate = Path(payload.path)  # type: ignore[arg-type]

    try:
        resolved = candidate.resolve()
    except OSError as exc:
        raise HTTPException(status_code=404, detail="path not found") from exc

    if not _is_inside_allowed_root(resolved, _allowed_roots()):
        raise HTTPException(status_code=400, detail="path outside allowed roots")

    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="file not found")

    _spawn_open_command(resolved)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
