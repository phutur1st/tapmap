"""Flask endpoint that exposes snapshot data for hub polling.

Register with register_node_endpoint() after the Dash app is created.
The endpoint is only activated when TAPMAP_NODE_MODE=1.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

_ENDPOINT_PATH = "/api/v1/snapshot"
# Fields added by the hub layer that nodes should not expose
_STRIP_FIELDS = frozenset({"app_info"})


def register_node_endpoint(
    flask_app: Any,
    snapshot_fn: Callable[[], dict[str, Any]],
    token: str | None = None,
) -> None:
    """Register GET /api/v1/snapshot on the Flask app underlying Dash.

    Args:
        flask_app: The Flask application (``dash_app.server``).
        snapshot_fn: Callable that returns a fresh SnapshotPayload dict.
        token: Optional shared secret.  When set, requests must supply
            ``Authorization: Bearer <token>`` or receive a 401.
    """
    from flask import Response, request as flask_request

    def _snapshot_view() -> Response:
        if token:
            auth = flask_request.headers.get("Authorization", "")
            expected = f"Bearer {token}"
            if auth != expected:
                logger.warning("Node endpoint: unauthorized request from %s", flask_request.remote_addr)
                return Response(
                    json.dumps({"error": True, "message": "Unauthorized"}),
                    status=401,
                    mimetype="application/json",
                )

        try:
            payload = snapshot_fn()
            # Strip fields that are hub-internal and should not be leaked
            clean = {k: v for k, v in payload.items() if k not in _STRIP_FIELDS}
            return Response(
                json.dumps(clean),
                status=200,
                mimetype="application/json",
            )
        except Exception as exc:
            logger.error("Node endpoint: snapshot failed — %s", exc)
            return Response(
                json.dumps({"error": True, "message": str(exc)}),
                status=500,
                mimetype="application/json",
            )

    flask_app.add_url_rule(
        _ENDPOINT_PATH,
        endpoint="tapmap_node_snapshot",
        view_func=_snapshot_view,
        methods=["GET"],
    )
    logger.info("Node endpoint registered at %s", _ENDPOINT_PATH)
