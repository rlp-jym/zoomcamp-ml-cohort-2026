"""Pipeline orchestrator.

Usage (from pineapple_yield_prediction/):

    py -m src.run all
    py -m src.run --only psa,normalize
    py -m src.run --only nasa            # requires province_reference.csv
    py -m src.run all --refresh          # force fresh downloads
    py -m src.run all --offline          # use cached raw only

Steps: psa, normalize, geo, nasa, enso, docs
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

from . import enso as enso_mod
from . import geo as geo_mod
from . import nasa as nasa_mod
from . import psa as psa_mod
from .http_client import (
    display_path,
    record_provenance,
    sha256_bytes,
    utc_now_iso,
    write_json,
    write_text,
)
from .normalize import add_geo_hierarchy, add_geo_simple, melt_pxweb, read_wide, snake_case

ROOT = Path(__file__).resolve().parent.parent
ALL_STEPS = ["psa", "normalize", "geo", "nasa", "enso", "docs"]


def load_config() -> dict:
    with (ROOT / "src" / "config.yaml").open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def path_of(cfg: dict, key: str) -> Path:
    return ROOT / cfg["paths"][key]


def ensure_dirs(cfg: dict) -> None:
    for key in ("raw", "normalized", "reference", "provenance", "docs"):
        path_of(cfg, key).mkdir(parents=True, exist_ok=True)


def _read_csv_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def build_selections(name: str, meta: dict, cfg: dict) -> dict:
    start = int(cfg["psa"]["year_start"])
    end = int(cfg["psa"]["year_end"])
    years = psa_mod.resolve_years(meta, start, end)

    if name in {"production", "area"}:
        crops = psa_mod.resolve_codes(meta, "Crop", cfg["psa"]["production_crops"])
        return {"Crop": crops, "Year": years}
    if name == "farmgate":
        commodities = psa_mod.resolve_codes(
            meta, "Commodity", cfg["psa"]["farmgate_commodities"]
        )
        return {"Commodity": commodities, "Year": years}
    return {"Year": years}


def step_psa(cfg: dict, refresh: bool, offline: bool) -> None:
    api_base = cfg["psa"]["api_base"]
    raw_dir = path_of(cfg, "raw")
    prov_dir = path_of(cfg, "provenance")

    for name, spec in cfg["psa"]["tables"].items():
        raw_path = raw_dir / spec["raw"]
        meta_path = raw_dir / spec["metadata"]

        if raw_path.exists() and meta_path.exists() and not refresh:
            print(f"[psa] cache hit: {name}")
            continue
        if offline:
            raise FileNotFoundError(f"Offline mode but missing cache for {name}")

        print(f"[psa] fetching metadata: {name}")
        meta, meta_text, meta_resp = psa_mod.fetch_metadata(api_base, spec["path"])
        write_text(meta_path, meta_text)

        selections = build_selections(name, meta, cfg)
        query = psa_mod.build_query(meta, selections)

        print(f"[psa] fetching table: {name}")
        csv_text, url, table_resp = psa_mod.fetch_table(api_base, spec["path"], query)
        write_text(raw_path, csv_text)

        record_provenance(
            prov_dir,
            name,
            url=url,
            method="POST",
            request_body=query,
            response=table_resp,
            file_path=raw_path,
        )
        record_provenance(
            prov_dir,
            f"{name}_metadata",
            url=url,
            method="GET",
            response=meta_resp,
            file_path=meta_path,
        )
        rows = max(0, csv_text.count("\n") - 1)
        print(f"[psa] wrote {raw_path.relative_to(ROOT)} ({rows} data rows)")


def _normalize_table(
    raw_path: Path,
    out_path: Path,
    source_table: str,
    hierarchy: bool,
    prefix_dimension: str | None = None,
) -> pd.DataFrame:
    wide = read_wide(_read_csv_text(raw_path))
    wide = add_geo_hierarchy(wide) if hierarchy else add_geo_simple(wide)
    long = melt_pxweb(wide, source_table, prefix_dimension=prefix_dimension)
    long.columns = [snake_case(column) for column in long.columns]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    long.to_csv(out_path, index=False, encoding="utf-8")
    print(f"[normalize] {out_path.relative_to(ROOT)} -> {len(long):,} rows")
    return long


def step_normalize(cfg: dict) -> list[tuple[str, str]]:
    raw_dir = path_of(cfg, "raw") / "psa"
    norm_dir = path_of(cfg, "normalized")
    tables = cfg["psa"]["tables"]

    production = _normalize_table(
        raw_dir / Path(tables["production"]["raw"]).name,
        norm_dir / "psa_production_long.csv",
        "production",
        hierarchy=True,
    )
    _normalize_table(
        raw_dir / Path(tables["area"]["raw"]).name,
        norm_dir / "psa_area_long.csv",
        "area",
        hierarchy=True,
    )
    _normalize_table(
        raw_dir / Path(tables["farmgate"]["raw"]).name,
        norm_dir / "psa_farmgate_long.csv",
        "farmgate",
        hierarchy=True,
    )
    _normalize_table(
        raw_dir / Path(tables["ppa"]["raw"]).name,
        norm_dir / "psa_ppa_long.csv",
        "ppa",
        hierarchy=False,
        prefix_dimension="Type of Valuation",
    )

    provinces = (
        production.loc[production["geo_level"] == 2, ["region_name", "province_name"]]
        .dropna()
        .drop_duplicates()
        .sort_values(["region_name", "province_name"])
    )
    observed = list(provinces.itertuples(index=False, name=None))
    write_json(
        path_of(cfg, "reference") / "observed_provinces.json",
        {"count": len(observed), "provinces": observed},
    )
    print(f"[normalize] observed province units: {len(observed)}")
    return observed


def step_geo(
    cfg: dict,
    refresh: bool,
    offline: bool,
    observed: list[tuple[str, str]] | None,
) -> None:
    raw_dir = path_of(cfg, "raw")
    ref_dir = path_of(cfg, "reference")
    prov_dir = path_of(cfg, "provenance")
    psgc_raw = raw_dir / "psgc"
    gb_raw = raw_dir / "geoboundaries"

    regions_path = psgc_raw / "regions.json"
    provinces_path = psgc_raw / "provinces.json"

    if refresh or not (regions_path.exists() and provinces_path.exists()):
        if offline:
            raise FileNotFoundError("Offline mode but PSGC cache is missing")
        print("[geo] fetching PSGC regions and provinces")
        regions = geo_mod.fetch_psgc_resource(cfg["geo"]["psgc_base"], "regions")
        provinces = geo_mod.fetch_psgc_resource(cfg["geo"]["psgc_base"], "provinces")
        write_json(
            regions_path,
            {"retrieved_at_utc": utc_now_iso(), "count": len(regions), "results": regions},
        )
        write_json(
            provinces_path,
            {"retrieved_at_utc": utc_now_iso(), "count": len(provinces), "results": provinces},
        )
        record_provenance(
            prov_dir,
            "psgc",
            url=f"{cfg['geo']['psgc_base']}/provinces",
            method="GET",
            file_path=provinces_path,
            extra={"regions_file": display_path(regions_path)},
        )
    else:
        print("[geo] PSGC cache hit")
        regions = json.loads(regions_path.read_text(encoding="utf-8"))["results"]
        provinces = json.loads(provinces_path.read_text(encoding="utf-8"))["results"]

    psgc_df = pd.DataFrame(provinces)
    psgc_df.to_csv(ref_dir / "psgc_provinces.csv", index=False, encoding="utf-8")

    gb_path = gb_raw / "PHL_ADM2.geojson"
    gb_meta_path = gb_raw / "PHL_ADM2.metadata.json"

    if refresh or not (gb_path.exists() and gb_meta_path.exists()):
        if offline:
            raise FileNotFoundError("Offline mode but geoBoundaries cache is missing")
        print("[geo] fetching geoBoundaries ADM2")
        meta, geojson_url, geojson_text = geo_mod.fetch_geoboundaries(
            cfg["geo"]["geoboundaries_adm2_api"]
        )
        write_json(gb_meta_path, meta)
        write_text(gb_path, geojson_text)
        record_provenance(
            prov_dir,
            "geoboundaries_adm2",
            url=geojson_url,
            method="GET",
            file_path=gb_path,
            extra={"license": meta.get("boundaryLicense"), "source": meta.get("boundarySource")},
        )
    else:
        print("[geo] geoBoundaries cache hit")

    gb_df = geo_mod.parse_geoboundaries(gb_path.read_text(encoding="utf-8"))
    gb_df.to_csv(ref_dir / "geoboundaries_provinces.csv", index=False, encoding="utf-8")

    province_level = psgc_df
    if "geographic_level" in psgc_df.columns:
        province_level = psgc_df[psgc_df["geographic_level"] == "Prov"]
        if province_level.empty:
            province_level = psgc_df

    centroids = geo_mod.build_centroid_reference(province_level, gb_df)
    centroids.to_csv(ref_dir / "psgc_centroids.csv", index=False, encoding="utf-8")

    if observed is None:
        observed_path = ref_dir / "observed_provinces.json"
        if not observed_path.exists():
            raise FileNotFoundError(
                "observed_provinces.json missing; run the normalize step first"
            )
        payload = json.loads(observed_path.read_text(encoding="utf-8"))
        observed = [tuple(item) for item in payload["provinces"]]

    reference = geo_mod.build_province_reference(observed, centroids, gb_df, psgc_df)
    reference.to_csv(ref_dir / "province_reference.csv", index=False, encoding="utf-8")

    unmatched = reference[reference["centroid_match_method"] == "none"]
    print(
        f"[geo] province reference: {len(reference)} units, "
        f"{len(unmatched)} without centroid -> {ref_dir / 'province_reference.csv'}"
    )
    for _, row in unmatched.iterrows():
        print(f"[geo]   UNMATCHED: {row['region_name']} / {row['province_name']}")


def step_nasa(cfg: dict, refresh: bool, offline: bool) -> None:
    ref_dir = path_of(cfg, "reference")
    raw_dir = path_of(cfg, "raw") / "nasa"
    prov_dir = path_of(cfg, "provenance")
    norm_dir = path_of(cfg, "normalized")
    raw_dir.mkdir(parents=True, exist_ok=True)

    reference_path = ref_dir / "province_reference.csv"
    if not reference_path.exists():
        raise FileNotFoundError(
            "province_reference.csv missing; run the geo step first"
        )
    reference = pd.read_csv(reference_path, dtype=str)

    prov_path = prov_dir / "nasa.json"
    existing: dict[str, dict] = {}
    if prov_path.exists():
        try:
            payload = json.loads(prov_path.read_text(encoding="utf-8"))
            existing = {
                item["artifact"]: item
                for item in payload.get("requests", [])
                if item.get("artifact")
            }
        except (json.JSONDecodeError, KeyError):
            existing = {}

    records: list[dict] = []
    for _, row in reference.iterrows():
        latitude = row.get("latitude")
        longitude = row.get("longitude")
        if pd.isna(latitude) or pd.isna(longitude) or not latitude or not longitude:
            records.append(
                {
                    "region_name": row.get("region_name"),
                    "province_name": row.get("province_name"),
                    "skipped": "no centroid",
                }
            )
            continue

        slug = nasa_mod.slugify(f"{row['region_name']}-{row['province_name']}")
        raw_path = raw_dir / f"{slug}.json"

        if refresh or not raw_path.exists():
            if offline:
                raise FileNotFoundError(f"Offline mode but missing NASA cache: {slug}")
            url, text = nasa_mod.fetch_province(
                cfg["nasa"]["api_base"],
                float(latitude),
                float(longitude),
                cfg["nasa"]["parameters"],
                cfg["nasa"]["community"],
                int(cfg["nasa"]["start_year"]),
                int(cfg["nasa"]["end_year"]),
            )
            write_text(raw_path, text)
            print(f"[nasa] fetched {row['province_name']}")
            records.append(
                {
                    "artifact": slug,
                    "region_name": row.get("region_name"),
                    "province_name": row.get("province_name"),
                    "url": url,
                    "retrieved_at_utc": utc_now_iso(),
                    "file": display_path(raw_path),
                    "file_sha256": sha256_bytes(raw_path.read_bytes()),
                }
            )
        else:
            record = dict(existing.get(slug, {}))
            record.update(
                {
                    "artifact": slug,
                    "region_name": row.get("region_name"),
                    "province_name": row.get("province_name"),
                    "file": display_path(raw_path),
                    "file_sha256": sha256_bytes(raw_path.read_bytes()),
                }
            )
            record.setdefault("cached", True)
            records.append(record)

    write_json(
        prov_dir / "nasa.json",
        {"generated_at_utc": utc_now_iso(), "requests": records},
    )

    rows: list[dict] = []
    for _, row in reference.iterrows():
        slug = nasa_mod.slugify(f"{row['region_name']}-{row['province_name']}")
        raw_path = raw_dir / f"{slug}.json"
        if raw_path.exists():
            rows.extend(
                nasa_mod.normalize_file(
                    raw_path, row["region_name"], row["province_name"]
                )
            )

    weather = pd.DataFrame(rows)
    weather.to_csv(norm_dir / "nasa_weather_long.csv", index=False, encoding="utf-8")
    print(f"[nasa] nasa_weather_long.csv -> {len(weather):,} rows")


def step_enso(cfg: dict, refresh: bool, offline: bool) -> None:
    raw_path = path_of(cfg, "raw") / "noaa" / "oni.ascii.txt"
    prov_dir = path_of(cfg, "provenance")
    norm_dir = path_of(cfg, "normalized")

    if refresh or not raw_path.exists():
        if offline:
            raise FileNotFoundError("Offline mode but ONI cache is missing")
        print("[enso] fetching ONI")
        text = enso_mod.fetch(cfg["enso"]["url"])
        write_text(raw_path, text)
        record_provenance(
            prov_dir,
            "oni",
            url=cfg["enso"]["url"],
            method="GET",
            file_path=raw_path,
        )
    else:
        print("[enso] cache hit")

    rows = enso_mod.parse(raw_path.read_text(encoding="utf-8"))
    frame = pd.DataFrame(rows)
    frame.to_csv(norm_dir / "noaa_enso_long.csv", index=False, encoding="utf-8")
    print(f"[enso] noaa_enso_long.csv -> {len(frame):,} rows")


def _file_facts(path: Path) -> dict:
    if not path.exists():
        return {"file": str(path), "missing": True}
    return {
        "file": str(path.relative_to(ROOT)),
        "bytes": path.stat().st_size,
        "sha256": sha256_bytes(path.read_bytes()),
    }


def step_docs(cfg: dict) -> None:
    docs = path_of(cfg, "docs")
    raw_dir = path_of(cfg, "raw")
    norm_dir = path_of(cfg, "normalized")
    ref_dir = path_of(cfg, "reference")

    sources = f"""# Data sources

