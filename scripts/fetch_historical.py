#!/usr/bin/env python3
"""Fetch NASA POWER monthly T2M for a point and write the validated annual dataset.

Output (real data only):
  data/raw/power_<loc>_T2M_monthly.json                    (verbatim API response)
  data/processed/<loc>__air_temperature__observed.json     (validated annual dataset)

Requires outbound HTTPS to power.larc.nasa.gov. No API key needed.
Usage: python scripts/fetch_historical.py --location cairo [--start 1981 --end 2025]
"""
import argparse, datetime as dt, json, sys
import requests
from _common import DATA, PROCESSED, RAW, load_location, write_text_utf8
from app.services.builders import build_observed_dataset  # noqa: E402

API = "https://power.larc.nasa.gov/api/temporal/monthly/point"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--location", default="cairo", help="location id, comma-separated list, or 'all' (every primary_mvp location)")
    ap.add_argument("--start", type=int, default=1981)
    ap.add_argument("--end", type=int, default=dt.date.today().year)
    ap.add_argument("--community", default="AG", help="POWER community (AG, RE, SB)")
    ap.add_argument("--from-raw", action="store_true",
                    help="Rebuild the processed dataset from the already-downloaded data/raw file (no network).")
    a = ap.parse_args()
    ids = all_ids() if a.location == "all" else [x.strip() for x in a.location.split(",") if x.strip()]
    failed = []
    for i in ids:
        try:
            run(a, i)
        except SystemExit as e:  # keep going so one failure does not hide the others
            print(f"[{i}] {e}"); failed.append(i)
    if failed:
        sys.exit(f"FAILED for: {failed}")


def all_ids():
    import json as _j
    return [l["id"] for l in _j.loads((DATA / "metadata" / "locations.json").read_text(encoding="utf-8"))["locations"] if l["status"] == "primary_mvp"]


def run(a, location_id):
    loc = load_location(location_id)
    a.location = location_id
    if loc["analysis_geometry"]["type"] != "point":
        sys.exit(f"{a.location}: no point analysis geometry configured; refusing to guess a region.")
    lat, lon = loc["analysis_geometry"]["latitude"], loc["analysis_geometry"]["longitude"]
    raw = RAW / f"power_{a.location}_T2M_monthly.json"
    out = PROCESSED / f"{a.location}__{loc['primary_variable']}__observed.json"
    if a.from_raw:
        if not raw.is_file():
            sys.exit(f"{raw} does not exist; run without --from-raw to download it.")
        payload = json.loads(raw.read_text(encoding="utf-8"))
        request_url = f"{API} (rebuilt from saved response {raw.name})"
    else:
        params = {"parameters": "T2M", "community": a.community, "longitude": lon, "latitude": lat,
                  "start": a.start, "end": a.end, "format": "JSON"}
        try:
            r = requests.get(API, params=params, timeout=120)
            r.raise_for_status()
        except requests.RequestException as e:
            sys.exit(f"FAILED to reach NASA POWER: {e}\nNo data was written. (Not substituting any other values.)")
        payload = r.json()
        request_url = r.url
        write_text_utf8(raw, json.dumps(payload))
    try:
        ds = build_observed_dataset(payload, location_id=a.location, variable_id=loc["primary_variable"],
                                    lat=lat, lon=lon, request_url=request_url)
    except (KeyError, ValueError) as e:
        sys.exit(f"FAILED to build the observed dataset from the POWER response: {type(e).__name__}: {e}\n"
                 "Nothing was written to data/processed.")
    write_text_utf8(out, ds.model_dump_json(indent=1))
    print(f"wrote {out}\n      years={ds.coverage['first_year']}-{ds.coverage['last_complete_year']}  baseline={ds.baseline.mean} degC")

if __name__ == "__main__":
    main()
