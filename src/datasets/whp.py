"""USFS Wildfire Hazard Potential (2023 classified, CONUS) point query."""

from __future__ import annotations

import os

import rasterio
from rasterio.warp import transform as warp_transform

WHP_COG_URI = os.environ.get("WHP_COG_URI", "s3://prefire-data/whp/whp2023_cls_conus.tif")
WHP_CLASS_LABELS = {
    1: "Very Low",
    2: "Low",
    3: "Moderate",
    4: "High",
    5: "Very High",
}
SOURCE = "USFS WHP 2023"


def query(event: dict) -> dict:
    """Return the WHP class for a single lat/lon point.

    Preconditions:
        - event["queryStringParameters"] contains `lat` and `lon` as
          float-parseable strings. lat in [-90, 90], lon in [-180, 180].

    Postconditions:
        - Returns {"zone": <label>, "whp_class": <int 1-5>, "source": SOURCE}.
        - Returns {"zone": None, "whp_class": None, "source": SOURCE} if the
          point falls on nodata (e.g. open water, non-burnable).
        - Raises ValueError on missing or invalid params.
    """
    params = event.get("queryStringParameters") or {}
    lat = _parse_float(params, "lat", -90.0, 90.0)
    lon = _parse_float(params, "lon", -180.0, 180.0)

    value, nodata = _read_pixel(lat, lon)

    if nodata is not None and value == int(nodata):
        return {"zone": None, "whp_class": None, "source": SOURCE}
    return {
        "zone": WHP_CLASS_LABELS.get(value),
        "whp_class": value,
        "source": SOURCE,
    }


def _read_pixel(lat: float, lon: float) -> tuple[int, float | None]:
    """Read a single pixel value (and nodata) from the WHP COG.

    Preconditions:
        - WHP_COG_URI points to a readable Cloud-Optimized GeoTIFF.

    Postconditions:
        - Returns (value, nodata) where value is the integer class at the
          given lat/lon and nodata is the raster's nodata sentinel or None.
    """
    with rasterio.Env(AWS_NO_SIGN_REQUEST="NO"):
        with rasterio.open(WHP_COG_URI) as ds:
            xs, ys = warp_transform("EPSG:4326", ds.crs, [lon], [lat])
            row, col = ds.index(xs[0], ys[0])
            window = ((row, row + 1), (col, col + 1))
            value = int(ds.read(1, window=window)[0, 0])
            nodata = ds.nodata
    return value, nodata


def _parse_float(params: dict, key: str, lo: float, hi: float) -> float:
    """Parse params[key] as a float bounded by [lo, hi].

    Preconditions:
        - lo <= hi.

    Postconditions:
        - Returns the parsed float.
        - Raises ValueError if the key is missing, not numeric, or out of range.
    """
    if key not in params or params[key] is None:
        raise ValueError(f"missing required query param: {key}")
    try:
        v = float(params[key])
    except (TypeError, ValueError) as e:
        raise ValueError(f"{key} must be a number") from e
    if not lo <= v <= hi:
        raise ValueError(f"{key} out of range [{lo}, {hi}]")
    return v