Retrieved by `src/run.py`. All raw files are byte-exact snapshots.

## PSA OpenSTAT (authoritative)

- API base: `{cfg['psa']['api_base']}`
- HTML metadata pages return HTTP 403; the API works. Do not scrape HTML.
- Open data license: freely usable with attribution to the Philippine Statistics Authority.

| Dataset | Table path | Raw file |
|---|---|---|
| Fruit crops: volume of production | `{cfg['psa']['tables']['production']['path']}` | `{cfg['psa']['tables']['production']['raw']}` |
| Fruit crops: area planted/harvested | `{cfg['psa']['tables']['area']['path']}` | `{cfg['psa']['tables']['area']['raw']}` |
| Fruits: farmgate prices | `{cfg['psa']['tables']['farmgate']['path']}` | `{cfg['psa']['tables']['farmgate']['raw']}` |
| GDP by industry, province and HUC | `{cfg['psa']['tables']['ppa']['path']}` | `{cfg['psa']['tables']['ppa']['raw']}` |

## NASA POWER

- Endpoint: `{cfg['nasa']['api_base']}`
- Community: `{cfg['nasa']['community']}`
- No API key required.
- Monthly values for the grid cell nearest each province centroid.

| Parameter | Unit | Description |
|---|---|---|
| `PRECTOTCORR` | mm/day | Bias-corrected precipitation rate. Monthly total = value x days in month. |
| `T2M` | deg C | Mean air temperature at 2 m. |
| `T2M_MAX` | deg C | Mean daily maximum temperature at 2 m. |
| `T2M_MIN` | deg C | Mean daily minimum temperature at 2 m. |
| `RH2M` | % | Relative humidity at 2 m. |
| `ALLSKY_SFC_SW_DWN` | MJ/m2/day | All-sky surface shortwave downward irradiance (solar energy). |

