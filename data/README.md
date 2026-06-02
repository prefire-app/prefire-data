# Source data

## USFS Wildfire Hazard Potential (WHP)

- **Version in use:** `2023 classified, RDS-2015-0047-4` (270 m, CONUS, EPSG:5070).
- **Landing page:** https://www.fs.usda.gov/rds/archive/Catalog/RDS-2015-0047-4
- **Raw download:** https://www.fs.usda.gov/rds/archive/products/RDS-2015-0047-4/RDS-2015-0047-4.zip
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
