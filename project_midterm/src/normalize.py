"""Light normalization for PxWeb CSV output.

What this module deliberately does NOT do:
- join tables
- compute yield, value, or lags
- drop rows
- impute
- aggregate periods

It only reshapes wide -> long, decodes the geolocation hierarchy,
labels periods, and converts missing markers to null while preserving
the raw marker in ``value_raw``.
"""

from __future__ import annotations

import re
from io import StringIO

import pandas as pd

MONTHS = {
    name: idx
    for idx, name in enumerate(
        [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ],
        start=1,
    )
}

DOTS_RE = re.compile(r"^(\.*)")
FOOTNOTE_RE = re.compile(r"\s+[A-Za-z0-9]\/\s*$")
YEAR_TOKEN = re.compile(r"^\d{4}$")


def read_wide(text: str) -> pd.DataFrame:
    """Read a PxWeb CSV as strings, preserving blanks and '..' markers."""
    return pd.read_csv(StringIO(text), dtype=str, keep_default_na=False)


def period_type_and_num(period: str) -> tuple[str, int]:
    p = str(period).strip()
    low = p.lower()

    if low.startswith("quarter"):
        digits = re.sub(r"\D", "", p)
        return "quarter", int(digits) if digits else 0
    if low.startswith("semester"):
        digits = re.sub(r"\D", "", p)
        return "semester", int(digits) if digits else 0
    if low == "annual":
        return "annual", 0
    if p in MONTHS:
        return "month", MONTHS[p]
    return "unknown", 0


def _tokens(label: str) -> list[str]:
    return str(label).split()


def is_time_column(label: str) -> bool:
    """True when the label starts or ends with a 4-digit year.

    PxWeb puts the year in the column label. Most tables use
    ``2023 Quarter1``; PPA combines valuation and year as
    ``At Current Prices 2018``.
    """
    tokens = _tokens(label)
    if not tokens:
        return False
    return bool(YEAR_TOKEN.match(tokens[0]) or YEAR_TOKEN.match(tokens[-1]))


def parse_time_label(label: str) -> tuple[str, int, str]:
    """Return (prefix, year, period) for a PxWeb time column label."""
    tokens = _tokens(label)
    if tokens and YEAR_TOKEN.match(tokens[0]):
        return "", int(tokens[0]), (" ".join(tokens[1:]) or "Annual")
    if tokens and YEAR_TOKEN.match(tokens[-1]):
        return " ".join(tokens[:-1]), int(tokens[-1]), "Annual"
    raise ValueError(f"Not a time label: {label!r}")


def clean_geo_label(label: str) -> tuple[int, str]:
    """Return (hierarchy level, cleaned name) from a dotted PSA label.

    PSA encodes hierarchy with leading dots: 2 = region, 4 = province,
    6 = city/HUC. Footnote markers such as ' a/' are stripped.
    """
    label = str(label)
    dots = len(DOTS_RE.match(label).group(1))
    level = dots // 2
    name = DOTS_RE.sub("", label).strip()
    name = FOOTNOTE_RE.sub("", name).strip()
    name = re.sub(r"\s+", " ", name)
    return level, name


def add_geo_hierarchy(df: pd.DataFrame, geo_col: str = "Geolocation") -> pd.DataFrame:
    """Decode region/province context. Assumes rows are in source order."""
    levels: list[int] = []
    regions: list[str | None] = []
    provinces: list[str | None] = []
    names: list[str] = []

    current_region: str | None = None
    current_province: str | None = None

    for label in df[geo_col].fillna(""):
        level, name = clean_geo_label(label)
        if level == 0:
            current_region = None
            current_province = None
        elif level == 1:
            current_region = name
            current_province = None
        elif level == 2:
            current_province = name
        levels.append(level)
        regions.append(current_region)
        provinces.append(current_province)
        names.append(name)

    out = df.copy()
    out["geo_level"] = levels
    out["geo_level_name"] = out["geo_level"].map(
        {0: "national", 1: "region", 2: "province", 3: "city"}
    )
    out["region_name"] = regions
    out["province_name"] = provinces
    out["geo_name"] = names
    return out.drop(columns=[geo_col])


def add_geo_simple(df: pd.DataFrame, geo_col: str = "Geolocation") -> pd.DataFrame:
    """Strip dots without inferring hierarchy (used for PPA geographies)."""
    out = df.copy()
    parsed = out[geo_col].fillna("").map(clean_geo_label)
    out["geo_level"] = parsed.map(lambda item: item[0])
    out["geo_name"] = parsed.map(lambda item: item[1])
    return out.drop(columns=[geo_col])


def melt_pxweb(
    df: pd.DataFrame,
    source_table: str,
    prefix_dimension: str | None = None,
) -> pd.DataFrame:
    """Melt time columns into rows and normalize values.

    ``prefix_dimension`` names the dimension that PxWeb folded into the
    column label (for PPA this is ``Type of Valuation``).
    """
    time_cols = [c for c in df.columns if is_time_column(c)]
    if not time_cols:
        raise ValueError(f"No time columns found. Columns: {list(df.columns)[:10]}")

    dim_cols = [c for c in df.columns if c not in time_cols]
    long = df.melt(
        id_vars=dim_cols,
        value_vars=time_cols,
        var_name="time_label",
        value_name="value_raw",
    )

    parsed = long["time_label"].map(parse_time_label)
    long["column_prefix"] = parsed.map(lambda item: item[0])
    long["year"] = parsed.map(lambda item: item[1])
    long["period"] = parsed.map(lambda item: item[2])

    raw = long["value_raw"].fillna("").str.strip()
    numeric = raw.str.replace(",", "", regex=False)
    numeric = numeric.replace({"": None, "..": None, "...": None, "-": None, "/s": None})
    long["value"] = pd.to_numeric(numeric, errors="coerce")

    meta = long["period"].map(period_type_and_num)
    long["period_type"] = meta.map(lambda item: item[0])
    long["period_num"] = meta.map(lambda item: item[1])

    if prefix_dimension:
        long[prefix_dimension] = long["column_prefix"]
    long = long.drop(columns=["time_label", "column_prefix"])

    long.insert(0, "source_table", source_table)
    return long


def snake_case(name: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z]+", "_", str(name).strip().lower())
    return re.sub(r"_+", "_", s).strip("_")
