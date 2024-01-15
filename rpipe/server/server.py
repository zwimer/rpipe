from __future__ import annotations
from datetime import datetime, timedelta
from threading import Thread
import time
import sys

from flask import Flask, Response, request
import waitress

from ..version import __version__
from .constants import MAX_SIZE_HARD
from .globals import lock, streams
from .write import write
from .read import read


PRUNE_DELAY: int = 5

app = Flask(__name__)


@app.route("/")
@app.route("/help")
def _help() -> str:
    return (
        "Write to /write, read from /read or /peek, clear with "
        "/clear; add a trailing /<channel> to specify the channel. "
        "Note: Using the web version bypasses version consistenct checks "
        "and may result in safe but unexpected behavior (such as failing "
        "an uploaded message; if possible use the rpipe CLI instead. "
        "Install the CLI via: pip install rpipe"
    )


@app.route("/version")
def _show_version() -> str:
    return __version__


@app.route("/c/<channel>", methods=["DELETE", "GET", "POST", "PUT", "CLEAR"])
def _channel(channel: str) -> Response:
    match request.method:
        case "DELETE":
            with lock:
                if channel in streams:
                    del streams[channel]
            return Response("Cleared", status=202)
        case "GET":
            return read(channel)
        case "POST" | "PUT":
            return write(channel)
        case _:
            return Response(status=404)


def _periodic_prune() -> None:
    """
    Remove items added to rpipe too long ago
    """
    prune_age = timedelta(minutes=PRUNE_DELAY)
    while True:
        old: datetime = datetime.now() - prune_age
        with lock:
            for i, k in streams.items():
                if k.when < old:
                    del streams[i]
        time.sleep(60)


def start(host: str, port: int, debug: bool) -> None:
    app.config["MAX_CONTENT_LENGTH"] = MAX_SIZE_HARD
    app.url_map.strict_slashes = False
    Thread(target=_periodic_prune, daemon=True).start()
    print(f"Starting server on {host}:{port}")
    if debug:
        sys.stdout = sys.stderr
        app.run(host=host, port=port, debug=True)
    else:
        waitress.serve(app, host=host, port=port)
