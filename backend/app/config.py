"""Runtime configuration (environment variables only; no secrets are stored in code)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv() -> None:
    """Tiny .env reader (backend/.env). Real environment variables always win."""
    f = Path(__file__).resolve().parents[1] / ".env"
    if not f.is_file():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()


def _bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    demo_mode: bool
    cors_origins: tuple[str, ...]

    @property
    def processed_dir(self) -> Path:
        """Real, script-produced scientific data. Never contains synthetic values."""
        return self.data_dir / "processed"

    @property
    def demo_dir(self) -> Path:
        """Synthetic demonstration data, isolated from processed/."""
        return self.data_dir / "demo"

    @property
    def metadata_dir(self) -> Path:
        return self.data_dir / "metadata"


def get_settings() -> Settings:
    origins = os.environ.get("EARTH_DUET_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    return Settings(
        data_dir=Path(os.environ.get("EARTH_DUET_DATA_DIR", REPO_ROOT / "data")),
        demo_mode=_bool("EARTH_DUET_DEMO_MODE", False),
        cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
    )
