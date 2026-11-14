#!/usr/bin/env python3
"""Extract NEX-GDDP-CMIP6 `tas` window means for a point and write the projection dataset.

Backends (choose with --backend, default auto):
  s3   : anonymous read of NASA's public NEX-GDDP-CMIP6 bucket on the AWS Open Data program
         (s3://nex-gddp-cmip6, region us-west-2; https://registry.opendata.aws/nex-gddp-cmip6/) via s3fs + xarray.
         No credentials needed. Per-model-year results are cached in data/raw/nex_gddp/ so a run can be resumed.
         NOTE: each yearly file is global (~hundreds of MB); extracting a point can take a long time and a lot of
         bandwidth. Use --models to try a smaller subset first, or the ee backend.
  ee   : Google Earth Engine collection NASA/GDDP-CMIP6 (needs `earthengine authenticate` and EE_PROJECT, which is read
         from the environment or backend/.env). Much faster than s3 for a single point.
  auto : s3 if the bucket passes a pre-flight check, otherwise ee if EE_PROJECT is set, otherwise stop with a clear message.

Both backends yield (mean_K, n_days) for a window = mean of ALL daily values in the window; the shared builder then
converts K->degC, computes baseline anomalies (historical 1995-2014 per model) and ensemble spread.

Nothing is ever guessed: if a source is unreachable, a model/file is missing or a request fails, NO projection file is
written and the app labels projections "unavailable".

Usage:
  python scripts/fetch_projections.py --check                 # only test that the data source is reachable
  python scripts/fetch_projections.py --location cairo [--backend auto|s3|ee] [--models ACCESS-CM2,CanESM5]
"""
import argparse, json, os, sys, time
from _common import NEX_CACHE, PROCESSED, load_location, write_text_utf8
from app.services.builders import build_projection_dataset

MODELS = [
    {"id": "ACCESS-CM2", "variant": "r1i1p1f1", "grid": "gn"},
    {"id": "CanESM5", "variant": "r1i1p1f1", "grid": "gn"},
    {"id": "MPI-ESM1-2-HR", "variant": "r1i1p1f1", "grid": "gn"},
    {"id": "MRI-ESM2-0", "variant": "r1i1p1f1", "grid": "gn"},
    {"id": "NorESM2-MM", "variant": "r1i1p1f1", "grid": "gn"},
]
# The AWS Open Data bucket is named "nex-gddp-cmip6" (the earlier "nasa-nex-gddp-cmip6" does not exist, which caused
# "FileNotFoundError: The specified bucket does not exist"). Override with EARTH_DUET_NEX_BUCKET if NASA ever moves it.
BUCKET = os.environ.get("EARTH_DUET_NEX_BUCKET", "nex-gddp-cmip6")
REGION = "us-west-2"
PREFIX = "NEX-GDDP-CMIP6"
CACHE = NEX_CACHE


class SourceUnavailable(Exception):
    pass


def _fs():
    try:
        import s3fs
    except ImportError as e:
        raise SourceUnavailable("s3fs/xarray are not installed. Run fetch-nasa-data.bat (it installs "
                                "backend\\requirements-data.txt) or: pip install -r backend/requirements-data.txt") from e
    return s3fs.S3FileSystem(anon=True, client_kwargs={"region_name": REGION})


def s3_preflight(models=MODELS) -> None:
    """Cheap listing calls proving the bucket, the dataset root and every model/scenario folder exist."""
    fs = _fs()
    try:
        roots = fs.ls(f"{BUCKET}/{PREFIX}", detail=False)
    except FileNotFoundError as e:
        raise SourceUnavailable(f"s3://{BUCKET}/{PREFIX}/ was not found ({e}). The bucket name or layout may have "
                                "changed; check https://registry.opendata.aws/nex-gddp-cmip6/ and set "
                                "EARTH_DUET_NEX_BUCKET.") from e
    except Exception as e:  # network, DNS, proxy, permissions
        raise SourceUnavailable(f"Could not list s3://{BUCKET}/{PREFIX}/ ({type(e).__name__}: {e}). "
                                "Check your internet connection / firewall.") from e
    have = {r.rstrip("/").split("/")[-1] for r in roots}
    missing = [m["id"] for m in models if m["id"] not in have]
    if missing:
        raise SourceUnavailable(f"Models not present in s3://{BUCKET}/{PREFIX}/: {missing}. "
                                f"Available models include: {sorted(have)[:40]}")
    for m in models:
        for scn in ("historical", "ssp245", "ssp585"):
            try:
                fs.ls(f"{BUCKET}/{PREFIX}/{m['id']}/{scn}", detail=False)
            except Exception as e:
                raise SourceUnavailable(f"{m['id']}/{scn} not found in the bucket ({type(e).__name__}: {e})") from e


