"""FastAPI service for pineapple yield prediction."""

import threading
import webbrowser
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

app = FastAPI(title="pineapple-yield-prediction")

BASE = Path(__file__).resolve().parent
_artifact = joblib.load(BASE / "model" / "pineapple_yield_model.joblib")
_model = _artifact["model"]
_features = _artifact["features"]

FIELDS = [
    ("oni_anom_prev2", "ENSO anomaly", "ONI; negative = La Nina, positive = El Nino", -1.405, 2.090, 0.001, -0.13),
    ("allsky_sfc_sw_dwn_prev2", "Solar irradiance", "all-sky shortwave downward, MJ/m2/day", 14.363, 22.352, 0.001, 17.055),
    ("prectotcorr_prev2", "Precipitation", "total rainfall in the semester, mm", 284.49, 5306.0, 0.01, 1470.21),
    ("rh2m_prev2", "Relative humidity", "mean relative humidity, %", 70.658, 91.102, 0.001, 86.73),
    ("t2m_prev2", "Mean temperature", "mean air temperature, C", 21.353, 28.667, 0.001, 26.445),
    ("t2m_max_prev2", "Max temperature", "mean daily maximum, C", 27.170, 36.470, 0.001, 34.418),
    ("t2m_min_prev2", "Min temperature", "mean daily minimum, C", 15.203, 25.963, 0.001, 21.763),
    ("yield_prev2", "Previous yield", "same semester last year, mt/ha", 0.023, 52.569, 0.001, 3.94),
]

SCENARIO_FIELDS = [f for f in FIELDS if f[0] != "yield_prev2"]
FIELD_DESC = {f[0]: f[2] for f in FIELDS}


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


class Scenario(BaseModel):
    oni_anom_prev2: float
    allsky_sfc_sw_dwn_prev2: float
    prectotcorr_prev2: float
    rh2m_prev2: float
    t2m_prev2: float
    t2m_max_prev2: float
    t2m_min_prev2: float


def _rows() -> str:
    out = []
    for name, label, unit, lo, hi, step, default in SCENARIO_FIELDS:
        out.append(
            f'<label>{label} <span class="unit">{unit}</span>'
            f'<input type="range" id="{name}" title="{FIELD_DESC[name]}" min="{lo}" max="{hi}" step="{step}" value="{default}" '
            f'oninput="document.getElementById(\'{name}_v\').textContent=this.value">'
            f'<span id="{name}_v" class="val">{default}</span></label>'
        )
    return "\n".join(out)