- Fill value `-999.0` is stored as null.
- Annual rows (`YYYY13`) are dropped during normalization.

## NOAA ONI

- Endpoint: `{cfg['enso']['url']}`
- Index: Oceanic Nino Index (ONI)
- Region: Nino 3.4 (5N-5S, 120W-170W)
- Definition: 3-month running mean of sea-surface temperature anomalies
- Source dataset: ERSSTv5
- Base period: centered 30-year climatology, updated every five years;
  current base 1991-2020
- Units: degrees Celsius
- File columns: `SEAS` (season), `YR` (year), `TOTAL` (absolute SST),
  `ANOM` (anomaly)
- Seasons are overlapping 3-month windows (`DJF`, `JFM`, ..., `NDJ`)

## PSGC classification

- `{cfg['geo']['psgc_base']}/regions`
- `{cfg['geo']['psgc_base']}/provinces`
- Version: `Q2_2024`.

## geoBoundaries (province geometry, used once for centroids)

- Metadata: `{cfg['geo']['geoboundaries_adm2_api']}`
- Unit: PHL ADM2 (provinces), 87 units
- Source: NAMRIA / PSA / OCHA Philippines
- License: CC BY 3.0 IGO
- Centroid method: area-weighted polygon centroid (largest polygon for multipart)
- Tolerance: suitable for 0.5 degree NASA POWER grid sampling, not for mapping.

