"""Loads and validates processed datasets. Keyed by (location, variable) — no location is hard-coded.

Real data lives in data/processed. Synthetic demo data lives in data/demo and is only
served when EARTH_DUET_DEMO_MODE is enabled, and is always flagged is_demo=True.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from ..config import Settings
from ..schemas.datasets import ObservedDataset, ProjectionDataset


class DatasetUnavailable(Exception):
    def __init__(self, code: str, message: str, hint: Optional[str] = None):
        super().__init__(message)
        self.code, self.message, self.hint = code, message, hint


def _read_text_robust(path: Path) -> str:
    """Read a dataset file as UTF-8. Earlier versions of the fetch scripts wrote files with the Windows ANSI code
    page (cp1252) on Windows; those contain bytes such as 0xB0 ('°') that are invalid UTF-8. Fall back to cp1252
    for such files so they still load; nothing is altered or guessed - only the character decoding differs."""
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252")


class DatasetStore:
    def __init__(self, settings: Settings):
        self.settings = settings

    # --- metadata ---
    def _meta(self, name: str) -> dict:
        return json.loads((self.settings.metadata_dir / name).read_text(encoding="utf-8"))

    def locations(self) -> list[dict]:
        return self._meta("locations.json")["locations"]

    def variables(self) -> list[dict]:
        return self._meta("variables.json")["variables"]

    def scenarios(self) -> dict:
        return self._meta("scenarios.json")

    def imagery(self) -> dict:
        return self._meta("imagery.json")

    def location(self, location_id: str) -> dict:
        for loc in self.locations():
            if loc["id"] == location_id:
                return loc
        raise DatasetUnavailable("unknown_location", f"Unknown location '{location_id}'.",
                                 "Use GET /api/locations for valid ids.")

    def variable(self, variable_id: str) -> dict:
        for v in self.variables():
            if v["id"] == variable_id:
                return v
        raise DatasetUnavailable("unknown_variable", f"Unknown variable '{variable_id}'.",
                                 "Use GET /api/variables for valid ids.")

    # --- datasets ---
    def _path(self, kind: str, location: str, variable: str) -> tuple[Path, bool]:
        name = f"{location}__{variable}__{kind}.json"
        real = self.settings.processed_dir / name
        if real.exists():
            return real, False
        if self.settings.demo_mode:
            demo = self.settings.demo_dir / name
            if demo.exists():
                return demo, True
        raise DatasetUnavailable(
            "dataset_not_available",
            f"No {kind} dataset is available for location '{location}', variable '{variable}'.",
            "Run scripts/fetch_historical.py / fetch_projections.py with network access, "
            "or set EARTH_DUET_DEMO_MODE=true for clearly-labelled synthetic demo data.",
        )

    def _load(self, model, kind: str, location: str, variable: str):
        self.variable(variable)
        loc = self.location(location)
        if loc["status"] != "primary_mvp":
            raise DatasetUnavailable("dataset_not_configured",
                                     f"Dataset not configured for {loc['name']}.",
                                     "Only Cairo and Aswan have configured datasets in this MVP.")
        path, is_demo = self._path(kind, location, variable)
        try:
            ds = model.model_validate_json(_read_text_robust(path))
        except OSError as e:
            raise DatasetUnavailable("dataset_invalid", f"Dataset {path.name} could not be read: {e}.")
        except ValidationError as e:
            raise DatasetUnavailable("dataset_invalid", f"Dataset {path.name} failed validation: {e.error_count()} error(s).",
                                     str(e)[:500])
        if is_demo and not ds.is_demo:
            raise DatasetUnavailable("dataset_invalid", "Demo directory contains a non-demo dataset.")
        if not is_demo and ds.is_demo:
            raise DatasetUnavailable("dataset_invalid", "processed/ must never contain synthetic data.")
        return ds

    def observed(self, location: str, variable: str) -> ObservedDataset:
        return self._load(ObservedDataset, "observed", location, variable)

    def projection(self, location: str, variable: str) -> ProjectionDataset:
        return self._load(ProjectionDataset, "projection", location, variable)

    def diagnostics(self) -> dict:
        """Where this running server looks for data, and which expected files exist there (no records)."""
        files = {}
        for loc in self.locations():
            if loc["status"] != "primary_mvp":
                continue
            for kind in ("observed", "projection"):
                name = f"{loc['id']}__{loc['primary_variable']}__{kind}.json"
                p = self.settings.processed_dir / name
                files[name] = {"exists": p.is_file(), "bytes": p.stat().st_size if p.is_file() else None}
        return {"data_dir": str(self.settings.data_dir.resolve()),
                "processed_dir": str(self.settings.processed_dir.resolve()), "processed_files": files}

    def dataset_status(self, loc: dict) -> tuple[str, str]:
        if loc["status"] != "primary_mvp":
            return "not_configured", "Dataset not configured"
        var = loc["primary_variable"]
        real = (self.settings.processed_dir / f"{loc['id']}__{var}__observed.json").exists()
        if real:
            return "configured", "Real NASA-derived datasets loaded"
        demo = (self.settings.demo_dir / f"{loc['id']}__{var}__observed.json").exists()
        if self.settings.demo_mode and demo:
            return "demo_only", "SYNTHETIC DEMO DATA — not NASA measurements"
        return "data_not_fetched", "Integration implemented; run the fetch scripts to download real data"
