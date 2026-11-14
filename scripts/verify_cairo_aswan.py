#!/usr/bin/env python3
"""Print a side-by-side check of the REAL processed Cairo and Aswan temperature datasets (no network, no fake data).
If the backend is running it also checks what the API serves."""
import json, sys, urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"


def read(path: Path):
    raw = path.read_bytes()
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except UnicodeDecodeError:
        return json.loads(raw.decode("cp1252"))


def main() -> int:
    ok, rows = True, {}
    for loc in ("cairo", "aswan"):
        p = DATA / "processed" / f"{loc}__air_temperature__observed.json"
        if not p.is_file():
            print(f"[MISSING] {p}  -> run fetch-nasa-data.bat"); ok = False; continue
        d = read(p)
        if d.get("is_demo"):
            print(f"[BAD] {p.name} is flagged synthetic"); ok = False; continue
        rows[loc] = {r["year"]: r["value"] for r in d["records"] if r["complete"]}
        g = d["geometry"]
        print(f"{loc:6} lat {g['latitude']:.4f} lon {g['longitude']:.4f}  years {min(rows[loc])}-{max(rows[loc])}  "
              f"({len(rows[loc])} complete)  1995-2014 baseline {d['baseline']['mean']} degC  source: {d['source']['name']}")
    if len(rows) == 2:
        common = sorted(set(rows["cairo"]) & set(rows["aswan"]))
        print("\nyear   Cairo   Aswan   Aswan-Cairo")
        for y in [c for c in common if c % 5 == 0 or c == common[-1]]:
            c, a = rows["cairo"][y], rows["aswan"][y]
            print(f"{y}  {c:6.2f}  {a:6.2f}  {a - c:+6.2f}")
        if rows["cairo"] == rows["aswan"]:
            print("[BAD] the two series are identical"); ok = False
        elif all(rows["aswan"][y] > rows["cairo"][y] for y in common):
            print("\n[OK] Aswan is warmer than Cairo in every common year, as expected for a more southern desert city.")
    try:
        for loc in ("cairo", "aswan"):
            with urllib.request.urlopen(f"http://127.0.0.1:8000/api/timeseries?location={loc}&variable=air_temperature", timeout=5) as r:
                j = json.load(r)
            print(f"[API OK] {loc}: latest complete year {j['latest_complete_year']}, {len(j['available_years'])} years")
    except Exception as e:  # noqa
        print(f"[API] not checked / failing ({type(e).__name__}: {e}) - start the backend with start-earth-duet.bat"); ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
