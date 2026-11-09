# Data dictionary

## Layers

- `data/raw/` - byte-exact downloads. Never edited.
- `data/normalized/` - light reshaping only. No joins, no derived measures, no row drops.
- `data/reference/` - crosswalks and centroids used to key the data.

## Normalized files

### production_long.csv
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

### area_long.csv
Same schema as production; `value` is hectares. Quarterly cells are mostly
null for pineapple; semester values are populated.

### farmgate_long.csv
Same schema plus `commodity`; `value` is pesos per kilogram.

### ppa_long.csv
Same schema plus `sector` and `type_of_valuation`; `value` is thousand pesos.
No region/province carry-forward: PPA geographies use a different label shape.

### weather_long.csv

| Column | Meaning |
|---|---|
| `region_name`, `province_name` | key matching the PSA normalized tables |
| `year`, `month` | calendar month |
| `parameter` | NASA POWER parameter code |
| `unit` | source unit |
| `value` | null when NASA returns -999.0 |

Parameters: PRECTOTCORR (mm/day), T2M / T2M_MAX / T2M_MIN (deg C),
RH2M (%), ALLSKY_SFC_SW_DWN (MJ/m2/day).

### enso_long.csv
`season` (DJF, JFM, ...), `year`, `total`, `anomaly` from NOAA ONI.

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
