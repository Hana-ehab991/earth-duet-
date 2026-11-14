#!/usr/bin/env python3
"""Generate SYNTHETIC demo datasets into data/demo/. NOT NASA DATA.

Purpose: let the UI be exercised end-to-end when NASA services are unreachable.
Everything is labelled record_type='synthetic_demo', is_demo=true; model ids are DEMO-*.
The values are a seeded smooth trend plus noise and carry NO scientific meaning.
Never write into data/processed from this script.
"""
import json
import numpy as np
from _common import DATA, load_location
from app.schemas.datasets import ObservedDataset, ProjectionDataset
from app.services.builders import BASELINE_PERIOD, TARGET_YEARS, WINDOW_YEARS, _nex_bbox
from app.services.climate_processing import grid_cell_bbox, window_for_target

BANNER = "SYNTHETIC DEMONSTRATION DATA — NOT NASA MEASUREMENTS OR MODEL OUTPUT"

def main():
    loc = load_location("cairo"); g = loc["analysis_geometry"]; lat, lon = g["latitude"], g["longitude"]
    rng = np.random.default_rng(20261112)
    (DATA / "demo").mkdir(exist_ok=True)
    years = list(range(1981, 2026))
    vals = {y: 21.5 + 0.03 * (y - 1981) + rng.normal(0, 0.3) for y in years}
    recs = [{"year": y, "value": round(vals[y], 3), "complete": True, "n_months": 12, "reason": None} for y in years]
    base = np.mean([vals[y] for y in range(*BASELINE_PERIOD)] + [vals[BASELINE_PERIOD[1]]])
    obs = ObservedDataset.model_validate({
        "dataset_id": "synthetic_demo_observed", "location_id": "cairo", "variable_id": "air_temperature",
        "record_type": "synthetic_demo", "is_demo": True, "unit": "°C",
        "source": {"name": BANNER, "url": "about:blank", "product": "synthetic generator scripts/generate_demo_data.py", "parameter": "synthetic",
                   "citation_note": "Not a scientific dataset."},
        "geometry": {"type": "point", "latitude": lat, "longitude": lon,
                     "support_bbox": grid_cell_bbox(lat, lon, 0.5, 0.625, -90.0, -180.0), "spatial_support": "Synthetic; no real spatial support."},
        "processing": {"method": "Seeded linear trend + Gaussian noise (seed 20261112). Illustrative only."},
        "baseline": {"period": list(BASELINE_PERIOD), "mean": round(float(base), 3), "description": "Synthetic baseline."},
        "coverage": {"first_year": 1981, "last_complete_year": 2025, "temporal_resolution": "annual (synthetic)"},
        "records": recs})
    (DATA / "demo" / "cairo__air_temperature__observed.json").write_text(obs.model_dump_json(indent=1))

    models = [{"id": f"DEMO-MODEL-{c}", "variant": None, "note": "synthetic"} for c in "ABC"]
    offs = {"A": -0.3, "B": 0.0, "C": 0.35}
    inc = {"ssp245": {2030: 0.9, 2050: 1.6, 2075: 2.1, 2100: 2.4}, "ssp585": {2030: 1.0, 2050: 2.2, 2075: 3.6, 2100: 4.8}}
    records, ens = [], []
    for scn in ("ssp245", "ssp585"):
        for t in TARGET_YEARS:
            vs, an = [], []
            for m in models:
                k = m["id"][-1]; b = round(21.9 + offs[k] * 0.4, 4)
                a = round(inc[scn][t] * (1 + offs[k] * 0.5), 4); v = round(b + a, 4)
                records.append({"scenario": scn, "target_year": t, "model": m["id"], "value": v, "baseline": b, "anomaly": round(v - b, 4)})
                vs.append(v); an.append(round(v - b, 4))
            ens.append({"scenario": scn, "target_year": t, "n_models": 3, "mean": round(float(np.mean(vs)), 4), "min": min(vs), "max": max(vs),
                        "std": round(float(np.std(vs, ddof=1)), 4), "anomaly_mean": round(float(np.mean(an)), 4), "anomaly_min": min(an), "anomaly_max": max(an)})
    wins = [dict(zip(("start_year", "end_year", "clipped"), window_for_target(t, WINDOW_YEARS)), target_year=t) for t in TARGET_YEARS]
    proj = ProjectionDataset.model_validate({
        "dataset_id": "synthetic_demo_projection", "location_id": "cairo", "variable_id": "air_temperature",
        "record_type": "synthetic_demo", "is_demo": True, "unit": "°C",
        "source": {"name": BANNER, "url": "about:blank", "product": "synthetic generator", "parameter": "synthetic"},
        "geometry": {"type": "point", "latitude": lat, "longitude": lon, "support_bbox": _nex_bbox(lat, lon), "spatial_support": "Synthetic."},
        "processing": {"method": "Hand-set illustrative increments; NOT climate model output."},
        "baseline": {"period": list(BASELINE_PERIOD), "mean": 21.9, "description": "Synthetic."},
        "models": models, "scenarios": ["ssp245", "ssp585"], "windows": wins, "records": records, "ensemble": ens,
        "uncertainty_note": "Synthetic spread; meaningless scientifically."})
    (DATA / "demo" / "cairo__air_temperature__projection.json").write_text(proj.model_dump_json(indent=1))
    print("wrote synthetic demo datasets to data/demo/")

if __name__ == "__main__":
    main()
