"""Geographic reference data: PSGC provinces and province centroids.

Centroids come from geoBoundaries ADM2 (PHL provinces), sourced from
NAMRIA / PSA / OCHA Philippines under CC BY 3.0 IGO. They are computed
once and committed as a reference CSV so the rest of the pipeline never
needs a shapefile or a geometry library.

Name matching is deliberately explicit: exact raw name, then a curated
alias, then a conservative fuzzy score. Collisions such as
``Cotabato`` vs ``Cotabato City`` are resolved in favour of the
non-city record.
"""

from __future__ import annotations

import json
import re
import unicodedata
from difflib import SequenceMatcher

import pandas as pd

from .http_client import request

PSGC_ORIGIN = "https://statistics.bettergov.ph"
PAGE_SIZE = 1000

# PSGC province name -> geoBoundaries raw name.
ALIASES_PSGC_TO_GB = {
    "davao de oro": "compostela valley",
    "maguindanao del norte": "maguindanao",
    "maguindanao del sur": "maguindanao",
}

# Observed PSA name -> PSGC name (code lookup only).
ALIASES_PSA_TO_PSGC = {
    "compostela valley": "davao de oro",
    "north cotabato": "cotabato",
}

# Hand-entered centroids for HUCs that geoBoundaries does not publish
# as ADM2 units. Used only when no polygon match exists.
MANUAL_CENTROIDS = {
    "puerto princesa": (9.739200, 118.735300),
    "bacolod": (10.676500, 122.950900),
    "butuan": (8.947500, 125.540600),
}


def norm_name(value: str) -> str:
    """Lowercase, strip accents/punctuation and generic geographic words."""
    s = unicodedata.normalize("NFKD", str(value))
    s = s.encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"\b(city|municipality|province|of)\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def fetch_psgc_resource(base: str, resource: str) -> list[dict]:
    """Fetch every page of a PSGC resource."""
    url = f"{base}/{resource}?page_size={PAGE_SIZE}&page=1"
    rows: list[dict] = []
    while url:
        resp = request("GET", url)
        payload = resp.json()
        rows.extend(payload.get("results", []))
        nxt = payload.get("next")
        url = f"{PSGC_ORIGIN}{nxt}" if nxt else None
    return rows


def fetch_geoboundaries(api_url: str) -> tuple[dict, str, str]:
    """Return (metadata, geojson_url, geojson_text)."""
    meta = request("GET", api_url).json()
    geojson_url = meta.get("simplifiedGeometryGeoJSON") or meta.get("gjDownloadURL")
    if not geojson_url:
        raise ValueError("geoBoundaries metadata has no GeoJSON download URL")
    resp = request("GET", geojson_url)
    return meta, geojson_url, resp.text


def _ring_centroid(coords: list) -> tuple[float, float, float]:
    """Area-weighted centroid of a closed ring using the shoelace formula."""
    area = 0.0
    cx = 0.0
    cy = 0.0
    for i in range(len(coords) - 1):
        x0, y0 = coords[i][0], coords[i][1]
        x1, y1 = coords[i + 1][0], coords[i + 1][1]
        cross = x0 * y1 - x1 * y0
        area += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross

    area *= 0.5
    if abs(area) < 1e-12:
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        return sum(xs) / len(xs), sum(ys) / len(ys), 0.0

    return cx / (6.0 * area), cy / (6.0 * area), abs(area)


def geometry_centroid(geometry: dict) -> tuple[float, float, float]:
    """Centroid of a Polygon/MultiPolygon; largest polygon wins for multipart."""
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")

    if gtype == "Polygon":
        return _ring_centroid(coords[0])

    if gtype == "MultiPolygon":
        best: tuple[float, float, float] | None = None
        for polygon in coords:
            candidate = _ring_centroid(polygon[0])
            if best is None or candidate[2] > best[2]:
                best = candidate
        if best is None:
            raise ValueError("Empty MultiPolygon")
        return best

    raise ValueError(f"Unsupported geometry type: {gtype}")


def parse_geoboundaries(text: str) -> pd.DataFrame:
    """Parse GeoJSON into a province centroid table."""
    payload = json.loads(text)
    rows = []
    for feature in payload.get("features", []):
        props = feature.get("properties", {})
        name = props.get("shapeName") or props.get("name")
        if not name:
            continue
        lon, lat, area = geometry_centroid(feature["geometry"])
        rows.append(
            {
                "geoboundaries_name": name,
                "latitude": round(lat, 6),
                "longitude": round(lon, 6),
                "polygon_area_deg2": round(area, 8),
            }
        )
    return pd.DataFrame(rows)


