from __future__ import annotations
from typing import TYPE_CHECKING
from logging import getLogger

from flask import Flask
import waitress

from ..version import __version__
from .util import MAX_SIZE_HARD, plaintext
from .channel import channel_handler
from .server import Server
from .admin import Admin

if TYPE_CHECKING:
    from pathlib import Path
    from flask import Response


app = Flask(f"rpipe_server {__version__}")
server = Server()
admin = Admin()
_LOG = "app"


@app.route("/")
@app.route("/help")
def _help() -> Response:
    getLogger(_LOG).info("Request for /help")
    msg = (
        "Welcome to the web UI of rpipe. "
        "To interact with a given channel, use the path /c/<channel>. "
        "To read a message from a given channel, use a GET request. "
        "To write a message to a given channel, use PUT and POST requests. "
        "To clear a channel, use a DELETE request. "
        "Note: Using the web version bypasses version consistent checks "
        "and may result in safe but unexpected behavior (such as failing "
        "an uploaded message; if possible use the rpipe client CLI instead. "
        "Install the CLI via: pip install rpipe"
    )
    return plaintext(msg)


@app.route("/version")
def _show_version() -> Response:
    getLogger(_LOG).info("Request for /version")
    return plaintext(__version__)


@app.route("/c/<channel>", methods=["DELETE", "GET", "POST", "PUT"])
def _channel(channel: str) -> Response:
    return channel_handler(server.state, channel)


# Admin routes


@app.route("/admin/uid")
def _admin_uid() -> Response:
    """
    Get a few UIDSs needed to sign admin requests
    The exact number is up to the server, if you need more, request more
    These UIDs will expire after a short period of time
    """
    return admin.uids()


@app.route("/admin/debug", methods=["POST"])
def _admin_debug() -> Response:
    return admin.debug(server.state)


@app.route("/admin/channels", methods=["POST"])
def _admin_channels() -> Response:
    return admin.channels(server.state)


# Serve


def serve(host: str, port: int, debug: bool, state_file: Path | None, key_files: list[Path]) -> None:
    log = getLogger(_LOG)
    log.info("Setting max packet size: %s", MAX_SIZE_HARD)
    app.config["MAX_CONTENT_LENGTH"] = MAX_SIZE_HARD
    app.url_map.strict_slashes = False
    server.start(debug, state_file)
    admin.load_keys(key_files)
    log.info("Serving on %s:%s", host, port)
    if debug:
        app.run(host=host, port=port, debug=True)
    else:
        waitress.serve(app, host=host, port=port)
