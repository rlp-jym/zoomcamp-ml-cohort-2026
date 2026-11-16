# Pineapple Yield Forecasting (Midterm Project)

Province-semester level early-warning model for pineapple yield (`mt/ha`) in the
Philippines, with a SOCCSKSARGEN (Region 12) focus. Intended users: DA Regional
Field Office XII and NEDA/DEPDev Region 12, for monitoring, early intervention,
and investment targeting in agro-industrial value chains.

## Problem

Pineapple production in SOCCSKSARGEN is volatile and interventions tend to be
reactive. This project predicts the next semester's yield about 12 months ahead,
from lagged weather (NASA POWER), ENSO (NOAA ONI), and the previous yield, so
that a low-yield semester can be flagged before harvest. Reported metric is
RMSE on `log1p(yield)`; the deployed model also reports RMSE in `mt/ha`.

## Data

Raw snapshots and provenance are committed under `data/raw/` and `provenance/`;
normalized tables used for analysis are in `data/normalized/`.

| Source | Content |
|---|---|
| PSA OpenSTAT | Fruit-crop production, area, farmgate prices |
| NASA POWER | Monthly weather by province centroid |
| NOAA CPC | Oceanic Nino Index (ENSO) |
| PSGC + geoBoundaries | Province codes and centroids |

Dataset: 658 province-semester rows after cleaning (>= 500 required), 28
provinces, 2010-2026.

## Run the data pipeline

```bash
pip install -r requirements.txt   # or: uv sync
py -m src.run all
py -m src.verify
```

Or, with uv, open the notebook:

```bash
.\run.bat          # JupyterLab on the project venv
.\run.bat exec     # run the notebook top-to-bottom
```

## Notebook

`notebook.ipynb` contains data preparation, EDA, feature engineering, model
selection and tuning, and the early-warning / cost-of-late-intervention demos.

Feature set (lag 2 = one year):
`oni_anom_prev2`, `allsky_sfc_sw_dwn_prev2`, `prectotcorr_prev2`,
`rh2m_prev2`, `t2m_prev2`, `t2m_max_prev2`, `t2m_min_prev2`, `yield_prev2`.

Time-based split: train <= 2022, validate 2023-24, test >= 2025.

| Model | Val RMSE | Test RMSE |
|---|---|---|
| Naive (`yield_prev2`) | 0.390 | 0.379 |
| LinearRegression | 0.500 | - |
| DecisionTree (depth 6) | 0.385 | - |
| RandomForest (depth 5) | 0.389 | - |
| XGBoost (depth 4) | 0.351 | 0.399 |

XGBoost is the final model. `yield_prev2` dominates feature importance (~0.8);
lag-2 weather adds residual signal; `area_ha` had no material effect and was
dropped. Test RMSE = 4.18 mt/ha.

Early-warning demo (test period): 13 of 65 provinces flagged (>=10% predicted
drop), ~38,598 mt (~PHP 579 M) at risk at a blended farmgate price of PHP 15/kg.
Region 12 was stable: 9 test rows, 0 alerts. Alert precision is low (2 of 13
confirmed declines) - acceptable for an early-warning system, but noted.

## Train the model

```bash
python train.py        # writes pineapple_yield_model.joblib
```

## Run the service

```bash
uv run uvicorn app:app --reload --port 9696
```

Health check:

```bash
curl http://localhost:9696/health
```

Prediction (8 lagged features -> mt/ha):

```bash
curl -X POST http://localhost:9696/predict \
  -H "Content-Type: application/json" \
  -d '{"oni_anom_prev2":-0.13,"allsky_sfc_sw_dwn_prev2":17.055,"prectotcorr_prev2":1470.21,"rh2m_prev2":86.73,"t2m_prev2":26.445,"t2m_max_prev2":34.418,"t2m_min_prev2":21.763,"yield_prev2":3.94}'
```

## Docker

```bash
docker build -t pineapple-yield .
docker run -it -p 9696:9696 pineapple-yield
```

## Limitations

- Alert precision is low; the model is close to a persistence forecast.
- Sultan Kudarat is over-predicted in the test period (predicted ~8 vs actual ~4 mt/ha).
- ~29% of test rows have yield < 5 mt/ha, which look like PSA reporting quirks
  and inflate percentage-based metrics.
- The forward projection (2027 S1) covers only the 22 provinces with 2026 S1
  data and reuses 2026 S1 area as an exposure proxy.
- No cloud deployment.
