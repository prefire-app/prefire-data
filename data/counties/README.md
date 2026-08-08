# Counties build script

Builds the county point-in-polygon index consumed by
[`src/datasets/county.py`](../../src/datasets/county.py).

## Source

Census Bureau cartographic boundary file
`cb_<vintage>_us_county_500k` (pre-simplified for general-purpose mapping,
~3 MB zipped). Identical authoritative county geometry as the full TIGER/Line
shapefile, but at a coastline simplification level appropriate for "which
county contains this lat/lon" queries.

- Landing page: https://www.census.gov/geographies/mapping-files/time-series/geo/carto-boundary-file.html
- Download: `https://www2.census.gov/geo/tiger/GENZ<vintage>/shp/cb_<vintage>_us_county_500k.zip`
- License: public domain

## Refresh

When Census publishes a new vintage (~annually):

    pip install pyshp shapely
    ./prepare_county_index.py s3://prefire-data/counties/

The Lambda reads from `s3://prefire-data/counties/cb_<vintage>_us_county_500k.pkl`
(env var `COUNTY_INDEX_URI` overrides). Bump the vintage by re-running the
script with `--vintage YYYY` and updating `COUNTY_INDEX_URI` if the year
changes; no Lambda redeploy is required if the URI stays the same.

## Output schema

A pickled `list[tuple[str, str, str, bytes]]` where each tuple is
`(statefp, countyfp, name, polygon_wkb)`. The Lambda deserializes once per
cold start (~1 s) and caches a `shapely.STRtree` in module memory for
sub-millisecond point-in-polygon lookups.