## Attribution

Philippine Statistics Authority (PSA) via OpenSTAT. geoBoundaries via the
geoBoundaries project (CC BY 3.0 IGO). NASA POWER via NASA Langley Research
Center. NOAA CPC for the ONI. BetterGov.ph classification API for PSGC codes.
"""
    write_text(docs / "sources.md", sources)

    dictionary = """# Data dictionary

## Layers

- `data/raw/` - byte-exact downloads. Never edited.
- `data/normalized/` - light reshaping only. No joins, no derived measures, no row drops.
- `data/reference/` - crosswalks and centroids used to key the data.

## Normalized files

### psa_production_long.csv
Pineapple volume of production.

| Column | Meaning |
|---|---|
| `source_table` | logical source name (`production`) |
| `crop` | PSA crop label |
| `geo_level` | 0 national, 1 region, 2 province or independent city, 3 city/HUC nested under a province |
| `geo_level_name` | label for the level |
| `region_name` | carried region context |
| `province_name` | carried province context |
| `geo_name` | geography label with dots removed |
| `year` | calendar year |
| `period` | source period label (`Quarter1`, `Semester1`, `Annual`, ...) |
| `period_type` | `quarter`, `semester`, `annual`, `month` |
| `period_num` | quarter/semester/month number; 0 for annual |
| `value_raw` | original source string (`..`, `/s`, number) |
| `value` | metric tons; null for `..` and other non-numeric markers |

