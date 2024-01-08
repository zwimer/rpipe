from __future__ import annotations
from datetime import datetime, timedelta
from threading import Thread, RLock
from typing import NamedTuple
from pathlib import Path
import argparse
import time
import sys

from flask import Flask, Response, request
import waitress

from ._version import __version__


#
# Types
#


class Data(NamedTuple):
    """
    A timestamped bytes class
    """

    data: bytes
    when: datetime


#
# Globals
#

data: dict[str, Data] = {}
lock = RLock()

app = Flask(__name__)
app.url_map.strict_slashes = False

#
# Helpers
#


def _get(channel: str, delete: bool) -> tuple[str, int] | bytes:
    with lock:
        got: Data | None = data.get(channel, None)
        if delete and got is not None:
            del data[channel]
    if got is None:
        return f"No data on channel {channel}", 400
    return got.data


def _periodic_prune() -> None:
    prune_age = timedelta(minutes=5)
    while True:
        old: datetime = datetime.now() - prune_age
        with lock:
            for i in [i for i, k in data.items() if k.when < old]:
                del data[i]
        time.sleep(60)


#
# Routes
#


@app.route("/help")
def _help() -> str:
    return (
        "Write to /write, read from /read or /peek, clear with "
        "/clear; add a trailing /<channel> to specify the channel"
    )


@app.route("/")
def _root() -> str:
    return _help()


@app.route("/clear/<channel>")
def _clear(channel: str) -> Response:
    with lock:
        if channel in data:
            del data[channel]
    return Response(status=204)


@app.route("/peek/<channel>")
def _peek(channel: str) -> tuple[str, int] | bytes:
    return _get(channel, False)


@app.route("/read/<channel>")
def _read(channel: str) -> tuple[str, int] | bytes:
    return _get(channel, True)


@app.route("/write/<channel>", methods=["POST"])
def _write(channel: str) -> Response:
    with lock:
        data[channel] = Data(request.get_data(), datetime.now())
    return Response(status=204)


#
# Main
#


def start(host: str, port: int, debug: bool) -> None:
    Thread(target=_periodic_prune, daemon=True).start()
    print(f"Starting server on {host}:{port}")
    if debug:
        app.run(host=host, port=port, debug=True)
    else:
        waitress.serve(app, host=host, port=port)


def main(prog, *args) -> None:
    name = Path(prog).name
    parser = argparse.ArgumentParser(prog=name)
    parser.add_argument("--version", action="version", version=f"{name} {__version__}")
    parser.add_argument("--host", default="0.0.0.0", help="The host waitress will bind to for listening")
    parser.add_argument("port", type=int, help="The port waitress will listen on")
    parser.add_argument("--debug", action="store_true", help="Run in debug mode")
    start(**vars(parser.parse_args(args)))


def cli() -> None:
    main(*sys.argv)


if __name__ == "__main__":
    cli()
