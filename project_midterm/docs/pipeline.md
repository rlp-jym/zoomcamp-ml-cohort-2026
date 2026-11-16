# Data pipeline

Acquisition and light normalization only. The notebook starts from
`data/normalized/` and `data/raw/`.

## Requirements

- Python 3.12+
- Install: `pip install -r requirements.txt`

The parent course environment already includes pandas and requests; add
`PyYAML` if it is missing.

## Commands

Run from `project_midterm/`:

```bash
py -m src.run all                 # full pipeline (uses cache where present)
py -m src.run --only psa          # download PSA tables only
py -m src.run --only normalize    # reshape raw -> normalized
py -m src.run --only geo          # PSGC + geoBoundaries + centroids
py -m src.run --only nasa         # weather (90 province points)
py -m src.run --only enso         # ONI
py -m src.run --only docs         # sources, dictionary, ingest report
py -m src.run all --refresh       # force fresh downloads
py -m src.run all --offline       # no network; fail if cache is missing
py -m src.verify                  # acceptance checks against the baseline
```

## What each stage produces

| Stage | Output |
|---|---|
| `psa` | `data/raw/psa/*.csv` + `*.metadata.json` + `provenance/*.json` |
| `normalize` | `data/normalized/psa_{production,area,farmgate,ppa}_long.csv` |
| `geo` | `data/reference/psgc_provinces.csv`, `geoboundaries_provinces.csv`, `psgc_centroids.csv`, `province_reference.csv` |
| `nasa` | `data/raw/nasa/*.json`, `data/normalized/nasa_weather_long.csv` |
| `enso` | `data/raw/noaa/oni.ascii.txt`, `data/normalized/noaa_enso_long.csv` |
| `docs` | `docs/sources.md`, `docs/data_dictionary.md`, `docs/ingest_report.txt` |

## Design rules

- Raw files are byte-exact and never edited.
- Normalization only reshapes and labels. It does not join, derive, drop,
  impute, or aggregate.
- Every download is cached. `--offline` must succeed from cache.
- PSA dimension codes are resolved from metadata at runtime, never hardcoded.
- PSA table paths live in `config.yaml`; if PSA renumbers a table, change one line.
- `..` becomes null; zeros stay zero; the original marker is kept in `value_raw`.
- NASA `YYYY13` (annual) rows are dropped to avoid double counting.
- Weather is monthly; aggregating to semester is the analyst's job.

## Troubleshooting

- **PSA returns 403**: expected on HTML pages. The API endpoints under
  `/PXWeb/api/v1/` are the only supported path.
- **PSA table missing**: the matrix ID may have changed. Search the current
  table list in OpenSTAT and update `config.yaml`.
- **NASA returns `-999.0`**: missing value; stored as null.
- **Province unmatched**: inspect `data/reference/province_reference.csv`,
  then extend `ALIASES_*` or `MANUAL_CENTROIDS` in `src/geo.py`.
- **Old snapshot**: run with `--refresh`. Revisions are expected; the
  committed raw snapshot is the pinned version used for the analysis.
