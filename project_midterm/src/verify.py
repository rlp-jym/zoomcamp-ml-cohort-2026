"""Acceptance checks for the data layer.

Run:  py -m src.verify

These checks verify acquisition integrity and the documented baseline.
They do not evaluate model quality or make cleaning decisions.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
NORM = ROOT / "data" / "normalized"
REF = ROOT / "data" / "reference"

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}{(': ' + detail) if detail else ''}")
    if not condition:
        failures.append(name)


def main() -> int:
    production = pd.read_csv(NORM / "production_long.csv")
    area = pd.read_csv(NORM / "area_long.csv")
    farmgate = pd.read_csv(NORM / "farmgate_long.csv")
    weather = pd.read_csv(NORM / "weather_long.csv")
    enso = pd.read_csv(NORM / "enso_long.csv")
    ppa = pd.read_csv(NORM / "ppa_long.csv")
    reference = pd.read_csv(REF / "province_reference.csv")

    # --- Baseline: South Cotabato 2023 -----------------------------------
    sc = production[(production["geo_name"] == "South Cotabato") & (production["year"] == 2023)]
    sc = sc.set_index("period")["value"]
    check("production S1 2023", abs(sc.get("Semester1", 0) - 394069.65) < 0.01, f"{sc.get('Semester1')}")
    check("production S2 2023", abs(sc.get("Semester2", 0) - 395934.55) < 0.01, f"{sc.get('Semester2')}")
    check("production Annual 2023", abs(sc.get("Annual", 0) - 790004.20) < 0.01, f"{sc.get('Annual')}")

    sca = area[(area["geo_name"] == "South Cotabato") & (area["year"] == 2023)].set_index("period")["value"]
    check("area S1 2023", abs(sca.get("Semester1", 0) - 23484.00) < 0.01, f"{sca.get('Semester1')}")
    check("area S2 2023", abs(sca.get("Semester2", 0) - 23400.00) < 0.01, f"{sca.get('Semester2')}")
    check("area Annual 2023", abs(sca.get("Annual", 0) - 23484.00) < 0.01, f"{sca.get('Annual')}")
    check(
        "area Annual is not S1+S2",
        abs(sca.get("Annual", 0) - (sca.get("Semester1", 0) + sca.get("Semester2", 0))) > 1,
        "stock measure preserved",
    )

    scf = farmgate[
        (farmgate["geo_name"] == "South Cotabato")
        & (farmgate["year"] == 2023)
        & (farmgate["commodity"] == "Pineapple Hawaiian")
    ].set_index("period")["value"]
    check("farmgate Jan 2023", abs(scf.get("January", 0) - 3.91) < 0.001, f"{scf.get('January')}")
    check("farmgate Dec 2023", abs(scf.get("December", 0) - 5.26) < 0.001, f"{scf.get('December')}")
    check("farmgate Annual 2023", abs(scf.get("Annual", 0) - 4.66) < 0.001, f"{scf.get('Annual')}")
    check("farmgate sparsity preserved", pd.isna(scf.get("July")) and pd.isna(scf.get("October")))

    # --- Key uniqueness ---------------------------------------------------
    for frame, name, keys in [
        (production, "production", ["geo_level", "region_name", "geo_name", "year", "period"]),
        (area, "area", ["geo_level", "region_name", "geo_name", "year", "period"]),
        (
            farmgate,
            "farmgate",
            ["geo_level", "region_name", "geo_name", "commodity", "year", "period"],
        ),
    ]:
        duplicates = int(frame.duplicated(subset=keys).sum())
        check(f"{name} key unique", duplicates == 0, f"duplicates={duplicates}")

    # --- Null vs zero -----------------------------------------------------
    check("production nulls preserved", int(production["value"].isna().sum()) > 0)
    check("area nulls preserved", int(area["value"].isna().sum()) > 0)
    check("no zero-filling in production", int((production["value"] == 0).sum()) == 0)
    check("value_raw preserves dots", (production["value_raw"] == "..").any())

    # --- Weather ----------------------------------------------------------
    scw = weather[(weather["province_name"] == "South Cotabato") & (weather["year"] == 2023)]
    check("weather 6 params x 12 months", len(scw) == 72, f"rows={len(scw)}")
    check("weather has no YYYY13 month", int((weather["month"] == 13).sum()) == 0)
    check(
        "weather parameters complete",
        set(scw["parameter"])
        == {
            "PRECTOTCORR",
            "T2M",
            "T2M_MAX",
            "T2M_MIN",
            "RH2M",
            "ALLSKY_SFC_SW_DWN",
        },
    )

    # --- ENSO -------------------------------------------------------------
    check("ENSO covers 2023", int((enso["year"] == 2023).sum()) == 12)
    check("ENSO has 2023 DJF", bool(((enso["year"] == 2023) & (enso["season"] == "DJF")).any()))

    # --- PPA --------------------------------------------------------------
    check("PPA preserved /s markers", bool((ppa["value_raw"] == "/s").any()))
    check("PPA /s is null in value", pd.isna(ppa.loc[ppa["value_raw"] == "/s", "value"]).all())

    # --- Reference --------------------------------------------------------
    check("province reference count", len(reference) >= 82, f"units={len(reference)}")
    check("all reference rows have centroids", reference["latitude"].notna().all())
    check("all reference rows have PSGC codes", reference["psgc_code"].notna().sum() >= 89)

    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s): {failures}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
