#!/usr/bin/env python3
"""Export processed datasets to CSV (with provenance header comments) for use outside the app."""
import argparse, csv
from _common import DATA
from app.schemas.datasets import ObservedDataset, ProjectionDataset

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--location", default="cairo"); ap.add_argument("--demo", action="store_true")
    a = ap.parse_args(); d = DATA / ("demo" if a.demo else "processed")
    var = "air_temperature"
    p = d / f"{a.location}__{var}__observed.json"
    if p.exists():
        ds = ObservedDataset.model_validate_json(p.read_text())
        out = DATA / "processed" / f"{a.location}_{var}_observed.csv" if not a.demo else d / f"{a.location}_{var}_observed.csv"
        with open(out, "w", newline="") as f:
            f.write(f"# {ds.source.name} | {ds.source.parameter} | unit={ds.unit} | type={ds.record_type} | {ds.processing.method}\n")
            w = csv.writer(f); w.writerow(["year", f"value_{ds.unit}", "complete", "n_months"])
            for r in ds.records: w.writerow([r.year, r.value, r.complete, r.n_months])
        print("wrote", out)
    p = d / f"{a.location}__{var}__projection.json"
    if p.exists():
        ds = ProjectionDataset.model_validate_json(p.read_text())
        out = (d / f"{a.location}_{var}_projection.csv")
        with open(out, "w", newline="") as f:
            f.write(f"# {ds.source.name} | tas | unit={ds.unit} | type={ds.record_type} | {ds.processing.method}\n")
            w = csv.writer(f); w.writerow(["scenario", "target_year", "model", "value", "baseline", "anomaly"])
            for r in ds.records: w.writerow([r.scenario, r.target_year, r.model, r.value, r.baseline, r.anomaly])
        print("wrote", out)

if __name__ == "__main__":
    main()
