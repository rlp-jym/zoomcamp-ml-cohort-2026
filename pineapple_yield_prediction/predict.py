"""FastAPI service for pineapple yield prediction."""

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field

app = FastAPI(title="pineapple-yield-prediction")

BASE = Path(__file__).resolve().parent
_artifact = joblib.load(BASE / "model" / "pineapple_yield_model.joblib")
_model = _artifact["model"]
_features = _artifact["features"]

FIELDS = [
    ("oni_anom_prev2", "ENSO anomaly", "", -1.405, 2.090, 0.001, -0.13),
    ("allsky_sfc_sw_dwn_prev2", "Solar irradiance", "MJ/m2/day", 14.363, 22.352, 0.001, 17.055),
    ("prectotcorr_prev2", "Precipitation", "mm", 284.49, 5306.0, 0.01, 1470.21),
    ("rh2m_prev2", "Relative humidity", "%", 70.658, 91.102, 0.001, 86.73),
    ("t2m_prev2", "Mean temperature", "C", 21.353, 28.667, 0.001, 26.445),
    ("t2m_max_prev2", "Max temperature", "C", 27.170, 36.470, 0.001, 34.418),
    ("t2m_min_prev2", "Min temperature", "C", 15.203, 25.963, 0.001, 21.763),
    ("yield_prev2", "Previous yield", "mt/ha", 0.023, 52.569, 0.001, 3.94),
]


class Features(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "oni_anom_prev2": -0.13,
        "allsky_sfc_sw_dwn_prev2": 17.055,
        "prectotcorr_prev2": 1470.21,
        "rh2m_prev2": 86.73,
        "t2m_prev2": 26.445,
        "t2m_max_prev2": 34.418,
        "t2m_min_prev2": 21.763,
        "yield_prev2": 3.94,
    }})

    oni_anom_prev2: float = Field(title="ENSO anomaly", description="ONI; negative = La Nina, positive = El Nino")
    allsky_sfc_sw_dwn_prev2: float = Field(title="Solar irradiance", description="All-sky shortwave downward, MJ/m2/day")
    prectotcorr_prev2: float = Field(title="Precipitation", description="Total rainfall in the semester, mm")
    rh2m_prev2: float = Field(title="Relative humidity", description="Mean relative humidity, %")
    t2m_prev2: float = Field(title="Mean temperature", description="Mean air temperature, C")
    t2m_max_prev2: float = Field(title="Max temperature", description="Mean daily maximum, C")
    t2m_min_prev2: float = Field(title="Min temperature", description="Mean daily minimum, C")
    yield_prev2: float = Field(title="Previous yield", description="Same semester last year, mt/ha")


def _rows() -> str:
    out = []
    for name, label, unit, lo, hi, step, default in FIELDS:
        out.append(
            f'<label>{label} <span class="unit">{unit}</span>'
            f'<input type="range" id="{name}" min="{lo}" max="{hi}" step="{step}" value="{default}" '
            f'oninput="document.getElementById(\'{name}_v\').textContent=this.value">'
            f'<span id="{name}_v" class="val">{default}</span></label>'
        )
    return "\n".join(out)


HOME_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Pineapple Yield Prediction</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 460px; margin: 30px auto; }
  h1 { font-size: 1.15rem; }
  label { display: block; margin: 10px 0 2px; font-size: 0.9rem; }
  .unit { color: #666; font-size: 0.8rem; margin-left: 4px; }
  input[type=range] { width: 100%; }
  .val { float: right; font-variant-numeric: tabular-nums; }
  button { margin-top: 14px; padding: 8px 18px; }
  #result { margin-top: 16px; padding: 12px; background: #f4f4f4; border-radius: 6px; min-height: 3.5em; }
  table { width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 0.85rem; }
  th, td { padding: 4px 6px; text-align: left; border-bottom: 1px solid #ddd; }
  th { background: #eee; }
</style>
</head>
<body>
<h1>Pineapple Yield Prediction</h1>
""" + _rows() + """
<button onclick="predict()">Predict</button>
<div id="result"></div>
<h2>2027 S1 watchlist</h2>
<table id="wl"><thead><tr><th>Province</th><th>Prev</th><th>Pred</th><th>Change</th><th>At risk (mt)</th></tr></thead><tbody></tbody></table>
<script>
const fields = """ + str([f[0] for f in FIELDS]) + """;
async function predict() {
  const payload = {};
  for (const f of fields) payload[f] = parseFloat(document.getElementById(f).value);
  const r = await fetch("/predict", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(payload)});
  const d = await r.json();
  const change = (d.yield_mt_ha / payload.yield_prev2 - 1) * 100;
  document.getElementById("result").innerHTML =
    "Predicted yield: " + d.yield_mt_ha + " mt/ha<br>" +
    "Change: " + change.toFixed(1) + "%<br>" +
    "Warning: " + (change <= -10 ? "YES (>=10% drop)" : "none");
}
async function loadWatchlist() {
  const r = await fetch("/watchlist");
  const rows = await r.json();
  const tbody = document.querySelector("#wl tbody");
  tbody.innerHTML = rows.map(x =>
    "<tr><td>" + x.province + "</td><td>" + x.yield_prev2 + "</td><td>" + x.yield_pred + "</td><td>" + x.change_pct + "%</td><td>" + x.mt_at_risk + "</td></tr>"
  ).join("");
}
loadWatchlist();
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return HOME_HTML


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/predict")
def predict(f: Features) -> dict:
    row = pd.DataFrame([{name: getattr(f, name) for name in _features}])
    pred = float(np.expm1(_model.predict(row)[0]))
    return {"yield_mt_ha": round(pred, 2)}


@app.get("/watchlist")
def watchlist() -> list[dict]:
    path = BASE / "model" / "watchlist_features.csv"
    if not path.exists():
        return []
    df = pd.read_csv(path)
    preds = np.expm1(_model.predict(df[_features].fillna(0)))
    rows = []
    for i, r in df.iterrows():
        prev = float(r["yield_prev2"])
        pred = float(preds[i])
        change = (pred / prev - 1) * 100 if prev else 0.0
        rows.append({
            "region": str(r["region"]),
            "province": str(r["province"]),
            "yield_prev2": round(prev, 2),
            "yield_pred": round(pred, 2),
            "change_pct": round(change, 1),
            "mt_at_risk": round(float(r["area_ha"]) * max(0.0, prev - pred), 0),
            "alert": change <= -10,
        })
    rows.sort(key=lambda x: x["mt_at_risk"], reverse=True)
    return rows


if __name__ == "__main__":
    import threading
    import webbrowser

    import uvicorn

    threading.Timer(3.0, lambda: webbrowser.open("http://127.0.0.1:9696/", new=1)).start()
    uvicorn.run(app, host="127.0.0.1", port=9696)