def s3_backend(lat, lon, models):
    import xarray as xr
    fs = _fs()
    by_id = {m["id"]: m for m in models}

    def find_file(m, scn, year):
        base = f"{BUCKET}/{PREFIX}/{m['id']}/{scn}"
        # Preferred: the declared variant/grid. Fallback: any variant/grid (some models use r1i1p1f2, gr, gr1, ...).
        for pat in (f"{base}/{m['variant']}/tas/tas_day_{m['id']}_{scn}_{m['variant']}_{m['grid']}_{year}*.nc",
                    f"{base}/*/tas/tas_day_{m['id']}_{scn}_*_{year}*.nc"):
            files = sorted(fs.glob(pat))
            if files:
                return files[-1]  # newest version suffix (e.g. _v1.1 / _v2.0) sorts last
        raise FileNotFoundError(f"No NEX-GDDP-CMIP6 tas file for {m['id']} {scn} {year} under s3://{base}/")

    def year_mean(model, scn, year):
        cf = CACHE / f"{model}_{scn}_{year}_{lat:.4f}_{lon:.4f}.json"
        if cf.exists():
            d = json.loads(cf.read_text(encoding="utf-8")); return d["mean_k"], d["n_days"]
        path = find_file(by_id[model], scn, year)
        t0 = time.time()
        print(f"    reading {model} {scn} {year} ...", end="", flush=True)
        with fs.open(path, "rb", block_size=8 * 1024 * 1024) as f, xr.open_dataset(f, engine="h5netcdf") as ds:
            vals = ds["tas"].sel(lat=lat, lon=lon % 360.0, method="nearest").values.astype("float64")
        if vals.size < 365 or not (vals == vals).all():
            raise ValueError(f"{path}: expected a full year of valid daily values, got {vals.size} (NaNs present: {not (vals == vals).all()})")
        d = {"mean_k": float(vals.mean()), "n_days": int(vals.size), "file": path}
        write_text_utf8(cf, json.dumps(d))
        print(f" done ({time.time() - t0:.0f}s)")
        return d["mean_k"], d["n_days"]

    def window(model, scn, start, end):
        tot = n = 0.0
        for y in range(start, end + 1):
            mk, nd = year_mean(model, scn, y); tot += mk * nd; n += nd
        return tot / n, int(n)
    return window


