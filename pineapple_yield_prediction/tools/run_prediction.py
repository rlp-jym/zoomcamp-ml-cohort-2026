"""Interactive pineapple yield prediction.

Prompts for the 8 lag-2 features, validates the range, and prints a prediction.
Blank input uses the value from samples/sample_request.json.
"""

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

SPECS = [
    ("oni_anom_prev2", "ENSO anomaly", "ONI; negative = La Nina, positive = El Nino", -1.405, 2.090),
    ("allsky_sfc_sw_dwn_prev2", "Solar irradiance", "all-sky shortwave downward, MJ/m2/day", 14.363, 22.352),
    ("prectotcorr_prev2", "Precipitation", "total rainfall in the semester, mm", 284.490, 5306.000),
    ("rh2m_prev2", "Relative humidity", "mean relative humidity, %", 70.658, 91.102),
    ("t2m_prev2", "Mean temperature", "mean air temperature, C", 21.353, 28.667),
    ("t2m_max_prev2", "Max temperature", "mean daily maximum, C", 27.170, 36.470),
    ("t2m_min_prev2", "Min temperature", "mean daily minimum, C", 15.203, 25.963),
    ("yield_prev2", "Previous yield", "same semester last year, mt/ha", 0.023, 52.569),
]


def ask(name, label, desc, lo, hi, default):
    if desc:
        print(f"  {desc}")
    while True:
        raw = input(f"{label:<24} [{lo:.2f} .. {hi:.2f}]  ({default}): ").strip()
        if raw == "":
            return float(default)
        try:
            value = float(raw)
        except ValueError:
            print("  not a number, try again")
            continue
        if value < lo or value > hi:
            print(f"  out of range, expected {lo:.2f} .. {hi:.2f}")
            continue
        return value


def main() -> None:
    defaults = json.loads((BASE / "samples" / "sample_request.json").read_text())
    artifact = joblib.load(BASE / "model" / "pineapple_yield_model.joblib")
    model = artifact["model"]
    features = artifact["features"]

    print()
    print("Pineapple yield prediction")
    print("=" * 26)
    print("Enter the 8 lag-2 features. Blank = sample value.\n")

    values = {}
    for name, label, desc, lo, hi in SPECS:
        values[name] = ask(name, label, desc, lo, hi, defaults[name])

    row = {name: values[name] for name in features}
    pred = float(np.expm1(model.predict(pd.DataFrame([row]))[0]))

    prev = values["yield_prev2"]
    change = (pred / prev - 1) * 100
    alert = change <= -10

    print()
    print("Prediction")
    print("=" * 10)
    print(f"{'previous yield':<18} {prev:.2f} mt/ha")
    print(f"{'predicted yield':<18} {pred:.2f} mt/ha")
    print(f"{'change':<18} {change:+.1f}%")
    print(f"{'warning':<18} {'YES (>=10% drop)' if alert else 'no'}")


if __name__ == "__main__":
    main()
    try:
        input("\nPress Enter to close...")
    except EOFError:
        pass
