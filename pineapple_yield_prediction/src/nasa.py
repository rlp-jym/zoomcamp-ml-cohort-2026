"""NASA POWER monthly weather acquisition and normalization."""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlencode

from .http_client import request

FILL_VALUE = -999.0


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")


def build_url(
    api_base: str,
    latitude: float,
    longitude: float,
    parameters: list[str],
    community: str,
    start_year: int,
    end_year: int,
) -> str:
    query = {
        "parameters": ",".join(parameters),
        "community": community,
        "longitude": f"{longitude:.5f}",
        "latitude": f"{latitude:.5f}",
        "start": str(start_year),
        "end": str(end_year),
        "format": "JSON",
    }
    return f"{api_base}?{urlencode(query)}"


def fetch_province(
    api_base: str,
    latitude: float,
    longitude: float,
    parameters: list[str],
    community: str,
    start_year: int,
    end_year: int,
) -> tuple[str, str]:
    url = build_url(api_base, latitude, longitude, parameters, community, start_year, end_year)
    resp = request("GET", url)
    return url, resp.text


def normalize_file(
    path: Path,
    region_name: str,
    province_name: str,
) -> list[dict]:
    """Convert one raw NASA JSON into long rows (YYYY13 annual row dropped)."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    series = payload["properties"]["parameter"]
    parameter_meta = payload.get("parameters", {})

    rows: list[dict] = []
    for parameter, values in series.items():
        unit = parameter_meta.get(parameter, {}).get("units")
        for key, value in values.items():
            if len(key) != 6 or not key.isdigit():
                continue
            year = int(key[:4])
            month = int(key[4:])
            if month == 13:  # annual aggregate, would double count
                continue
            if value == FILL_VALUE:
                value = None
            rows.append(
                {
                    "region_name": region_name,
                    "province_name": province_name,
                    "year": year,
                    "month": month,
                    "parameter": parameter,
                    "unit": unit,
                    "value": value,
                }
            )
    return rows
