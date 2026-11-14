"""Shared helpers for the data scripts."""
import json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
DATA = ROOT / "data"

# Folders the scripts write to. Created automatically so a fresh checkout / unzip just works.
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
NEX_CACHE = RAW / "nex_gddp"


def ensure_dirs() -> None:
    for d in (RAW, PROCESSED, NEX_CACHE):
        d.mkdir(parents=True, exist_ok=True)


def load_env() -> None:
    """Read backend/.env (same file the API uses) so EE_PROJECT etc. also work for scripts. Real env vars win."""
    f = ROOT / "backend" / ".env"
    if not f.is_file():
        return
    for line in f.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def write_text_utf8(path: Path, text: str) -> None:
    """Always UTF-8 (Path.write_text() uses the Windows ANSI code page by default, which produced files the
    API could not read, and cannot even encode characters such as '−'). Written atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def load_location(location_id: str) -> dict:
    for l in json.loads((DATA / "metadata" / "locations.json").read_text(encoding="utf-8"))["locations"]:
        if l["id"] == location_id:
            return l
    raise SystemExit(f"Unknown location {location_id}")


ensure_dirs()
load_env()
