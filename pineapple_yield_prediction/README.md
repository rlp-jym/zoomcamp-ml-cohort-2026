# Pineapple Yield Forecasting (Midterm Project)

Province-semester yield (`mt/ha`) early-warning model for the Philippines, with a
SOCCSKSARGEN (Region 12) focus. Users: DA RFO XII and NEDA/DEPDev Region 12.

## Problem

Pineapple yield is volatile and interventions tend to be reactive. This model
predicts the next semester's yield about 12 months ahead, from lagged weather
(NASA POWER), ENSO (NOAA ONI), and the previous yield, so a low-yield semester
can be flagged before harvest. Metric: RMSE on `log1p(yield)` (reported as
`mt/ha` too).

## Data

Raw snapshots and provenance are in `data/raw/` and `provenance/`; normalized
tables used for analysis are in `data/normalized/`.

| Source | Content |
|---|---|
| PSA OpenSTAT | Fruit-crop production, area, farmgate prices |
| NASA POWER | Monthly weather by province centroid |
| NOAA CPC | Oceanic Nino Index (ENSO) |
| PSGC + geoBoundaries | Province codes and centroids |

Cleaned dataset: 658 province-semester rows, 28 provinces, 2010-2026.

## Data pipeline (optional - refresh only)

The normalized data is already committed, so reviewers can skip this. To refresh
from PSA/NASA/NOAA or check integrity:

```bash
pip install -r requirements.txt   # or: uv sync
py -m src.run all       # network; rebuilds data/normalized
py -m src.verify        # offline integrity check
```

Click-run: `run_notebook.bat` opens JupyterLab; `run_notebook.bat exec` runs the
notebook top-to-bottom.

## Click-run scripts

| Script | What it does |
|---|---|
| `run_notebook.bat` | Open JupyterLab (`run_notebook.bat exec` runs top-to-bottom) |
| `run_training.bat` | Train and save `model/pineapple_yield_model.joblib` |
| `run_prediction.bat` | Interactive prompt for the 8 features |
| `run_verification.bat` | PASS/FAIL check against `samples/sample_request.json` |
| `run_server_api.bat` | Start the FastAPI service on port 9696 |
| `run_docker.bat` | Build and run the Docker image |

## Notebook (`notebook.ipynb`)

Data prep, EDA, feature engineering, model selection/tuning, and the
early-warning and cost-of-late-intervention demos.

Features (lag 2 = one year): `oni_anom_prev2`, `allsky_sfc_sw_dwn_prev2`,
`prectotcorr_prev2`, `rh2m_prev2`, `t2m_prev2`, `t2m_max_prev2`,
`t2m_min_prev2`, `yield_prev2`. `area_ha` was dropped (no material effect).

Time split: train <= 2022 (513), validate 2023-24 (80), test >= 2025 (65).

| Model | Val RMSE | Test RMSE |
|---|---|---|
| Naive (`yield_prev2`) | 0.390 | 0.379 |
| LinearRegression | 0.500 | - |
| DecisionTree (depth 6) | 0.385 | - |
| RandomForest (depth 5) | 0.389 | - |
| XGBoost (depth 4) | 0.351 | 0.399 |

XGBoost is the final model (RMSE 4.18 mt/ha on test). `yield_prev2` dominates
feature importance (~0.8); lag-2 weather adds residual signal.

Early-warning demo: 13 of 65 provinces flagged (>=10% predicted drop),
~38,598 mt (~PHP 579 M) at risk at PHP 15/kg. Region 12 was stable (9 test
rows, 0 alerts). Alert precision is low (2 of 13 confirmed declines).

Forward projection: 2027 S1 watchlist has 3 of 22 provinces flagged.

## Train the model

```bash
python train.py        # or double-click run_training.bat
```
Writes `model/pineapple_yield_model.joblib`. Prints KPIs (rows, split sizes,
XGBoost vs baseline RMSE).

## Run the service

```bash
python predict.py      # or double-click run_server_api.bat
```

- Health: http://localhost:9696/health
- Swagger UI: http://localhost:9696/docs (example prefilled; click Try it out)
- Sample request: `samples/sample_request.json` -> expected `samples/sample_response.json`

Double-click `run_prediction.bat` for an interactive prompt, or
`run_verification.bat` for a PASS/FAIL check (no server needed).

## Docker

```bash
docker build -t pineapple-yield .
docker run -it -p 9696:9696 pineapple-yield
```

Or double-click `run_docker.bat`.

## Limitations

- Alert precision is low; the model is close to a persistence forecast.
- Sultan Kudarat is over-predicted in the test period.
- ~29% of test rows have yield < 5 mt/ha (PSA reporting quirks).
- 2027 S1 projection covers only 22 provinces with 2026 S1 data.
- No cloud deployment.

## Structure

```
README.md  notebook.ipynb  train.py  predict.py  requirements.txt  Dockerfile
run_notebook.bat  run_training.bat  run_prediction.bat  run_verification.bat  run_server_api.bat  run_docker.bat
data/  docs/  provenance/  src/  model/  samples/  tools/
```