def ee_backend(lat, lon, models):
    try:
        import ee
    except ImportError as e:
        raise SourceUnavailable("earthengine-api is not installed (pip install -r backend/requirements-data.txt).") from e
    proj = os.environ.get("EE_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not proj:
        raise SourceUnavailable("EE_PROJECT is not set (add EE_PROJECT=your-project to backend/.env).")
    try:
        ee.Initialize(project=proj)
    except Exception as e:
        raise SourceUnavailable(f"Earth Engine could not be initialised ({type(e).__name__}: {e}). "
                                "Run `earthengine authenticate` and check EE_PROJECT.") from e
    pt = ee.Geometry.Point([lon, lat])
    coll = ee.ImageCollection("NASA/GDDP-CMIP6")
    CACHE.mkdir(parents=True, exist_ok=True)

    def window(model, scn, start, end):
        cf = CACHE / f"ee_{model}_{scn}_{start}-{end}_{lat:.4f}_{lon:.4f}.json"
        if cf.exists():
            d = json.loads(cf.read_text(encoding="utf-8")); return d["mean_k"], d["n_days"]
        c = (coll.filter(ee.Filter.eq("model", model)).filter(ee.Filter.eq("scenario", scn))
             .filterDate(f"{start}-01-01", f"{end + 1}-01-01").select("tas"))
        last = None
        for attempt in range(3):
            try:
                print(f"    EE {model} {scn} {start}-{end} ...", end="", flush=True)
                n = c.size().getInfo()
                r = c.mean().reduceRegion(ee.Reducer.first(), pt, 27830).get("tas").getInfo()
                if r is None or n == 0:
                    raise ValueError(f"No data for {model} {scn} {start}-{end}")
                print(" done")
                write_text_utf8(cf, json.dumps({"mean_k": float(r), "n_days": int(n)}))
                return float(r), int(n)
            except ValueError:
                raise
            except Exception as e:  # transient EE errors
                last = e; print(f" retry ({type(e).__name__})"); time.sleep(3 * (attempt + 1))
        raise RuntimeError(f"Earth Engine request failed after 3 attempts: {last}")
    return window


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--location", default="cairo")
    ap.add_argument("--backend", choices=["auto", "s3", "ee"], default="auto")
    ap.add_argument("--models", help="comma-separated subset of: " + ",".join(m["id"] for m in MODELS))
    ap.add_argument("--check", action="store_true", help="only test that the data source is reachable; write nothing")
    a = ap.parse_args()
    models = MODELS
    if a.models:
        want = [x.strip() for x in a.models.split(",") if x.strip()]
        bad = [w for w in want if w not in {m["id"] for m in MODELS}]
        if bad:
            sys.exit(f"Unknown model(s) {bad}. Choose from {[m['id'] for m in MODELS]}")
        models = [m for m in MODELS if m["id"] in want]

    loc = load_location(a.location)
    g = loc["analysis_geometry"]
    if g["type"] != "point":
        sys.exit("No point geometry configured; refusing to guess.")
    lat, lon = g["latitude"], g["longitude"]

    backend, notes = a.backend, []
    if backend in ("auto", "s3"):
        try:
            s3_preflight(models)
            backend = "s3"
            print(f"[ok] NEX-GDDP-CMIP6 reachable at s3://{BUCKET}/{PREFIX}/")
        except SourceUnavailable as e:
            if a.backend == "s3":
                sys.exit(f"PROJECTIONS UNAVAILABLE: {e}\nNo dataset was written. (Not substituting any values.)")
            notes.append(f"S3 not usable: {e}")
            if os.environ.get("EE_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT"):
                backend = "ee"
            else:
                sys.exit("PROJECTIONS UNAVAILABLE.\n  - " + "\n  - ".join(notes) +
                         "\n  - Earth Engine fallback not available: EE_PROJECT is not set.\n"
                         "No dataset was written. (Not substituting any values.) "
                         "Time Travel will show observed history and mark projections unavailable.")
    if a.check:
        print(f"[ok] backend '{backend}' looks usable. Nothing written (--check)."); return

    if backend == "s3":
        print(f"NOTE: reading yearly global NetCDF files for {len(models)} models; this can take a long time. "
              f"Progress is cached in {CACHE} - you can stop (Ctrl+C) and re-run to resume.")
    try:
        fn = s3_backend(lat, lon, models) if backend == "s3" else ee_backend(lat, lon, models)
        ds = build_projection_dataset(fn, location_id=a.location, variable_id=loc["primary_variable"], lat=lat, lon=lon,
                                      models=[{"id": m["id"], "variant": m["variant"]} for m in models],
                                      backend=backend, request_note=f"backend={backend}; bucket={BUCKET if backend == 's3' else 'NASA/GDDP-CMIP6 (Earth Engine)'}; models={[m['id'] for m in models]}")
    except KeyboardInterrupt:
        sys.exit("\nInterrupted. Progress is cached; no dataset was written.")
    except Exception as e:  # noqa
        sys.exit(f"PROJECTIONS UNAVAILABLE: {type(e).__name__}: {e}\nNo dataset was written. (Not substituting any values.)")
    out = PROCESSED / f"{a.location}__{loc['primary_variable']}__projection.json"
    write_text_utf8(out, ds.model_dump_json(indent=1))
    print(f"wrote {out}  (backend={backend}, models={len(models)})")


if __name__ == "__main__":
    main()
