"""Tests for src/datasets/whp.py."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.datasets import whp


class _FakeDataset:
    """Minimal stand-in for a rasterio dataset."""

    def __init__(self, value: int, nodata: float | None = 0.0):
        self._value = value
        self.nodata = nodata
        self.crs = "EPSG:5070"
        self.height = 1000
        self.width = 1000

    def index(self, x, y):  # noqa: ARG002
        return 10, 20

    def read(self, band, window):  # noqa: ARG002
        return np.array([[self._value]], dtype=np.int16)


@contextmanager
def _fake_open(value: int, nodata: float | None = 0.0):
    yield _FakeDataset(value, nodata)


def _event(lat=None, lon=None):
    params = {}
    if lat is not None:
        params["lat"] = str(lat)
    if lon is not None:
        params["lon"] = str(lon)
    return {"rawPath": "/whp", "queryStringParameters": params}


def _patches(value: int, nodata: float | None = 0.0):
    """Patch rasterio.open + warp_transform inside the whp module."""
    open_patch = patch.object(whp.rasterio, "open", lambda *_a, **_kw: _fake_open(value, nodata))
    env_patch = patch.object(whp.rasterio, "Env", MagicMock())
    warp_patch = patch.object(whp, "warp_transform", lambda *_a, **_kw: ([0.0], [0.0]))
    return open_patch, env_patch, warp_patch


# --- _parse_float unit tests --------------------------------------------------


def test_parse_float_returns_value_inside_range():
    assert whp._parse_float({"x": "1.5"}, "x", 0.0, 2.0) == 1.5


def test_parse_float_missing_key_raises():
    with pytest.raises(ValueError, match="missing required"):
        whp._parse_float({}, "x", 0.0, 1.0)


def test_parse_float_non_numeric_raises():
    with pytest.raises(ValueError, match="must be a number"):
        whp._parse_float({"x": "abc"}, "x", 0.0, 1.0)


def test_parse_float_below_range_raises():
    with pytest.raises(ValueError, match="out of range"):
        whp._parse_float({"x": "-1"}, "x", 0.0, 1.0)


def test_parse_float_above_range_raises():
    with pytest.raises(ValueError, match="out of range"):
        whp._parse_float({"x": "2"}, "x", 0.0, 1.0)


def test_parse_float_at_lower_bound_allowed():
    assert whp._parse_float({"x": "0"}, "x", 0.0, 1.0) == 0.0


def test_parse_float_at_upper_bound_allowed():
    assert whp._parse_float({"x": "1"}, "x", 0.0, 1.0) == 1.0


# --- acceptance tests ---------------------------------------------------------


@pytest.mark.acceptance
def test_ac_whp_returns_class_for_valid_point():
    op, ep, wp = _patches(value=4, nodata=0)
    with op, ep, wp:
        result = whp.query(_event(lat=37.7749, lon=-122.4194))
    assert result == {"zone": "High", "whp_class": 4, "source": whp.SOURCE}


@pytest.mark.acceptance
def test_ac_whp_returns_null_on_nodata():
    op, ep, wp = _patches(value=0, nodata=0)
    with op, ep, wp:
        result = whp.query(_event(lat=37.0, lon=-122.0))
    assert result == {"zone": None, "whp_class": None, "source": whp.SOURCE}


@pytest.mark.acceptance
def test_ac_whp_missing_lat_returns_400():
    with pytest.raises(ValueError, match="lat"):
        whp.query(_event(lon=-122.0))


@pytest.mark.acceptance
def test_ac_whp_lat_out_of_range_returns_400():
    with pytest.raises(ValueError, match="lat out of range"):
        whp.query(_event(lat=200.0, lon=-122.0))


@pytest.mark.acceptance
def test_ac_whp_non_burnable_returns_null():
    """WHP encodes 6=Non-burnable, 7=Water — both should map to null."""
    for v in (6, 7):
        op, ep, wp = _patches(value=v, nodata=0)
        with op, ep, wp:
            result = whp.query(_event(lat=37.0, lon=-122.0))
        assert result == {"zone": None, "whp_class": None, "source": whp.SOURCE}


@pytest.mark.acceptance
def test_ac_whp_out_of_raster_extent_returns_null():
    """Points outside the COG's row/col bounds must not return a value."""

    class _OOBDataset(_FakeDataset):
        def index(self, x, y):  # noqa: ARG002
            return -1, -1

    @contextmanager
    def _oob_open(*_a, **_kw):
        yield _OOBDataset(value=1, nodata=0)

    with (
        patch.object(whp.rasterio, "open", _oob_open),
        patch.object(whp.rasterio, "Env", MagicMock()),
        patch.object(whp, "warp_transform", lambda *_a, **_kw: ([0.0], [0.0])),
    ):
        result = whp.query(_event(lat=35.0, lon=-150.0))
    assert result == {"zone": None, "whp_class": None, "source": whp.SOURCE}