### psa_area_long.csv
Same schema as production; `value` is hectares. Quarterly cells are mostly
null for pineapple; semester values are populated.

### psa_farmgate_long.csv
Same schema plus `commodity`; `value` is pesos per kilogram.

### psa_ppa_long.csv
Same schema plus `sector` and `type_of_valuation`; `value` is thousand pesos.
No region/province carry-forward: PPA geographies use a different label shape.

### nasa_weather_long.csv

| Column | Meaning |
|---|---|
| `region_name`, `province_name` | key matching the PSA normalized tables |
| `year`, `month` | calendar month |
| `parameter` | NASA POWER parameter code |
| `unit` | source unit |
| `value` | null when NASA returns -999.0 |

Parameter descriptions:

| Parameter | Unit | Description |
|---|---|---|
| `PRECTOTCORR` | mm/day | Bias-corrected precipitation rate. Monthly total = value x days in month; semester total = sum of monthly totals. |
| `T2M` | deg C | Mean air temperature at 2 m. |
| `T2M_MAX` | deg C | Mean daily maximum temperature at 2 m. |
| `T2M_MIN` | deg C | Mean daily minimum temperature at 2 m. |
| `RH2M` | % | Relative humidity at 2 m. |
| `ALLSKY_SFC_SW_DWN` | MJ/m2/day | All-sky surface shortwave downward irradiance (solar energy). |

