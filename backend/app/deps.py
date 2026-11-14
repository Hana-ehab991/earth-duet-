from __future__ import annotations

from fastapi import Request

from .config import Settings, get_settings
from .services.dataset_store import DatasetStore


def get_store(request: Request) -> DatasetStore:
    return request.app.state.store
