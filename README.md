# prefire-data

A single AWS Lambda exposing point-query endpoints over geospatial datasets.
Currently hosts:

- `GET /whp?lat=<float>&lon=<float>` — USFS Wildfire Hazard Potential (2023
  classified, CONUS).
- `GET /county?lat=<float>&lon=<float>` — US county point-in-polygon lookup
  (Census cb_2024_us_county_500k). Returns `stateFips`, `countyFips`,
  `countyName`, `stateCode`.

## Layout

- `src/handler.py` — Lambda entry; routes paths to dataset query functions.
- `src/datasets/` — one module per dataset, each exposing `query(event)`.
- `src/utils/responses.py` — API Gateway HTTP API v2 response helpers.
- `data/` — scripts and docs for (re)building the source rasters in S3.
- `infra/` — CDK app (API Gateway v2 + container-image Lambda + S3 reference).

## Adding a new dataset

1. Create `src/datasets/<name>.py` with `def query(event: dict) -> dict`.
2. Register it in `ROUTES` in [`src/handler.py`](src/handler.py).
3. Add tests under `tests/datasets/test_<name>.py`.

No changes to handler routing logic or infra (beyond rebuilding the Lambda
image) should be required.

## Develop

```
make install
make lint
make test
```

## Deploy

```
make deploy
```

Then call:

```
curl "$DataApiEndpoint/whp?lat=37.7749&lon=-122.4194"
```