Notes:

- Values are monthly means for the NASA POWER grid cell nearest the province centroid.
- `PRECTOTCORR` is a rate: multiply by days in month before summing.
- Temperature, humidity and solar are averaged over the semester.
- `-999.0` is the missing-value fill and is stored as null.
- The `YYYY13` annual row is dropped to avoid double counting.

### noaa_enso_long.csv

| Column | Meaning |
|---|---|
| `season` | 3-month window: `DJF`, `JFM`, `FMA`, ..., `NDJ` |
| `year` | year of the middle month of the window |
| `total` | absolute 3-month mean sea-surface temperature, deg C |
| `anomaly` | departure from the climatological normal, deg C |

Definitions:

- ONI: 3-month running mean of SST anomalies in the Nino 3.4 region
  (5N-5S, 120W-170W), ERSSTv5.
- Base period: centered 30-year climatology updated every five years;
  current base 1991-2020.
- El Nino: `anomaly >= +0.5 deg C` for five consecutive overlapping seasons.
- La Nina: `anomaly <= -0.5 deg C` for five consecutive overlapping seasons.
- Neutral: between -0.5 and +0.5 deg C.
- Magnitude: +/-0.5 weak, +/-1.0 moderate, +/-1.5 strong, +/-2.0 very strong.
- Seasons overlap: each calendar month appears in three consecutive windows.
  Do not sum adjacent seasons.
- Non-overlapping semester mapping: S1 = mean(`JFM`, `AMJ`);
  S2 = mean(`JAS`, `OND`).
- Use `anomaly` as the feature.

## Reference files

- `psgc_provinces.csv` - PSGC province and HUC records.
- `geoboundaries_provinces.csv` - geoBoundaries ADM2 names and centroids.
- `psgc_centroids.csv` - PSGC province matched to a geoBoundaries centroid.
- `province_reference.csv` - observed PSA province names mapped to PSGC codes
  and centroids. `psgc_match_method` is `exact`, `fuzzy:<score>`, or `none`.
  `centroid_match_method` is `psgc`, `geoboundaries:exact`,
  `geoboundaries:fuzzy:<score>`, `manual`, or `none`.
- `observed_provinces.json` - unique (region, province) pairs found in production.

## Known quirks (documented, deliberately not resolved)

1. Periods overlap: Q1+Q2 = S1, S1+S2 = Annual for production.
2. Area is not additive: Annual area equals S1, not S1+S2.
3. Farmgate has an `Annual` column; do not mix it with months.
4. HUC/city rows (level 3) nest under provinces; avoid double counting.
5. 2023: Davao City and Zamboanga City merged into their provinces per PSA notes.
6. BARMM regional total does not equal the sum of its provinces.
7. Negros Island Region duplicates Negros Occidental / Oriental / Siquijor;
   key on (region, province), not name.