def _index_by_norm(
    rows: list[dict],
    name_key: str,
    prefer_non_city: bool = False,
) -> dict[str, dict]:
    """Index rows by normalized name, optionally preferring non-city records."""
    index: dict[str, dict] = {}
    for row in rows:
        key = norm_name(row[name_key])
        if not key:
            continue
        current = index.get(key)
        if current is None:
            index[key] = row
            continue
        if prefer_non_city:
            row_is_city = "city" in str(row[name_key]).lower()
            current_is_city = "city" in str(current.get(name_key, "")).lower()
            if not row_is_city and current_is_city:
                index[key] = row
    return index


def _match(
    target: str,
    index: dict[str, dict],
    aliases: dict[str, str] | None = None,
    threshold: float = 0.90,
) -> tuple[dict | None, str]:
    key = norm_name(target)
    if aliases:
        key = aliases.get(key, key)

    if key in index:
        return index[key], "exact"

    best_key = None
    best_score = 0.0
    for candidate in index:
        score = SequenceMatcher(None, key, candidate).ratio()
        if score > best_score:
            best_key, best_score = candidate, score

    if best_key is not None and best_score >= threshold:
        return index[best_key], f"fuzzy:{best_score:.2f}"
    return None, "none"


def build_centroid_reference(
    psgc_provinces: pd.DataFrame,
    gb_df: pd.DataFrame,
) -> pd.DataFrame:
    """Match PSGC provinces to geoBoundaries centroids."""
    gb_rows = gb_df.to_dict("records")
    gb_by_raw = {row["geoboundaries_name"]: row for row in gb_rows}
    gb_index = _index_by_norm(gb_rows, "geoboundaries_name", prefer_non_city=True)

    rows = []
    for _, province in psgc_provinces.iterrows():
        name = province["area_name"]
        match = None
        method = "none"

        if name in gb_by_raw:
            match, method = gb_by_raw[name], "exact"
        else:
            match, method = _match(name, gb_index, ALIASES_PSGC_TO_GB)

        rows.append(
            {
                "psgc_code": province["code"],
                "psgc_name": name,
                "geographic_level": province.get("geographic_level"),
                "region_code": province.get("reg"),
                "geoboundaries_name": match["geoboundaries_name"] if match else None,
                "latitude": match["latitude"] if match else None,
                "longitude": match["longitude"] if match else None,
                "centroid_match_method": method,
            }
        )

    return pd.DataFrame(rows)


def build_province_reference(
    observed: list[tuple[str, str]],
    psgc_centroids: pd.DataFrame,
    gb_df: pd.DataFrame,
    psgc_all: pd.DataFrame,
) -> pd.DataFrame:
    """Map observed PSA province names to PSGC codes and coordinates.

    Code resolution and centroid resolution are independent: a name can
    have a PSGC code but no polygon (new provinces), or a polygon but no
    current PSGC record (retired names).
    """
    psgc_rows = psgc_all.to_dict("records")
    psgc_index = _index_by_norm(psgc_rows, "area_name", prefer_non_city=False)
    centroid_rows = psgc_centroids.to_dict("records")
    centroid_index = {
        row["psgc_name"]: row
        for row in centroid_rows
        if row.get("latitude") is not None and not pd.isna(row.get("latitude"))
    }

    gb_rows = gb_df.to_dict("records")
    gb_by_raw = {row["geoboundaries_name"]: row for row in gb_rows}
    gb_index = _index_by_norm(gb_rows, "geoboundaries_name", prefer_non_city=True)

    rows = []
    for region, province in observed:
        # 1. PSGC code lookup
        psgc_match, psgc_method = _match(province, psgc_index, ALIASES_PSA_TO_PSGC)

        # 2. Centroid: PSGC centroid -> direct geoBoundaries -> manual
        centroid = None
        centroid_method = "none"
        if psgc_match is not None:
            centroid = centroid_index.get(psgc_match["area_name"])
            if centroid is not None:
                centroid_method = "psgc"

        if centroid is None:
            raw_row = gb_by_raw.get(province)
            if raw_row is not None:
                centroid, centroid_method = raw_row, "geoboundaries:exact"
            else:
                gb_match, gb_method = _match(province, gb_index, ALIASES_PSGC_TO_GB)
                if gb_match is not None:
                    centroid, centroid_method = gb_match, f"geoboundaries:{gb_method}"

        if centroid is None:
            manual = MANUAL_CENTROIDS.get(norm_name(province))
            if manual is not None:
                centroid = {"latitude": manual[0], "longitude": manual[1], "geoboundaries_name": None}
                centroid_method = "manual"

        rows.append(
            {
                "region_name": region,
                "province_name": province,
                "psgc_code": psgc_match["code"] if psgc_match is not None else None,
                "psgc_name": psgc_match["area_name"] if psgc_match is not None else None,
                "psgc_match_method": psgc_method,
                "geoboundaries_name": (
                    centroid.get("geoboundaries_name") if centroid is not None else None
                ),
                "latitude": centroid.get("latitude") if centroid is not None else None,
                "longitude": centroid.get("longitude") if centroid is not None else None,
                "centroid_match_method": centroid_method,
            }
        )

    return pd.DataFrame(rows)
