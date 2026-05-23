from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import Base, engine
from .routers import (
    applications,
    captures,
    evidence_banks,
    files,
    jobs,
    master_resumes,
    resume_versions,
    runs,
)


def create_app() -> FastAPI:
    app = FastAPI(title="jobapply backend", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    Base.metadata.create_all(bind=engine)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(captures.router)
    app.include_router(jobs.router)
    app.include_router(master_resumes.router)
    app.include_router(evidence_banks.router)
    app.include_router(applications.router)
    app.include_router(runs.router)
    app.include_router(resume_versions.router)
    app.include_router(files.router)

    return app


app = create_app()
