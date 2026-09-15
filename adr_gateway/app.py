"""Compose the HTTP adapter, upstream client and storage configuration."""
from fastapi import FastAPI

from .adr_client import AdrClient
from .api import router
from .config import Settings, load_settings


def create_app(settings: Settings | None = None, *, transport=None) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(title="ADR HTTP adapter", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.adr = AdrClient(settings, transport=transport)
    app.include_router(router)
    return app
