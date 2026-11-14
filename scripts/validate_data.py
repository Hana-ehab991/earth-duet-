#!/usr/bin/env python3
"""Validate every processed (and optionally demo) dataset against the schemas + physical sanity checks."""
import argparse, sys
from _common import DATA
from app.schemas.datasets import ObservedDataset, ProjectionDataset

def check_observed(ds, errs):
    for r in ds.records:
        if r.value is not None and not (-60 <= r.value <= 60):
            errs.append(f"{ds.location_id}: implausible annual T2M {r.value} in {r.year}")
    if ds.unit != "°C":
        errs.append("unit must be °C")

def check_projection(ds, errs):
    for r in ds.records:
        if not (-60 <= r.value <= 70):
            errs.append(f"implausible projected value {r.value} ({r.model} {r.scenario} {r.target_year})")
    for e in ds.ensemble:
        vals = [r.value for r in ds.records if r.scenario == e.scenario and r.target_year == e.target_year]
        if len(vals) != e.n_models or abs(sum(vals) / len(vals) - e.mean) > 1e-3:
            errs.append(f"ensemble mean mismatch {e.scenario} {e.target_year}")
        if not (e.min <= e.mean <= e.max):
            errs.append(f"ensemble min/mean/max inconsistent {e.scenario} {e.target_year}")
    for w in ds.windows:
        if w.end_year > 2100:
            errs.append("window beyond 2100")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--demo", action="store_true"); a = ap.parse_args()
    d = DATA / ("demo" if a.demo else "processed")
    files = sorted(d.glob("*.json")); errs = []
    if not files:
        print(f"No datasets in {d} (nothing to validate)."); return
    for f in files:
        cls = ObservedDataset if f.name.endswith("__observed.json") else ProjectionDataset
        try:
            from app.services.dataset_store import _read_text_robust
            ds = cls.model_validate_json(_read_text_robust(f))
        except Exception as e:
            errs.append(f"{f.name}: schema error: {e}"); continue
        if a.demo != ds.is_demo:
            errs.append(f"{f.name}: is_demo={ds.is_demo} in wrong directory")
        (check_observed if cls is ObservedDataset else check_projection)(ds, errs)
        print(f"checked {f.name}")
    if errs:
        print("\n".join("ERROR: " + e for e in errs)); sys.exit(1)
    print("OK")

if __name__ == "__main__":
    main()
