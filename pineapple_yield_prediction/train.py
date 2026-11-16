"""Train the final pineapple yield model and save the artifact."""

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.impute import SimpleImputer
from sklearn.metrics import root_mean_squared_error
from sklearn.pipeline import Pipeline

BASE = Path(__file__).resolve().parent
DATA = BASE / "data" / "normalized"

FINAL_FEATS = [
    "oni_anom_prev2",
    "allsky_sfc_sw_dwn_prev2",
    "prectotcorr_prev2",
    "rh2m_prev2",
    "t2m_prev2",
    "t2m_max_prev2",
    "t2m_min_prev2",
    "yield_prev2",
]


def build_features() -> pd.DataFrame:
    psa_area_data = pd.read_csv(DATA / "psa_area_long.csv")
    psa_prod_data = pd.read_csv(DATA / "psa_production_long.csv")
    noaa_enso_data = pd.read_csv(DATA / "noaa_enso_long.csv")
    nasa_weather_data = pd.read_csv(DATA / "nasa_weather_long.csv")

    area_prod_cols = [
        "crop", "geo_level_name", "region_name", "province_name",
        "year", "period_type", "period", "value",
    ]
    psa_area = psa_area_data[area_prod_cols]
    psa_prod = psa_prod_data[area_prod_cols]
    psa = psa_area.rename(columns={"value": "area_ha"}).merge(
        psa_prod.rename(columns={"value": "prod_mt"}),
        on=["crop", "geo_level_name", "region_name", "province_name",
            "year", "period_type", "period"],
        how="left", validate="one_to_one",
    )

    for c in psa_area.select_dtypes(include="str").columns:
        psa[c] = psa[c].str.lower().str.replace(" ", "_")

    psa = psa.rename(columns={
        "geo_level_name": "level",
        "region_name": "region",
        "province_name": "province",
    })
    psa["yield"] = psa["prod_mt"] / psa["area_ha"]

    psa = psa[(psa["yield"].notna()) & (psa["yield"] > 0)]
    psa = psa[(psa["level"] == "province") & (psa["period_type"] == "semester")].reset_index(drop=True)
    psa = psa[psa["yield"] < 100]
    psa = psa[psa["area_ha"] >= 100].reset_index(drop=True)

    psa = psa.sort_values(["region", "province", "year", "period"])
    for k in range(1, 5):
        psa[f"yield_prev{k}"] = psa.groupby(["region", "province"])["yield"].shift(k)

    # NOAA ONI -> semestral
    noaa = noaa_enso_data[noaa_enso_data["season"].isin(["JFM", "AMJ", "JAS", "OND"])].copy()
    semester = {"JFM": "semester1", "AMJ": "semester1", "JAS": "semester2", "OND": "semester2"}
    noaa["period"] = noaa["season"].map(semester)
    noaa = (
        noaa.dropna(subset=["period"])
        .groupby(["year", "period"], as_index=False)
        .agg(oni_anom=("anomaly", "mean"), n_seasons=("season", "size"))
    )
    noaa.loc[noaa["n_seasons"] < 2, "oni_anom"] = pd.NA
    noaa = noaa.drop(columns="n_seasons")
    noaa = noaa.sort_values(["year", "period"]).reset_index(drop=True)
    noaa = noaa.rename(columns={"oni_anom": "oni_anom_sem"})
    for k in range(1, 5):
        noaa[f"oni_anom_prev{k}"] = noaa["oni_anom_sem"].shift(k)
    noaa = noaa[noaa["year"] >= 2010]

    psa_noaa = psa.merge(noaa, on=["year", "period"], how="left", validate="many_to_one")

    # NASA POWER -> semestral
    nasa = nasa_weather_data.copy()
    for c in nasa.select_dtypes(include="str").columns:
        nasa[c] = nasa[c].str.lower().str.replace(" ", "_")

    nasa["period"] = nasa["month"].le(6).map({True: "semester1", False: "semester2"})
    nasa["days_in_month"] = pd.to_datetime(nasa[["year", "month"]].assign(day=1)).dt.days_in_month
    nasa["value_total"] = nasa["value"] * nasa["days_in_month"]

    nasa_sem = (
        nasa.groupby(["region_name", "province_name", "year", "period", "parameter", "unit"], as_index=False)
        .agg(value=("value", "mean"), value_total=("value_total", "sum"))
        .rename(columns={"region_name": "region", "province_name": "province"})
    )
    precip = nasa_sem["parameter"].eq("prectotcorr")
    nasa_sem.loc[precip, "value"] = nasa_sem.loc[precip, "value_total"].where(
        nasa_sem.loc[precip, "value"].notna()
    )
    nasa_sem.loc[precip, "unit"] = "mm"
    nasa_sem = nasa_sem.drop(columns="value_total")

    nasa_wide0 = nasa_sem.pivot(
        index=["region", "province", "year", "period"], columns="parameter", values="value"
    ).reset_index()
    param_cols = [c for c in nasa_wide0.columns if c not in ["region", "province", "year", "period"]]

    def make_lag(df, k):
        out = df.copy()
        idx = out["year"].to_numpy() * 2 + out["period"].eq("semester2").to_numpy().astype(int)
        tidx = idx + k
        out["year"] = tidx // 2
        out["period"] = np.where(tidx % 2 == 0, "semester1", "semester2")
        out = out.rename(columns={c: f"{c}_prev{k}" for c in param_cols})
        return out[["region", "province", "year", "period"] + [f"{c}_prev{k}" for c in param_cols]]

    psa_noaa_nasa = psa_noaa.copy()
    for k in range(1, 5):
        lagged = make_lag(nasa_wide0, k)
        psa_noaa_nasa = psa_noaa_nasa.merge(
            lagged, on=["region", "province", "year", "period"],
            how="left", validate="many_to_one",
        )

    df = psa_noaa_nasa[psa_noaa_nasa["yield_prev2"].notna()].copy()
    df = df.sort_values(["year", "period", "region", "province"]).reset_index(drop=True)
    return df


