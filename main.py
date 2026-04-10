import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from api.middleware import setup_middleware
from api.routers import (
    assets,
    exports,
    material_packages,
    outlines,
    projects,
    references,
    render,
    sites,
    slides,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

app = FastAPI(
    title="PPT Agent API",
    version="0.1.0",
    description="AI-powered PPT generation agent for architectural presentations",
)

setup_middleware(app)

app.include_router(projects.router, prefix="/projects", tags=["projects"])
app.include_router(sites.router, prefix="/projects", tags=["sites"])
app.include_router(references.router, prefix="/projects", tags=["references"])
app.include_router(assets.router, prefix="/projects", tags=["assets"])
app.include_router(material_packages.router, prefix="/projects", tags=["material-packages"])
app.include_router(outlines.router, prefix="/projects", tags=["outlines"])
app.include_router(slides.router, prefix="/projects", tags=["slides"])
app.include_router(render.router, prefix="/projects", tags=["render"])
app.include_router(exports.router, prefix="/projects", tags=["exports"])


@app.get("/health")
def health_check():
    return {"status": "ok", "version": "0.1.0"}


_slides_dir = Path("tmp/e2e_output/slides")
_slides_dir.mkdir(parents=True, exist_ok=True)
app.mount("/slides-output", StaticFiles(directory=str(_slides_dir)), name="slides-output")

_export_dir = Path("tmp/e2e_output/export")
_export_dir.mkdir(parents=True, exist_ok=True)
app.mount("/export-output", StaticFiles(directory=str(_export_dir)), name="export-output")

app.mount("/app", StaticFiles(directory="frontend", html=True), name="frontend")
