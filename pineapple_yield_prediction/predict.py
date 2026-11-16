"""FastAPI service for pineapple yield prediction."""

import joblib
import numpy as np
import pandas as pd
from pathlib import Path
from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

app = FastAPI(title="pineapple-yield-prediction")

BASE = Path(__file__).resolve().parent
_artifact = joblib.load(BASE / "model" / "pineapple_yield_model.joblib")
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

    oni_anom_prev2: float = Field(
        title="ENSO anomaly",
        description="ONI anomaly; negative = La Nina, positive = El Nino",
    )
    allsky_sfc_sw_dwn_prev2: float = Field(
        title="Solar irradiance",
        description="All-sky shortwave downward irradiance, MJ/m2/day",
    )
    prectotcorr_prev2: float = Field(
        title="Precipitation",
        description="Total rainfall in the semester, mm",
    )
    rh2m_prev2: float = Field(
        title="Relative humidity",
        description="Mean relative humidity, %",
    )
    t2m_prev2: float = Field(
        title="Mean temperature",
        description="Mean air temperature, C",
    )
    t2m_max_prev2: float = Field(
        title="Max temperature",
        description="Mean daily maximum, C",
    )
    t2m_min_prev2: float = Field(
        title="Min temperature",
        description="Mean daily minimum, C",
    )
    yield_prev2: float = Field(
        title="Previous yield",
        description="Same semester last year, mt/ha",
    )


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
