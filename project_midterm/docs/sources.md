# Data sources

Retrieved by `src/run.py`. All raw files are byte-exact snapshots.

## PSA OpenSTAT (authoritative)

- API base: `https://openstat.psa.gov.ph/PXWeb/api/v1/en/DB`
- HTML metadata pages return HTTP 403; the API works. Do not scrape HTML.
- Open data license: freely usable with attribution to the Philippine Statistics Authority.

| Dataset | Table path | Raw file |
|---|---|---|
| Fruit crops: volume of production | `2E/CS/0072E4EVCP2.px` | `psa/production_fruit_crops.csv` |
| Fruit crops: area planted/harvested | `2E/CS/0102E4EAHM2.px` | `psa/area_fruit_crops.csv` |
| Fruits: farmgate prices | `2M/NFG/0032M4AFN07.px` | `psa/farmgate_fruits.csv` |
| GDP by industry, province and HUC | `2A/PPA/0022A5FPPA1.px` | `psa/ppa_gdp_by_industry.csv` |

## NASA POWER

- Endpoint: `https://power.larc.nasa.gov/api/temporal/monthly/point`
- Community: `AG`
- No API key required.
- Monthly values for the grid cell nearest each province centroid.

| Parameter | Unit | Description |
|---|---|---|
| `PRECTOTCORR` | mm/day | Bias-corrected precipitation rate. Monthly total = value x days in month. |
| `T2M` | deg C | Mean air temperature at 2 m. |
| `T2M_MAX` | deg C | Mean daily maximum temperature at 2 m. |
| `T2M_MIN` | deg C | Mean daily minimum temperature at 2 m. |
| `RH2M` | % | Relative humidity at 2 m. |
| `ALLSKY_SFC_SW_DWN` | MJ/m2/day | All-sky surface shortwave downward irradiance (solar energy). |

- Fill value `-999.0` is stored as null.
- Annual rows (`YYYY13`) are dropped during normalization.

## NOAA ONI

- Endpoint: `https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt`
- Index: Oceanic Nino Index (ONI)
- Region: Nino 3.4 (5N-5S, 120W-170W)
- Definition: 3-month running mean of sea-surface temperature anomalies
- Source dataset: ERSSTv5
- Base period: centered 30-year climatology, updated every five years;
  current base 1991-2020
- Units: degrees Celsius
- File columns: `SEAS` (season), `YR` (year), `TOTAL` (absolute SST),
  `ANOM` (anomaly)
- Seasons are overlapping 3-month windows (`DJF`, `JFM`, ..., `NDJ`)

## PSGC classification

- `https://statistics.bettergov.ph/api/classification/psgc/Q2_2024/regions`
- `https://statistics.bettergov.ph/api/classification/psgc/Q2_2024/provinces`
- Version: `Q2_2024`.

## geoBoundaries (province geometry, used once for centroids)

- Metadata: `https://www.geoboundaries.org/api/current/gbOpen/PHL/ADM2/`
- Unit: PHL ADM2 (provinces), 87 units
- Source: NAMRIA / PSA / OCHA Philippines
- License: CC BY 3.0 IGO
- Centroid method: area-weighted polygon centroid (largest polygon for multipart)
- Tolerance: suitable for 0.5 degree NASA POWER grid sampling, not for mapping.

## Attribution

Philippine Statistics Authority (PSA) via OpenSTAT. geoBoundaries via the
geoBoundaries project (CC BY 3.0 IGO). NASA POWER via NASA Langley Research
Center. NOAA CPC for the ONI. BetterGov.ph classification API for PSGC codes.
