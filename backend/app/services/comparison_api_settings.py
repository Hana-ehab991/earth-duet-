"""Settings for the comparison API layer (cache, request limits), read from environment variables.

Kept separate from comparison_settings.py (Earth Engine access, Phase 2) and config.py (existing app) so neither
is modified. No credentials are read here. The cache path comes only from the environment, never from a request.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

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


def _bool_env(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    return default if v is None else v.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ComparisonApiSettings:
    #: SQLite cache file. Separate from the curated JSON datasets under data/processed and data/demo.
    cache_path: Path
    #: Days a cached region result is reused. 0 disables the cache entirely (nothing is read or written).
    cache_ttl_days: float = 30.0
    #: Max seconds one POST /api/compare-locations may take overall (both locations together).
    request_deadline_s: float = 120.0
    #: Max comparison requests per client per window. 0 disables rate limiting. PROCESS-LOCAL (see docs).
    rate_limit_requests: int = 20
    rate_limit_window_s: float = 60.0
    #: Take the client address from the right-most X-Forwarded-For entry. Enable ONLY behind a trusted proxy.
    trust_forwarded_for: bool = False
    #: Largest accepted request body.
    max_request_bytes: int = 8192


def get_comparison_api_settings(data_dir: Path) -> ComparisonApiSettings:
    override = (os.environ.get("EARTH_DUET_COMPARISON_CACHE_PATH") or "").strip()
    return ComparisonApiSettings(
        cache_path=Path(override) if override else Path(data_dir) / "cache" / "comparison.sqlite",
        cache_ttl_days=_float_env("EARTH_DUET_COMPARISON_CACHE_TTL_DAYS", 30.0, 0.0, 3650.0),
        request_deadline_s=_float_env("EARTH_DUET_COMPARISON_DEADLINE_S", 120.0, 10.0, 600.0),
        rate_limit_requests=int(_float_env("EARTH_DUET_COMPARISON_RATE_LIMIT", 20, 0, 10000)),
        rate_limit_window_s=_float_env("EARTH_DUET_COMPARISON_RATE_WINDOW_S", 60.0, 1.0, 3600.0),
        trust_forwarded_for=_bool_env("EARTH_DUET_TRUST_FORWARDED_FOR", False),
        max_request_bytes=int(_float_env("EARTH_DUET_COMPARISON_MAX_BODY_BYTES", 8192, 1024, 65536)),
    )
