"""Tests for src/handler.py routing."""

import json

import pytest

from src import handler


def _event(path, params=None):
    return {"rawPath": path, "queryStringParameters": params or {}}


def test_handler_dispatches_to_registered_route():
    handler.ROUTES["/__test_ok"] = lambda _e: {"hello": "world"}
    try:
        resp = handler.lambda_handler(_event("/__test_ok"), None)
    finally:
        del handler.ROUTES["/__test_ok"]
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"]) == {"hello": "world"}


@pytest.mark.acceptance
def test_ac_handler_unknown_route_returns_404():
    resp = handler.lambda_handler(_event("/xyz-does-not-exist"), None)
    assert resp["statusCode"] == 404
    body = json.loads(resp["body"])
    assert "unknown route" in body["error"]


def test_handler_value_error_returns_400():
    def boom(_event):
        raise ValueError("bad input")

    handler.ROUTES["/__test_bad"] = boom
    try:
        resp = handler.lambda_handler(_event("/__test_bad"), None)
    finally:
        del handler.ROUTES["/__test_bad"]
    assert resp["statusCode"] == 400
    assert json.loads(resp["body"]) == {"error": "bad input"}


@pytest.mark.acceptance
def test_ac_handler_unhandled_exception_returns_500():
    def boom(_event):
        raise RuntimeError("kaboom")

    handler.ROUTES["/__test_500"] = boom
    try:
        resp = handler.lambda_handler(_event("/__test_500"), None)
    finally:
        del handler.ROUTES["/__test_500"]
    assert resp["statusCode"] == 500
    body = json.loads(resp["body"])
    assert "internal error" in body["error"]
    assert "RuntimeError" in body["error"]
