"""FastAPI service for pineapple yield prediction."""

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict

app = FastAPI(title="pineapple-yield-prediction")

_artifact = joblib.load("pineapple_yield_model.joblib")
_model = _artifact["model"]
_features = _artifact["features"]


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

    oni_anom_prev2: float
    allsky_sfc_sw_dwn_prev2: float
    prectotcorr_prev2: float
    rh2m_prev2: float
    t2m_prev2: float
    t2m_max_prev2: float
    t2m_min_prev2: float
    yield_prev2: float


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/predict")
def predict(f: Features) -> dict:
    row = pd.DataFrame([{name: getattr(f, name) for name in _features}])
    pred = float(np.expm1(_model.predict(row)[0]))
    return {"yield_mt_ha": round(pred, 2)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=9696)
