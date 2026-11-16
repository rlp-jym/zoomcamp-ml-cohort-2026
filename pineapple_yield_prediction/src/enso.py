"""NOAA Oceanic Niño Index (ONI) acquisition and parsing."""

from __future__ import annotations

from .http_client import request


def fetch(url: str) -> str:
    resp = request("GET", url)
    return resp.text


def parse(text: str) -> list[dict]:
    """Parse the fixed-width ONI text table."""
    rows: list[dict] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        season, year, total, anomaly = parts[:4]
        if not year.isdigit():
            continue
        try:
            rows.append(
                {
                    "season": season,
                    "year": int(year),
                    "total": float(total),
                    "anomaly": float(anomaly),
                }
            )
        except ValueError:
            continue
    return rows
