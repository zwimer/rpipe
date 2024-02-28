from __future__ import annotations
from logging import basicConfig, getLogger, WARNING, DEBUG
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from threading import Thread
from os import environ
import time

from flask import Flask, Response, request
import waitress

from ..version import __version__
from .shutdown_handler import ShutdownHandler
from .globals import lock, streams, shutdown
from .constants import MAX_SIZE_HARD
from .write import write
from .read import read
from . import save_state

if TYPE_CHECKING:
    from pathlib import Path


PRUNE_DELAY: int = 5
_LOG: str = "server"

app = Flask(__name__)


@app.route("/")
@app.route("/help")
def _help() -> str:
    return (
        "Write to /write, read from /read or /peek, clear with "
        "/clear; add a trailing /<channel> to specify the channel. "
        "Note: Using the web version bypasses version consistent checks "
        "and may result in safe but unexpected behavior (such as failing "
        "an uploaded message; if possible use the rpipe CLI instead. "
        "Install the CLI via: pip install rpipe"
    )


@app.route("/version")
def _show_version() -> str:
    return __version__


@app.route("/c/<channel>", methods=["DELETE", "GET", "POST", "PUT", "CLEAR"])
def _channel(channel: str) -> Response:
    log = getLogger(_LOG)
    match request.method:
        case "DELETE":
            with lock:
                if channel in streams:
                    log.debug("Deleting channel %s", channel)
                    del streams[channel]
            return Response("Cleared", status=202)
        case "GET":
            return read(channel)
        case "POST" | "PUT":
            return write(channel)
        case _:
            log.debug("404: bad method: %s", request.method)
            return Response(status=404)


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
