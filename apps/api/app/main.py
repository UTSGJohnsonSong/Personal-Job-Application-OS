from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import applications, dashboard, health, jobs
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

configure_logging()
log = get_logger("api")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("starting job-os api env=%s sqlite=%s", settings.app_env, settings.is_sqlite)
    yield
    log.info("shutting down job-os api")


app = FastAPI(
    title="Personal Job Application OS",
    version="0.1.0",
    description="First-party job discovery, explainable eligibility/ranking, "
    "assisted preparation with per-application human confirmation.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "internal error"})


app.include_router(health.router)
app.include_router(dashboard.router)
app.include_router(jobs.router)
app.include_router(applications.router)


@app.get("/")
async def root() -> dict:
    return {"name": "Personal Job Application OS", "version": "0.1.0", "docs": "/docs"}
