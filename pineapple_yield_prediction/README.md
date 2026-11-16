# Pineapple Yield Prediction

Province-semester yield (`mt/ha`) early-warning model for the Philippines.

Users: regional planning offices.

## Problem

Pineapple production in the Philippines varies at the province-semester level.
The objective is to develop an early-warning system so that government
intervention can be performed in a timely manner, ultimately benefiting farmers.

## Solution

A model that generates expectations about future yield (`mt/ha`) to guide
decision-making by regional planning offices. It flags a likely low-yield
semester (a drop of at least 5%) about 12 months ahead, using lagged weather,
ENSO, and yield momentum.

Models compared: `LinearRegression`, `DecisionTree`, `RandomForest`, `XGBoost`.
Primary evaluation: RMSE on `log1p(yield)`. For the warning decision, precision,
recall, and F2 (recall-weighted) are reported. F2 is the selection metric because
a missed drop is more costly than a false alarm.

## Data

Raw snapshots and provenance are in `data/raw/` and `provenance/`; normalized
tables used for analysis are in `data/normalized/`. The data collection pipeline
was built using AI, as this is not the main focus of the course.

| Source | Content |
|---|---|
| PSA OpenSTAT | production, area, farmgate prices |
| NASA POWER | monthly weather by province |
| NOAA CPC | Oceanic Nino Index (ENSO) |
| PSGC + geoBoundaries | province codes and centroids |

Cleaned dataset: 28 provinces, 2010-2026, 658 province-semester rows.

## Data pipeline (optional - refresh only)

The normalized data is already committed, so reviewers can skip this. To refresh
from PSA/NASA/NOAA or check integrity:

```bash
pip install -r requirements.txt   # or: uv sync
py -m src.run all                 # network; rebuilds data/normalized
py -m src.verify                  # offline integrity check
```

## Quality-of-life scripts

| Script | What it does |
|---|---|
| `run_docker.bat` | Build and run the Docker image |
| `run_server_api.bat` | Start the FastAPI service on port 9696 |
| `run_notebook.bat` | Open JupyterLab (`run_notebook.bat exec` runs top-to-bottom) |
| `run_training.bat` | Train and save `model/pineapple_yield_model.joblib` |
| `run_verification.bat` | PASS/FAIL check against `samples/sample_request.json` |

## Notebook (`notebook.ipynb`)

Data prep, EDA, feature engineering, model selection/tuning, and the
early-warning and cost-of-late-intervention demos.

Features (lag 2 = one year cycle):

- `oni_anom_prev2`
- `allsky_sfc_sw_dwn_prev2`
- `prectotcorr_prev2`
- `rh2m_prev2`
- `t2m_prev2`
- `t2m_max_prev2`
- `t2m_min_prev2`
- `yield_prev2`

Data split:

- train <= 2022 (513)
- validate 2023-24 (80)
- test >= 2025 (65)

| Model | Val RMSE | Test RMSE |
|---|---|---|
| Seasonal persistence (`yield_prev2`, same semester last year) | 0.390 | 0.379 |
| LinearRegression | 0.500 | - |
| DecisionTree (depth 6) | 0.385 | 0.424 (3.51 mt/ha) |
| RandomForest (depth 5) | 0.389 | - |
| XGBoost (depth 4) | 0.351 | 0.399 (4.18 mt/ha) |

**Final model: DecisionTree.** XGBoost had the best RMSE, but DecisionTree had
the best alert F2 on validation (0.49) and is the model used for the warning
decision. On test, its alert F2 is 0.28 (precision 0.38, recall 0.26).

`yield_prev2` dominates feature importance (~0.97 for the tree); lag-2 weather
adds little.

Early-warning demo (DecisionTree, -5% threshold, test):

- 16 of 65 provinces flagged; 6 confirmed declines
- precision 0.38, recall 0.26, F2 0.28
- ~91,925 mt (~PHP 1.38 B) at risk at PHP 15/kg
- Region 12: 1 test alert (South Cotabato); 0 in the 2027 S1 projection
- Forward projection: 2027 S1 watchlist flags 6 of 22 provinces

## Train the model

```bash
python train.py        # or double-click run_training.bat
```

Writes `model/pineapple_yield_model.joblib`. Prints KPIs (rows, split sizes,
DecisionTree vs baseline RMSE).

## Run the service

```bash
python predict.py      # or double-click run_server_api.bat
```

- Health: http://localhost:9696/health
- Browser form: http://localhost:9696/ (sliders + scenario watchlist)
- Swagger UI: http://localhost:9696/docs
- Sample request: `samples/sample_request.json` -> `samples/sample_response.json`

The browser form applies the selected weather/ENSO values to all provinces;
previous yield and area remain province-specific. Double-click
`run_verification.bat` for a PASS/FAIL check (no server needed).

## Docker

```bash
docker build -t pineapple-yield .
docker run -it -p 9696:9696 pineapple-yield
```

Or double-click `run_docker.bat`.

## Limitations

- Test precision/recall (0.38 / 0.26) are lower than validation (0.58 / 0.47);
  the test set has only 65 rows.
- The dataset is small after cleaning, and the model relies heavily on
  `yield_prev2`; weather features add little.
- Seasonal persistence has better log RMSE (0.379 vs 0.424), though the tree is
  slightly better in mt/ha (3.51 vs 3.58).
- ~29% of test rows have yield < 5 mt/ha (PSA reporting quirks).
- The 2027 S1 projection covers only the 22 provinces with 2026 S1 data.
- No cloud deployment.

Next steps: more province-semester history, additional features (irrigation,
fertilizer, disease), and a larger test period.

## Structure

```
data/
docs/
provenance/
src/
model/
samples/
tools/
README.md
notebook.ipynb
train.py
predict.py
requirements.txt
Dockerfile
run_notebook.bat
run_training.bat
run_verification.bat
run_server_api.bat
run_docker.bat
```
