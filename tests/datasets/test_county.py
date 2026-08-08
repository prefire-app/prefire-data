"""Tests for src/datasets/county.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from shapely.geometry import Polygon
from shapely.strtree import STRtree

from src.datasets import county

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _square(minx: float, miny: float, maxx: float, maxy: float) -> Polygon:
    return Polygon([(minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy)])


@pytest.fixture
def _fake_index():
    """Install a deterministic in-memory STRtree covering two synthetic counties."""
    sf_county = _square(-122.6, 37.5, -122.3, 37.9)  # San Francisco-ish
    denver_county = _square(-105.2, 39.6, -104.9, 39.9)  # Denver-ish
    counties = [
        {
            "stateFips": "06",
            "countyFips": "06075",
            "countyName": "San Francisco County",
            "geom": sf_county,
        },
        {
            "stateFips": "08",
            "countyFips": "08031",
            "countyName": "Denver County",
            "geom": denver_county,
        },
    ]
    tree = STRtree([c["geom"] for c in counties])
    county._TREE = tree
    county._COUNTIES = counties
    county._lookup.cache_clear()
    yield
    county._TREE = None
    county._COUNTIES = None
    county._lookup.cache_clear()


def _event(lat=None, lon=None):
    params = {}
    if lat is not None:
        params["lat"] = str(lat)
    if lon is not None:
        params["lon"] = str(lon)
    return {"rawPath": "/county", "queryStringParameters": params}


# ---------------------------------------------------------------------------
# _parse_float (same contract as whp; covered briefly here too)
# ---------------------------------------------------------------------------


def test_parse_float_returns_value_inside_range():
    assert county._parse_float({"x": "1.5"}, "x", 0.0, 2.0) == 1.5


def test_parse_float_missing_key_raises():
    with pytest.raises(ValueError, match="missing required"):
        county._parse_float({}, "x", 0.0, 1.0)


def test_parse_float_out_of_range_raises():
    with pytest.raises(ValueError, match="out of range"):
        county._parse_float({"x": "5"}, "x", 0.0, 1.0)


# ---------------------------------------------------------------------------
# _download_index
# ---------------------------------------------------------------------------


def test_download_index_rejects_non_s3_uri():
    with pytest.raises(ValueError, match="s3://"):
        county._download_index("https://example.com/file.pkl", "/tmp/x")


def test_download_index_rejects_uri_without_key():
    with pytest.raises(ValueError, match="missing bucket or key"):
        county._download_index("s3://only-bucket", "/tmp/x")


def test_download_index_uses_boto3_client():
    fake_client = MagicMock()
    with patch.object(county.boto3, "client", return_value=fake_client) as client_factory:
        county._download_index("s3://my-bucket/path/to/file.pkl", "/tmp/dest")
    client_factory.assert_called_once_with("s3")
    fake_client.download_file.assert_called_once_with("my-bucket", "path/to/file.pkl", "/tmp/dest")


# ---------------------------------------------------------------------------
# query() — exercised through the fake in-memory index
# ---------------------------------------------------------------------------


@pytest.mark.acceptance
def test_ac_county_returns_match_for_known_ca_point(_fake_index):
    """AC: a known San Francisco point returns CA (06) / SF (06075)."""
    result = county.query(_event(lat=37.7749, lon=-122.4194))
    assert result["stateFips"] == "06"
    assert result["countyFips"] == "06075"
    assert result["stateCode"] == "CA"
    assert result["countyName"] == "San Francisco County"


@pytest.mark.acceptance
def test_ac_county_returns_match_for_known_co_point(_fake_index):
    """AC: a known Denver point returns CO (08) / Denver (08031)."""
    result = county.query(_event(lat=39.7392, lon=-104.9903))
    assert result["stateFips"] == "08"
    assert result["countyFips"] == "08031"
    assert result["stateCode"] == "CO"


@pytest.mark.acceptance
def test_ac_county_returns_null_in_ocean(_fake_index):
    """AC: a point in the ocean returns all-null county fields."""
    result = county.query(_event(lat=0.0, lon=-150.0))
    assert result == {
        "stateFips": None,
        "countyFips": None,
        "countyName": None,
        "stateCode": None,
        "source": county.SOURCE,
    }


def test_query_missing_lat_raises(_fake_index):
    with pytest.raises(ValueError, match="lat"):
        county.query(_event(lon=-122.0))


def test_query_lon_out_of_range_raises(_fake_index):
    with pytest.raises(ValueError, match="lon out of range"):
        county.query(_event(lat=37.0, lon=200.0))


def test_lookup_returns_none_for_point_outside_polygon_bbox(_fake_index):
    # Inside the SF county bounding box but outside the polygon would be
    # impossible for a rectangle; instead assert a clearly-outside point
    # returns None.
    assert county._lookup(0.0, 0.0) is None


def test_state_fips_to_code_covers_all_50_states_plus_dc():
    """Sanity: at least 51 entries (50 states + DC); CA/CO/NY present."""
    assert county.STATE_FIPS_TO_CODE["06"] == "CA"
    assert county.STATE_FIPS_TO_CODE["08"] == "CO"
    assert county.STATE_FIPS_TO_CODE["36"] == "NY"
    assert county.STATE_FIPS_TO_CODE["11"] == "DC"
    assert len(county.STATE_FIPS_TO_CODE) >= 51


def test_query_returns_source_field(_fake_index):
    result = county.query(_event(lat=37.7749, lon=-122.4194))
    assert result["source"] == county.SOURCE
