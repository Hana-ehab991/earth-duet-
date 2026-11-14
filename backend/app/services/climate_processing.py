"""Pure, source-agnostic climate processing helpers.

Used by the data scripts AND by tests. Nothing here talks to the network.
"""
from __future__ import annotations

import math
from typing import Iterable, Mapping, Optional, Sequence

import numpy as np

KELVIN_OFFSET = 273.15
MISSING_POWER = -999.0


def kelvin_to_celsius(k):
    """Explicit K → °C conversion (works on floats, numpy arrays, xarray)."""
    return k - KELVIN_OFFSET


def annual_mean_from_monthly(
    monthly: Mapping[int, Optional[float]], month_days: Optional[Mapping[int, int]] = None
) -> tuple[Optional[float], int]:
    """Mean of the 12 monthly means. Returns (value, n_valid_months).

    A year is only given a value if ALL 12 months are valid; partial years return
    (None, n_valid) rather than a biased partial-year mean (seasonal-cycle bias).
    If month_days is supplied the mean is day-weighted, otherwise it is the plain
    mean of monthly means (what NASA POWER's own annual value approximates).
    """
    vals = {m: v for m, v in monthly.items() if v is not None and not math.isnan(v) and v != MISSING_POWER}
    n = len(vals)
    if n < 12:
        return None, n
    if month_days:
        w = np.array([month_days[m] for m in sorted(vals)], float)
        x = np.array([vals[m] for m in sorted(vals)], float)
        return float(np.sum(w * x) / np.sum(w)), n
    return float(np.mean(list(vals.values()))), n


def days_in_month(year: int, month: int) -> int:
    import calendar

    return calendar.monthrange(year, month)[1]


def annual_mean_from_daily(daily_values: Sequence[float]) -> float:
    """Annual mean of daily values (equal weight per day, so leap years are handled by length)."""
    a = np.asarray(daily_values, float)
    if a.size < 365:
        raise ValueError(f"Expected a full year of daily data, got {a.size} days")
    return float(np.nanmean(a))


def window_for_target(target_year: int, window_years: int = 20, data_end: int = 2100, data_start: int = 2015):
    """Window of `window_years` centred on target_year, clipped to [data_start, data_end].

    For an even window length the window is [t - w/2, t + w/2 - 1] (e.g. 2030 → 2020–2039).
    Returns (start, end, clipped).
    """
    if window_years % 2 == 0:
        start, end = target_year - window_years // 2, target_year + window_years // 2 - 1
    else:
        h = window_years // 2
        start, end = target_year - h, target_year + h
    clipped = False
    if end > data_end:
        start, end, clipped = start, data_end, True
    if start < data_start:
        start, clipped = data_start, True
    return start, end, clipped


def window_mean(annual: Mapping[int, float], start: int, end: int) -> float:
    """Mean of annual means across [start, end]; refuses to average an incomplete window."""
    missing = [y for y in range(start, end + 1) if y not in annual or annual[y] is None]
    if missing:
        raise ValueError(f"Window {start}-{end} is missing years: {missing}")
    return float(np.mean([annual[y] for y in range(start, end + 1)]))


def ensemble_stats(values: Iterable[float]) -> dict:
    a = np.asarray(list(values), float)
    if a.size == 0:
        raise ValueError("no values")
    return {
        "n_models": int(a.size),
        "mean": float(a.mean()),
        "min": float(a.min()),
        "max": float(a.max()),
        "std": float(a.std(ddof=1)) if a.size > 1 else 0.0,
    }


def grid_cell_bbox(lat: float, lon: float, dlat: float, dlon: float, lat0: float, lon0: float):
    """Bounding box [W,S,E,N] of the regular-grid cell containing (lat, lon).

    lat0/lon0 are the CENTRES of a reference cell. Used to draw nominal spatial support.
    """
    ilat = round((lat - lat0) / dlat)
    ilon = round((lon - lon0) / dlon)
    clat = lat0 + ilat * dlat
    clon = lon0 + ilon * dlon
    return [clon - dlon / 2, clat - dlat / 2, clon + dlon / 2, clat + dlat / 2]
