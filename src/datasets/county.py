"""US county point-in-polygon lookup backed by a Census shapefile snapshot.

The index is built offline by ``data/counties/prepare_county_index.py`` and
stored as a single pickle in S3. On first invocation the module downloads the
pickle to ``/tmp`` and builds an ``shapely.STRtree`` for sub-millisecond
point-in-polygon lookups. Subsequent invocations on a warm Lambda hit memory.
"""

from __future__ import annotations

import os
import pickle
import threading
from functools import lru_cache

import boto3
from shapely import wkb
from shapely.geometry import Point
from shapely.strtree import STRtree

COUNTY_INDEX_URI = os.environ.get(
    "COUNTY_INDEX_URI",
    "s3://prefire-data/counties/cb_2024_us_county_500k.pkl",
)
_LOCAL_CACHE_PATH = "/tmp/county_index.pkl"  # noqa: S108 — Lambda /tmp is the only writable path
SOURCE = "Census CB 2024 (500k counties)"

# STATEFP -> USPS code. Includes 50 states + DC + 5 territories.
STATE_FIPS_TO_CODE = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO",
    "09": "CT", "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI",
    "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
    "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN",
    "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
    "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
    "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA",
    "54": "WV", "55": "WI", "56": "WY", "60": "AS", "66": "GU", "69": "MP",
    "72": "PR", "78": "VI",
}  # fmt: skip

_TREE: STRtree | None = None
_COUNTIES: list[dict] | None = None
_LOAD_LOCK = threading.Lock()


def query(event: dict) -> dict:
    """Return the county containing a single lat/lon point.

    Preconditions:
        - event["queryStringParameters"] contains lat/lon as float-parseable
          strings (lat in [-90, 90], lon in [-180, 180]).

    Postconditions:
        - Returns {stateFips, countyFips, countyName, stateCode, source} when
          the point lies inside a US county polygon.
        - Returns {stateFips: None, countyFips: None, countyName: None,
          stateCode: None, source} when the point is outside all county
          polygons (e.g. open ocean, outside US).
        - Raises ValueError on missing/invalid params.
    """
    params = event.get("queryStringParameters") or {}
    lat = _parse_float(params, "lat", -90.0, 90.0)
    lon = _parse_float(params, "lon", -180.0, 180.0)

    match = _lookup(round(lat, 5), round(lon, 5))
    if match is None:
        return {
            "stateFips": None,
            "countyFips": None,
            "countyName": None,
            "stateCode": None,
            "source": SOURCE,
        }
    return {**match, "source": SOURCE}


@lru_cache(maxsize=4096)
def _lookup(lat: float, lon: float) -> dict | None:
    """Point-in-polygon lookup against the cached county index.

    Preconditions:
        - lat/lon are finite floats already range-validated by the caller.

    Postconditions:
        - Returns a dict with stateFips/countyFips/countyName/stateCode when a
          containing county exists.
        - Returns None otherwise.
    """
    tree, counties = _ensure_loaded()
    pt = Point(lon, lat)  # shapely uses (x=lon, y=lat)
    for idx in tree.query(pt):
        county = counties[int(idx)]
        if county["geom"].contains(pt):
            return {
                "stateFips": county["stateFips"],
                "countyFips": county["countyFips"],
                "countyName": county["countyName"],
                "stateCode": STATE_FIPS_TO_CODE.get(county["stateFips"]),
            }
    return None


def _ensure_loaded() -> tuple[STRtree, list[dict]]:
    """Lazily download + deserialize the county index, building an STRtree.

    Preconditions:
        - COUNTY_INDEX_URI is a valid s3://bucket/key URI.

    Postconditions:
        - Returns the module-cached (tree, counties) tuple, building it on the
          first call. Subsequent calls return the same tuple.
    """
    global _TREE, _COUNTIES
    if _TREE is not None and _COUNTIES is not None:
        return _TREE, _COUNTIES
    with _LOAD_LOCK:
        if _TREE is not None and _COUNTIES is not None:
            return _TREE, _COUNTIES
        if not os.path.exists(_LOCAL_CACHE_PATH):
            _download_index(COUNTY_INDEX_URI, _LOCAL_CACHE_PATH)
        with open(_LOCAL_CACHE_PATH, "rb") as fh:
            raw = pickle.load(fh)  # noqa: S301 — file we built and uploaded ourselves
        counties = [
            {
                "stateFips": stfp,
                "countyFips": f"{stfp}{cofp}",
                "countyName": f"{name} County",
                "geom": wkb.loads(geom_wkb),
            }
            for (stfp, cofp, name, geom_wkb) in raw
        ]
        _TREE = STRtree([c["geom"] for c in counties])
        _COUNTIES = counties
        return _TREE, _COUNTIES


def _download_index(s3_uri: str, dest_path: str) -> None:
    """Download an s3:// URI to a local path using boto3.

    Preconditions:
        - s3_uri starts with 's3://' and contains a bucket and key.

    Postconditions:
        - dest_path exists and contains the object's bytes.
        - Raises ValueError on a malformed URI.
    """
    if not s3_uri.startswith("s3://"):
        raise ValueError(f"COUNTY_INDEX_URI must be s3://...; got {s3_uri!r}")
    without_scheme = s3_uri[len("s3://") :]
    bucket, _, key = without_scheme.partition("/")
    if not bucket or not key:
        raise ValueError(f"COUNTY_INDEX_URI missing bucket or key: {s3_uri!r}")
    boto3.client("s3").download_file(bucket, key, dest_path)


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
