from __future__ import annotations
from logging import basicConfig, getLogger, WARNING, DEBUG
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from threading import Thread
from os import environ
import time

from flask import Flask, request
import waitress

from ..version import __version__
from .shutdown_handler import ShutdownHandler
from .globals import lock, streams, shutdown
from .constants import MAX_SIZE_HARD
from .util import plaintext
from .write import write
from .read import read
from . import save_state

if TYPE_CHECKING:
    from pathlib import Path
    from flask import Response


PRUNE_DELAY: int = 5
_LOG: str = "server"

app = Flask(__name__)


@app.route("/")
@app.route("/help")
def _help() -> Response:
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
    return plaintext(__version__)


@app.route("/c/<channel>", methods=["DELETE", "GET", "POST", "PUT"])
def _channel(channel: str) -> Response:
    log = getLogger(_LOG)
    match request.method:
        case "DELETE":
            with lock:
                if channel in streams:
                    log.debug("Deleting channel %s", channel)
                    del streams[channel]
            return plaintext("Cleared", status=202)
        case "GET":
            return read(channel)
        case "POST" | "PUT":
            return write(channel)
        case _:
            log.debug("404: bad method: %s", request.method)
            return plaintext(f"Unknown method: {request.method}", status=404)


def _periodic_prune() -> None:
    """
    Remove items added to rpipe too long ago
    """
    prune_age = timedelta(minutes=PRUNE_DELAY)
    log = getLogger("Prune Thread")
    log.debug("Starting prune loop with prune age of %s", prune_age)
    while True:
        old: datetime = datetime.now() - prune_age
        with lock:
            if shutdown:
                return
            for i, k in streams.items():
                if k.when < old:
                    log.debug("Pruning channel %s", i)
                    del streams[i]
        time.sleep(60)


def start(host: str, port: int, debug: bool, dir: Path | None) -> None:
    basicConfig(level=DEBUG if debug else WARNING, format="%(message)s")
    log = getLogger(_LOG)
    log.debug("Setting max packet size: %s", MAX_SIZE_HARD)
    app.config["MAX_CONTENT_LENGTH"] = MAX_SIZE_HARD
    app.url_map.strict_slashes = False
    # Load state
    if dir is not None:
        if not dir.exists():
            raise RuntimeError(f"Directory {dir} does not exist")
        # Do not run on first load when in debug mode b / c of flask reloader
        if debug and environ.get("WERKZEUG_RUN_MAIN") != "true":
            msg = "Not loading state or installing shutdown handler during initial flask load on debug mode"
            log.info(msg)
        else:
            save_dir = dir / "save"
            if save_dir.exists():
                save_state.load(save_dir)
            ShutdownHandler(save_dir)
    # Start
    print(f"Starting server on {host}:{port}")
    Thread(target=_periodic_prune, daemon=True).start()
    if debug:
        app.run(host=host, port=port, debug=True)
    else:
        waitress.serve(app, host=host, port=port)
