from __future__ import annotations

from fastapi import FastAPI

from .db import Base, engine
from .routers import applications, captures, evidence_banks, jobs, master_resumes


def create_app() -> FastAPI:
    app = FastAPI(title="jobapply backend", version="0.1.0")

    Base.metadata.create_all(bind=engine)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(captures.router)
    app.include_router(jobs.router)
    app.include_router(master_resumes.router)
    app.include_router(evidence_banks.router)
    app.include_router(applications.router)

    return app


app = create_app()
