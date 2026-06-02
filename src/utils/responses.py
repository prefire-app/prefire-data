"""API Gateway HTTP API v2 response helpers."""

import json


def json_response(status: int, body: dict) -> dict:
    """Build an API Gateway HTTP v2 response with a JSON body.

    Preconditions:
        - body is JSON-serializable.

    Postconditions:
        - Returns a dict with `statusCode`, `headers`, and `body` keys.
    """
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def error_response(status: int, message: str) -> dict:
    """Build a JSON error response of the form {'error': message}.

    Preconditions:
        - message is a short human-readable string.

    Postconditions:
        - Returns json_response(status, {'error': message}).
    """
    return json_response(status, {"error": message})
