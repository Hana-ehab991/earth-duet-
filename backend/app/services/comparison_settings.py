"""Settings for the location-comparison feature, read from environment variables.

Kept separate from app/config.py so the existing configuration is untouched. Importing app.config first
makes sure backend/.env has been loaded (real environment variables always win).
No credentials are ever read, stored or logged here: Earth Engine access uses Application Default
Credentials / an attached service identity (see docs/EARTH_ENGINE_COMPARISON.md).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from .. import config as _config  # noqa: F401  (side effect: loads backend/.env)


def _float_env(name: str, default: float, lo: float, hi: float) -> float:
    raw = os.environ.get(name)
    try:
        v = float(raw) if raw is not None else default
    except ValueError:
        return default
    if v != v:  # NaN
        return default
    return min(hi, max(lo, v))


@dataclass(frozen=True)
class ComparisonSettings:
    #: Google Cloud project registered for Earth Engine (EE_PROJECT, falling back to GOOGLE_CLOUD_PROJECT).
    ee_project: Optional[str] = None
    #: Max seconds to wait for one Earth Engine computation before answering with a timeout error.
    ee_timeout_s: float = 60.0
    #: Max Earth Engine computations in flight at once (a timed-out computation keeps its slot until it ends).
    ee_max_concurrent: int = 4
    #: Max seconds a request waits for a free slot before being rejected as busy.
    ee_queue_wait_s: float = 10.0


def get_comparison_settings() -> ComparisonSettings:
    project = (os.environ.get("EE_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT") or "").strip() or None
    return ComparisonSettings(
        ee_project=project,
        ee_timeout_s=_float_env("EARTH_DUET_EE_TIMEOUT_S", 60.0, 5.0, 300.0),
        ee_max_concurrent=int(_float_env("EARTH_DUET_EE_MAX_CONCURRENT", 4, 1, 16)),
        ee_queue_wait_s=_float_env("EARTH_DUET_EE_QUEUE_WAIT_S", 10.0, 0.0, 60.0),
    )