def main() -> None:
    df = build_features()

    train = df[df["year"] <= 2022]
    val = df[df["year"].isin([2023, 2024])]
    test = df[df["year"] >= 2025]

    # honest holdout metric on a throwaway model
    holdout = Pipeline([
        ("impute", SimpleImputer(strategy="constant", fill_value=0)),
        ("xgb", xgb.XGBRegressor(
            n_estimators=110, max_depth=4, min_child_weight=50,
            learning_rate=0.05, random_state=9,
        )),
    ])
    holdout.fit(
        pd.concat([train[FINAL_FEATS], val[FINAL_FEATS]]),
        np.log1p(pd.concat([train["yield"], val["yield"]])),
    )
    pred_log = holdout.predict(test[FINAL_FEATS])
    rmse_log = root_mean_squared_error(np.log1p(test["yield"]), pred_log)
    rmse_mt = root_mean_squared_error(test["yield"], np.expm1(pred_log))
    base_log = root_mean_squared_error(np.log1p(test["yield"]), np.log1p(test["yield_prev2"]))

    # final model uses every row
    model = Pipeline([
        ("impute", SimpleImputer(strategy="constant", fill_value=0)),
        ("xgb", xgb.XGBRegressor(
            n_estimators=110, max_depth=4, min_child_weight=50,
            learning_rate=0.05, random_state=9,
        )),
    ])
    model.fit(df[FINAL_FEATS], np.log1p(df["yield"]))

    artifact = {"model": model, "features": FINAL_FEATS}
    out = BASE / "pineapple_yield_model.joblib"
    joblib.dump(artifact, out)

    print()
    print("Pineapple yield model")
    print("=" * 24)
    print(f"{'rows':<18} {len(df)}")
    print(f"{'features':<18} {len(FINAL_FEATS)}")
    print(f"{'train / val / test':<18} {len(train)} / {len(val)} / {len(test)}")
    print()
    print(f"{'holdout RMSE':<18} {rmse_log:.3f}  (log1p)")
    print(f"{'holdout RMSE':<18} {rmse_mt:.2f}   mt/ha")
    print(f"{'baseline RMSE':<18} {base_log:.3f}  (log1p, yield_prev2)")
    print()
    print(f"{'saved':<18} pineapple_yield_prediction/{out.name}")


if __name__ == "__main__":
    main()