8. `..` means missing; `0.00` means zero. Nulls are never filled with zero.
9. PSA revises history retroactively; use the committed snapshot.
10. The area table reports one measure per crop (planted or harvested). For
    pineapple it is likely planted area. Validate against PSA published yield.
11. Province names change over time (Davao de Oro, Cotabato).
12. Farmgate prices are sparse; count observed months before averaging.
13. PPA provincial GDP only covers 2018-2025.
"""
    write_text(docs / "data_dictionary.md", dictionary)

    lines = ["INGEST REPORT", f"generated_at_utc: {utc_now_iso()}", ""]
    lines.append("RAW FILES")
    for path in sorted(raw_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".csv", ".json", ".txt", ".geojson"}:
            facts = _file_facts(path)
            lines.append(
                f"  {facts['file']}  bytes={facts.get('bytes', 0):,}  "
                f"sha256={facts.get('sha256', 'missing')[:16]}..."
            )

    lines.append("")
    lines.append("NORMALIZED FILES")
    for path in sorted(norm_dir.glob("*.csv")):
        try:
            frame = pd.read_csv(path, dtype=str)
            nulls = int(frame.isna().sum().sum())
            lines.append(
                f"  {path.name}  rows={len(frame):,}  cols={len(frame.columns)}  "
                f"null_cells={nulls:,}"
            )
        except Exception as exc:  # noqa: BLE001
            lines.append(f"  {path.name}  ERROR reading: {exc}")

    ref_path = ref_dir / "province_reference.csv"
    if ref_path.exists():
        reference = pd.read_csv(ref_path, dtype=str)
        centroid_counts = reference["centroid_match_method"].value_counts(dropna=False).to_dict()
        psgc_counts = reference["psgc_match_method"].value_counts(dropna=False).to_dict()
        lines.append("")
        lines.append("PROVINCE REFERENCE")
        lines.append(f"  units={len(reference)}")
        lines.append(f"  centroid_match_method={centroid_counts}")
        lines.append(f"  psgc_match_method={psgc_counts}")
        unmatched = reference[reference["centroid_match_method"] == "none"]
        for _, row in unmatched.iterrows():
            lines.append(f"  NO CENTROID: {row['region_name']} / {row['province_name']}")

    write_text(docs / "ingest_report.txt", "\n".join(lines) + "\n")
    print(f"[docs] wrote {docs.relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Data acquisition and normalization pipeline")
    parser.add_argument(
        "steps",
        nargs="?",
        default="all",
        help="comma-separated steps: psa,normalize,geo,nasa,enso,docs or 'all'",
    )
    parser.add_argument("--refresh", action="store_true", help="force fresh downloads")
    parser.add_argument("--offline", action="store_true", help="use cached raw only")
    parser.add_argument("--only", default=None, help="alias for the steps argument")
    args = parser.parse_args()

    requested = args.only or args.steps
    steps = ALL_STEPS if requested == "all" else [s.strip() for s in requested.split(",")]

    unknown = [s for s in steps if s not in ALL_STEPS]
    if unknown:
        raise SystemExit(f"Unknown steps: {unknown}. Choose from {ALL_STEPS} or 'all'")

    cfg = load_config()
    ensure_dirs(cfg)

    observed: list[tuple[str, str]] | None = None

    if "psa" in steps:
        step_psa(cfg, args.refresh, args.offline)
    if "normalize" in steps:
        observed = step_normalize(cfg)
    if "geo" in steps:
        step_geo(cfg, args.refresh, args.offline, observed)
    if "nasa" in steps:
        step_nasa(cfg, args.refresh, args.offline)
    if "enso" in steps:
        step_enso(cfg, args.refresh, args.offline)
    if "docs" in steps:
        step_docs(cfg)

    print("done.")


if __name__ == "__main__":
    main()
