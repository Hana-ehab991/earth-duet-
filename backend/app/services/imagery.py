"""Imagery availability logic (pure; the server never fetches tiles)."""
from __future__ import annotations

from datetime import date
from typing import Optional


def imagery_for_year(layer: dict, year: int, today: Optional[date] = None) -> dict:
    today = today or date.today()
    start = date.fromisoformat(layer["documented_start_date"])
    month, day = (int(x) for x in layer["representative_month_day"].split("-"))
    try:
        target = date(year, month, day)
    except ValueError:
        return {"available": False, "date": None, "reason": "invalid_date"}
    if target < start:
        return {"available": False, "date": None,
                "reason": f"Layer documented start date is {start.isoformat()}; no imagery for {year}."}
    if target > today:
        return {"available": False, "date": None,
                "reason": "Representative date is in the future; no observed imagery exists yet."}
    return {"available": True, "date": target.isoformat(), "reason": None}
