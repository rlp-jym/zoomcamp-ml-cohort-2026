# Data dictionary

## Layers

- `data/raw/` - byte-exact downloads. Never edited.
- `data/normalized/` - light reshaping only. No joins, no derived measures, no row drops.
- `data/reference/` - crosswalks and centroids used to key the data.

## Normalized files

### psa_production_long.csv
Pineapple volume of production.

| Column | Meaning |
|---|---|
| `source_table` | logical source name (`production`) |
| `crop` | PSA crop label |
| `geo_level` | 0 national, 1 region, 2 province or independent city, 3 city/HUC nested under a province |
| `geo_level_name` | label for the level |
| `region_name` | carried region context |
| `province_name` | carried province context |
| `geo_name` | geography label with dots removed |
| `year` | calendar year |
| `period` | source period label (`Quarter1`, `Semester1`, `Annual`, ...) |
| `period_type` | `quarter`, `semester`, `annual`, `month` |
| `period_num` | quarter/semester/month number; 0 for annual |
| `value_raw` | original source string (`..`, `/s`, number) |
| `value` | metric tons; null for `..` and other non-numeric markers |

### psa_area_long.csv
Same schema as production; `value` is hectares. Quarterly cells are mostly
null for pineapple; semester values are populated.

### psa_farmgate_long.csv
Same schema plus `commodity`; `value` is pesos per kilogram.

### psa_ppa_long.csv
Same schema plus `sector` and `type_of_valuation`; `value` is thousand pesos.
No region/province carry-forward: PPA geographies use a different label shape.

### nasa_weather_long.csv

| Column | Meaning |
|---|---|
| `region_name`, `province_name` | key matching the PSA normalized tables |
| `year`, `month` | calendar month |
| `parameter` | NASA POWER parameter code |
| `unit` | source unit |
| `value` | null when NASA returns -999.0 |

Parameter descriptions:

| Parameter | Unit | Description |
|---|---|---|
| `PRECTOTCORR` | mm/day | Bias-corrected precipitation rate. Monthly total = value x days in month; semester total = sum of monthly totals. |
| `T2M` | deg C | Mean air temperature at 2 m. |
| `T2M_MAX` | deg C | Mean daily maximum temperature at 2 m. |
| `T2M_MIN` | deg C | Mean daily minimum temperature at 2 m. |
| `RH2M` | % | Relative humidity at 2 m. |
| `ALLSKY_SFC_SW_DWN` | MJ/m2/day | All-sky surface shortwave downward irradiance (solar energy). |

Notes:

- Values are monthly means for the NASA POWER grid cell nearest the province centroid.
- `PRECTOTCORR` is a rate: multiply by days in month before summing.
- Temperature, humidity and solar are averaged over the semester.
- `-999.0` is the missing-value fill and is stored as null.
- The `YYYY13` annual row is dropped to avoid double counting.

### noaa_enso_long.csv

| Column | Meaning |
|---|---|
| `season` | 3-month window: `DJF`, `JFM`, `FMA`, ..., `NDJ` |
| `year` | year of the middle month of the window |
| `total` | absolute 3-month mean sea-surface temperature, deg C |
| `anomaly` | departure from the climatological normal, deg C |

Definitions:

- ONI: 3-month running mean of SST anomalies in the Nino 3.4 region
  (5N-5S, 120W-170W), ERSSTv5.
- Base period: centered 30-year climatology updated every five years;
  current base 1991-2020.
- El Nino: `anomaly >= +0.5 deg C` for five consecutive overlapping seasons.
- La Nina: `anomaly <= -0.5 deg C` for five consecutive overlapping seasons.
- Neutral: between -0.5 and +0.5 deg C.
- Magnitude: +/-0.5 weak, +/-1.0 moderate, +/-1.5 strong, +/-2.0 very strong.
- Seasons overlap: each calendar month appears in three consecutive windows.
  Do not sum adjacent seasons.
- Non-overlapping semester mapping: S1 = mean(`JFM`, `AMJ`);
  S2 = mean(`JAS`, `OND`).
- Use `anomaly` as the feature.

## Reference files

- `psgc_provinces.csv` - PSGC province and HUC records.
- `geoboundaries_provinces.csv` - geoBoundaries ADM2 names and centroids.
- `psgc_centroids.csv` - PSGC province matched to a geoBoundaries centroid.
- `province_reference.csv` - observed PSA province names mapped to PSGC codes
  and centroids. `psgc_match_method` is `exact`, `fuzzy:<score>`, or `none`.
  `centroid_match_method` is `psgc`, `geoboundaries:exact`,
  `geoboundaries:fuzzy:<score>`, `manual`, or `none`.
- `observed_provinces.json` - unique (region, province) pairs found in production.

## Known quirks (documented, deliberately not resolved)

1. Periods overlap: Q1+Q2 = S1, S1+S2 = Annual for production.
2. Area is not additive: Annual area equals S1, not S1+S2.
3. Farmgate has an `Annual` column; do not mix it with months.
4. HUC/city rows (level 3) nest under provinces; avoid double counting.
5. 2023: Davao City and Zamboanga City merged into their provinces per PSA notes.
6. BARMM regional total does not equal the sum of its provinces.
7. Negros Island Region duplicates Negros Occidental / Oriental / Siquijor;
   key on (region, province), not name.
8. `..` means missing; `0.00` means zero. Nulls are never filled with zero.
9. PSA revises history retroactively; use the committed snapshot.
10. The area table reports one measure per crop (planted or harvested). For
    pineapple it is likely planted area. Validate against PSA published yield.
11. Province names change over time (Davao de Oro, Cotabato).
12. Farmgate prices are sparse; count observed months before averaging.
13. PPA provincial GDP only covers 2018-2025.