HOME_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Pineapple Yield Scenario</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 640px; margin: 30px auto; }
  h1 { font-size: 1.15rem; }
  h2 { font-size: 1rem; margin-top: 20px; }
  label { display: block; margin: 10px 0 2px; font-size: 0.9rem; }
  .unit { color: #666; font-size: 0.8rem; margin-left: 4px; }
  input[type=range] { width: 100%; }
  .val { float: right; font-variant-numeric: tabular-nums; }
  button { margin-top: 14px; padding: 8px 18px; }
  .caveat { color: #666; font-size: 0.8rem; margin: 6px 0 0; }
  #summary { margin-top: 16px; padding: 10px; background: #f4f4f4; border-radius: 6px; }
  table { width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 0.8rem; }
  th, td { padding: 4px 6px; text-align: left; border-bottom: 1px solid #ddd; }
  th { background: #eee; }
  .num { text-align: center; font-variant-numeric: tabular-nums; }
  tbody tr:nth-child(even) { background: #f7f7f7; }
  tbody tr:hover { background: #eef4ff; }
</style>
</head>
<body>
<h1>Pineapple Yield Scenario (2027 S1)</h1>
<p class="caveat">Scenario applies the same weather/ENSO values to every province.
Previous yield and area remain province-specific.</p>
""" + _rows() + """
<button onclick="runScenario()">Update scenario</button>
<div id="summary"></div>
<h2>2027 S1 watchlist (mt at risk)</h2>
<table id="wl"><thead><tr><th>Province</th><th class="num">Prev</th><th class="num">Pred</th><th class="num">Change</th><th class="num">At risk (mt)</th><th class="num">PHP at risk</th></tr></thead><tbody></tbody></table>
<script>
const fields = """ + str([f[0] for f in SCENARIO_FIELDS]) + """;
let rowsData = [];
async function loadWatchlist() {
  const r = await fetch("/watchlist");
  rowsData = await r.json();
  renderTable();
  summarize("Baseline (2027 S1 projection)");
}
function fmt(n, d) {
  return Number(n).toLocaleString(undefined, {minimumFractionDigits: d, maximumFractionDigits: d});
}
function renderTable() {
  const tbody = document.querySelector("#wl tbody");
  tbody.innerHTML = rowsData.map(x =>
    "<tr><td>" + x.province + "</td>" +
    '<td class="num">' + fmt(x.yield_prev2, 2) + "</td>" +
    '<td class="num">' + fmt(x.yield_pred, 2) + "</td>" +
    '<td class="num">' + fmt(x.change_pct, 1) + "%</td>" +
    '<td class="num">' + fmt(x.mt_at_risk, 0) + "</td>" +
    '<td class="num">' + fmt(x.php_at_risk, 0) + "</td></tr>"
  ).join("");
}
function summarize(label) {
  const mt = rowsData.reduce((a, x) => a + x.mt_at_risk, 0);
  const php = rowsData.reduce((a, x) => a + x.php_at_risk, 0);
  document.getElementById("summary").innerHTML =
    "<b>" + label + "</b><br>provinces at risk: " + rowsData.length +
    "<br>total mt at risk: " + fmt(mt, 0) +
    "<br>total PHP at risk: " + fmt(php, 0);
}
async function runScenario() {
  const payload = {};
  for (const f of fields) payload[f] = parseFloat(document.getElementById(f).value);
  const r = await fetch("/scenario", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(payload)});
  rowsData = await r.json();
  renderTable();
  summarize("Scenario");
}
loadWatchlist();
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    return HTMLResponse(HOME_HTML, headers={"Cache-Control": "no-store"})


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/predict")
def predict(f: Features) -> dict:
    row = pd.DataFrame([{name: getattr(f, name) for name in _features}])
    pred = float(np.expm1(_model.predict(row)[0]))
    return {"yield_mt_ha": round(pred, 2)}


def _risk_rows(df: pd.DataFrame) -> list[dict]:
    preds = np.expm1(_model.predict(df[_features].fillna(0)))
    rows = []
    for i, r in df.iterrows():
        prev = float(r["yield_prev2"])
        pred = float(preds[i])
        change = (pred / prev - 1) * 100 if prev else 0.0
        mt = float(r["area_ha"]) * max(0.0, prev - pred)
        if mt <= 0:
            continue
        rows.append({
            "region": str(r["region"]),
            "province": str(r["province"]).replace("_", " ").title(),
            "area_ha": round(float(r["area_ha"]), 0),
            "yield_prev2": round(prev, 2),
            "yield_pred": round(pred, 2),
            "change_pct": round(change, 1),
            "mt_at_risk": round(mt, 0),
            "php_at_risk": round(mt * 1000 * 15.0, 0),
            "alert": change <= -10,
        })
    rows.sort(key=lambda x: x["mt_at_risk"], reverse=True)
    return rows


@app.get("/watchlist")
def watchlist() -> list[dict]:
    path = BASE / "model" / "watchlist_features.csv"
    if not path.exists():
        return []
    return _risk_rows(pd.read_csv(path))


@app.post("/scenario")
def scenario(s: Scenario) -> list[dict]:
    path = BASE / "model" / "watchlist_features.csv"
    if not path.exists():
        return []
    df = pd.read_csv(path)
    for name in [f[0] for f in SCENARIO_FIELDS]:
        df[name] = getattr(s, name)
    return _risk_rows(df)


if __name__ == "__main__":
    threading.Timer(3.0, lambda: webbrowser.open("http://127.0.0.1:9696/", new=1)).start()
    uvicorn.run(app, host="127.0.0.1", port=9696)
