"""AWS Lambda entry point for prefire-data.

Routes API Gateway HTTP API v2 events to dataset query functions based on the
request path. Adding a new dataset requires:
  1. Implementing a `query(event) -> dict` function in src/datasets/<name>.py
  2. Registering it in the ROUTES table below.
"""

from .datasets import whp
from .utils.responses import error_response, json_response

ROUTES = {
    "/whp": whp.query,
    # "/fhsz":   fhsz.query,
    # "/parcel": parcel.query,
}


def lambda_handler(event: dict, context) -> dict:  # noqa: ARG001
    """Dispatch an API Gateway HTTP API v2 event to the matching dataset.

    Preconditions:
        - event is an API Gateway HTTP API v2 invocation event with
          `rawPath` and `queryStringParameters`.

    Postconditions:
        - Returns an API Gateway HTTP v2 response dict with `statusCode`,
          `headers`, and `body`.
        - 404 if the path is not in ROUTES.
        - 400 if required query params are missing or malformed.
        - 500 only on unhandled exceptions.
    """
    path = event.get("rawPath", "")
    handler = ROUTES.get(path)
    if handler is None:
        return error_response(404, f"unknown route: {path}")
    try:
        result = handler(event)
        return json_response(200, result)
    except ValueError as e:
        return error_response(400, str(e))
    except Exception as e:  # noqa: BLE001
        return error_response(500, f"internal error: {type(e).__name__}")
