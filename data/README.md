# Source data

## USFS Wildfire Hazard Potential (WHP)

- **Version in use:** `2023 classified, RDS-2015-0047-4` (270 m, CONUS, EPSG:5070).
- **Landing page:** https://www.fs.usda.gov/rds/archive/Catalog/RDS-2015-0047-4
- **Raw download:** https://www.fs.usda.gov/rds/archive/products/RDS-2015-0047-4/RDS-2015-0047-4_Data.zip
  (~351 MB; the classified CONUS GeoTIFF lives at `Data/whp2023_GeoTIF/whp2023_cls_conus.tif`).
- **S3 location read by the Lambda:** `s3://prefire-data/whp/whp2023_cls_conus.tif`
  (the env var `WHP_COG_URI` overrides this).

The classified raster encodes integer hazard classes 1–5; pixels outside any
burnable area carry the raster's nodata value.

### Refresh

When USFS publishes a new version (~every 1–2 years):

```
./prepare_whp_cog.sh s3://prefire-data/whp/
```

Then redeploy the Lambda. No code change is required if the S3 object name
stays the same. If it changes, update `WHP_COG_URI` in
[`infra/stacks/data_lambda_stack.py`](../infra/stacks/data_lambda_stack.py).

### Class meanings and project mapping

| WHP class | Label     | Project mapping       |
|-----------|-----------|-----------------------|
| 5         | Very High | `"Very High"`         |
| 4         | High      | `"High"`              |
| 3         | Moderate  | `"Moderate"`          |
| 1–2       | Very Low / Low | `null` (0 pts) |
| nodata    | —         | `null`                |

## US county boundaries

- **Source:** US Census Bureau cartographic boundary file
  `cb_<vintage>_us_county_500k` (pre-simplified, ~3 MB).
- **S3 location read by the Lambda:**
  `s3://prefire-data/counties/cb_2024_us_county_500k.pkl`
  (env var `COUNTY_INDEX_URI` overrides).
- **Refresh:** see [`counties/README.md`](counties/README.md).

## Building footprints (per-state PMTiles)

- **Source:** Overture Maps `buildings` theme (Microsoft + Google + OSM,
  pre-deduplicated), released monthly to `s3://overturemaps-us-west-2/`.
- **Output:** one PMTiles archive per state at
  `s3://prefire-data/pmtiles/buildings-<state_fips>.pmtiles`
  (e.g. `buildings-06.pmtiles` for California, `buildings-48.pmtiles` for Texas).
- **Consumed by:** the webapp's Leaflet map via `protomaps-leaflet`, fetched
  directly from S3 over HTTP range requests — **not** routed through this
  repo's Lambda.

The per-state split keeps each file in the low hundreds of MB (vs. ~15 GB
for a single CONUS file), lets refreshes run one state at a time, and aligns
with the webapp's state-selection flow.

### Refresh

Requires `tippecanoe >= 2.40`, `awscli`, and Python with `duckdb`. On macOS:

```
brew install tippecanoe awscli
pip install -r buildings/requirements.txt
```

Then, from `data/`:

```
# all 50 states + DC
./buildings/prepare_buildings_pmtiles.py --bucket prefire-data

# a subset
./buildings/prepare_buildings_pmtiles.py --bucket prefire-data --states 06,48,12

# build locally without uploading (debugging)
./buildings/prepare_buildings_pmtiles.py --bucket prefire-data --skip-upload \
  --workdir ./out --states 11
```

When a newer Overture release ships
([release notes](https://docs.overturemaps.org/release/latest/)), either pass
`--release 2026-MM-DD.0` or update `OVERTURE_RELEASE_DEFAULT` in
[`buildings/prepare_buildings_pmtiles.py`](buildings/prepare_buildings_pmtiles.py).

No Lambda or infra change is required — the script only writes new S3 objects.
