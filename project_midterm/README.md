# Pineapple Yield Forecasting (Midterm Project)

Province-level early-warning model for pineapple yield in the Philippines,
with a South Cotabato focus. Intended users: DA Regional Field Office XII
and NEDA / DEPDev Region 12.

> Status: data pipeline complete. EDA, modeling, deployment, and the full
> project README are in progress.

## Data

- **PSA OpenSTAT** - fruit-crop production, area, farmgate prices, provincial GDP
- **NASA POWER** - monthly weather by province centroid
- **NOAA CPC** - Oceanic Nino Index (ENSO)
- **PSGC + geoBoundaries** - province codes and centroids

Raw snapshots and provenance are committed under `data/raw/` and `provenance/`.
Normalized tables for analysis are in `data/normalized/`.

## Run the data pipeline

```bash
pip install -r requirements.txt
py -m src.run all
py -m src.verify
```

See `docs/pipeline.md`, `docs/sources.md`, and `docs/data_dictionary.md`.

## Not yet included

`notebook.ipynb`, `train.py`, `predict.py`, `serve.py`, `Dockerfile`,
deployment, and the full submission README.
