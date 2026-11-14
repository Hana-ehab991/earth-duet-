"""Turn raw source payloads into validated, provenance-rich datasets.

These builders are source-agnostic where possible: `build_projection_dataset` takes a
callable that returns window means, so it works with Earth Engine, S3/NetCDF, or a test double.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional

from ..schemas.datasets import ObservedDataset, ProjectionDataset
from .climate_processing import (MISSING_POWER, annual_mean_from_monthly, days_in_month, ensemble_stats,
                                 grid_cell_bbox, kelvin_to_celsius, window_for_target)

BASELINE_PERIOD = (1995, 2014)
TARGET_YEARS = (2030, 2050, 2075, 2100)
WINDOW_YEARS = 20
SCENARIOS = ("ssp245", "ssp585")

# window_mean_k(model_id, scenario, start_year, end_year) -> (mean_kelvin, n_days)
WindowMeanK = Callable[[str, str, int, int], tuple[float, int]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_observed_dataset(power_json: dict, *, location_id: str, variable_id: str, lat: float, lon: float,
                           request_url: str, retrieved_at: Optional[str] = None) -> ObservedDataset:
    """NASA POWER monthly point response → annual dataset. Only complete (12-month) years get a value."""
    t2m = power_json["properties"]["parameter"]["T2M"]
    meta = power_json.get("parameters", {}).get("T2M", {})
    unit = meta.get("units", "C")
    if unit not in ("C", "°C"):
        raise ValueError(f"Unexpected POWER T2M unit '{unit}'; refusing to relabel it as °C.")
    by_year: dict[int, dict[int, Optional[float]]] = {}
    for key, v in t2m.items():
        y, m = int(key[:4]), int(key[4:])
        if m == 13:  # POWER's own annual value; we recompute from months for transparency
            continue
        by_year.setdefault(y, {})[m] = None if v == MISSING_POWER else v
    records, vals = [], {}
    for y in sorted(by_year):
        months = by_year[y]
        md = {m: days_in_month(y, m) for m in months if months[m] is not None}
        val, n = annual_mean_from_monthly(months, md if len(md) == 12 else None)
        complete = val is not None
        records.append({"year": y, "value": None if val is None else round(val, 3), "complete": complete, "n_months": n,
                        "reason": None if complete else f"Only {n}/12 monthly values available; annual mean withheld."})
        if complete:
            vals[y] = val
    b0, b1 = BASELINE_PERIOD
    missing = [y for y in range(b0, b1 + 1) if y not in vals]
    if missing:
        raise ValueError(f"Baseline period {b0}-{b1} incomplete in source (missing {missing}).")
    base = sum(vals[y] for y in range(b0, b1 + 1)) / (b1 - b0 + 1)
    complete_years = sorted(vals)
    header = power_json.get("header", {})
    bbox = grid_cell_bbox(lat, lon, 0.5, 0.625, -90.0, -180.0)
    return ObservedDataset.model_validate({
        "dataset_id": "nasa_power_t2m_annual", "location_id": location_id, "variable_id": variable_id,
        "record_type": "reanalysis", "is_demo": False, "unit": "°C",
        "source": {"name": "NASA Prediction Of Worldwide Energy Resources (POWER)", "url": "https://power.larc.nasa.gov/",
                   "product": "POWER monthly temporal API, point endpoint", "parameter": "T2M (Temperature at 2 Metres)",
                   "citation_note": "POWER meteorological parameters are derived from reanalysis/model-assisted products "
                                    "(MERRA-2), not direct station observations. See https://power.larc.nasa.gov/docs/.",
                   "extra": {"api_version": header.get("api", {}).get("version"), "title": header.get("title"),
                             "fill_value": header.get("fill_value"), "sources": header.get("sources"),
                             "parameter_longname": meta.get("longname")}},
        "geometry": {"type": "point", "latitude": lat, "longitude": lon, "support_bbox": bbox,
                     "spatial_support": "Single point; value represents the containing POWER/MERRA-2 grid cell "
                                        "(nominally 0.5° lat × 0.625° lon, ~55 × 60 km at Cairo). Box shown is nominal support."},
        "processing": {"method": "Annual mean = day-weighted mean of the 12 monthly means of T2M. Years with any missing "
                                 "month are withheld (null), never partially averaged.",
                       "missing_value_handling": f"POWER fill value {MISSING_POWER} treated as missing.",
                       "retrieved_at": retrieved_at or _now(), "request": request_url},
        "baseline": {"period": list(BASELINE_PERIOD), "mean": round(base, 3),
                     "description": f"Mean of annual T2M over {b0}–{b1} from the same POWER product."},
        "coverage": {"first_year": complete_years[0], "last_complete_year": complete_years[-1],
                     "temporal_resolution": "annual (from monthly)"},
        "records": records,
    })


def build_projection_dataset(window_mean_k: WindowMeanK, *, location_id: str, variable_id: str, lat: float, lon: float,
                             models: list[dict], backend: str, retrieved_at: Optional[str] = None,
                             request_note: str = "") -> ProjectionDataset:
    """Assemble NEX-GDDP-CMIP6 `tas` window means, baseline-referenced anomalies and ensemble spread."""
    windows = []
    for t in TARGET_YEARS:
        s, e, clipped = window_for_target(t, WINDOW_YEARS, data_end=2100, data_start=2015)
        windows.append({"target_year": t, "start_year": s, "end_year": e, "clipped": clipped})
    b0, b1 = BASELINE_PERIOD
    baselines = {}
    for m in models:
        k, n = window_mean_k(m["id"], "historical", b0, b1)
        if n <= 0:
            raise ValueError(f"No daily data for {m['id']} historical baseline")
        baselines[m["id"]] = float(kelvin_to_celsius(k))
    records, ensemble = [], []
    for scn in SCENARIOS:
        for w in windows:
            vals, anoms = [], []
            for m in models:
                k, n = window_mean_k(m["id"], scn, w["start_year"], w["end_year"])
                if n <= 0:
                    raise ValueError(f"No daily data for {m['id']} {scn} {w['start_year']}-{w['end_year']}")
                v = float(kelvin_to_celsius(k))
                a = v - baselines[m["id"]]
                records.append({"scenario": scn, "target_year": w["target_year"], "model": m["id"],
                                "value": round(v, 4), "baseline": round(baselines[m["id"]], 4), "anomaly": round(round(v, 4) - round(baselines[m["id"]], 4), 4)})
                vals.append(round(v, 4)); anoms.append(round(v, 4) - round(baselines[m["id"]], 4))
            sv, sa = ensemble_stats(vals), ensemble_stats(anoms)
            ensemble.append({"scenario": scn, "target_year": w["target_year"], "n_models": sv["n_models"],
                             "mean": round(sv["mean"], 4), "min": round(sv["min"], 4), "max": round(sv["max"], 4),
                             "std": round(sv["std"], 4), "anomaly_mean": round(sa["mean"], 4),
                             "anomaly_min": round(sa["min"], 4), "anomaly_max": round(sa["max"], 4)})
    bbox = _nex_bbox(lat, lon)
    base_mean = sum(baselines.values()) / len(baselines)
    return ProjectionDataset.model_validate({
        "dataset_id": "nasa_nex_gddp_cmip6_tas_windows", "location_id": location_id, "variable_id": variable_id,
        "record_type": "projection", "is_demo": False, "unit": "°C",
        "source": {"name": "NASA Earth Exchange Global Daily Downscaled Projections (NEX-GDDP-CMIP6)",
                   "url": "https://developers.google.com/earth-engine/datasets/catalog/NASA_GDDP-CMIP6",
                   "product": "NEX-GDDP-CMIP6 daily, 0.25° bias-corrected, statistically downscaled CMIP6", "parameter": "tas",
                   "citation_note": "Cite per NASA NCCS NEX-GDDP-CMIP6 guidance (Thrasher et al.). Model output, not observations.",
                   "extra": {"backend": backend}},
        "geometry": {"type": "point", "latitude": lat, "longitude": lon, "support_bbox": bbox,
                     "spatial_support": "Single point; value is the containing 0.25° (~27 km) grid cell. "
                                        "Not a building- or neighbourhood-scale prediction."},
        "processing": {"method": f"Daily tas (K) averaged over a {WINDOW_YEARS}-year window centred on the target year "
                                 "(mean of all daily values), then converted K→°C. The 2100 window (2090–2109) is clipped to the data end, giving 2090–2100 (11 years), and is flagged. "
                                 "Anomaly = window mean − same model's historical 1995–2014 mean.",
                       "retrieved_at": retrieved_at or _now(), "request": request_note,
                       "extra": {"window_years": WINDOW_YEARS, "kelvin_to_celsius": "T[°C] = T[K] − 273.15", "backend": backend}},
        "baseline": {"period": list(BASELINE_PERIOD), "mean": round(base_mean, 4),
                     "description": "Ensemble mean of each model's 1995–2014 historical-simulation tas window mean (NEX-GDDP-CMIP6 'historical')."},
        "models": models, "scenarios": list(SCENARIOS), "windows": windows, "records": records, "ensemble": ensemble,
        "uncertainty_note": "min/max/std are inter-model spread across the listed models only; they are not a confidence "
                            "interval and do not include scenario uncertainty or internal variability beyond one run per model.",
    })


def _nex_bbox(lat: float, lon: float) -> list[float]:
    return grid_cell_bbox(lat, lon % 360.0, 0.25, 0.25, -89.875, 0.125)
