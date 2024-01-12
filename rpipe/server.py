from typing import NamedTuple, TYPE_CHECKING
from datetime import datetime, timedelta
from threading import Thread, RLock
from pathlib import Path
import argparse
import time
import sys

from flask import Flask, Response, request
import waitress

from ._shared import WriteCode, ReadCode, Headers
from ._version import __version__

if TYPE_CHECKING:
    from werkzeug.datastructures import Headers as HeadersType


MIN_CLIENT_VERSION = (3, 0, 0)


#
# Types
#


class Data(NamedTuple):
    """
    A timestamped bytes class
    """

    data: bytes
    when: datetime
    client_version: tuple[int, int, int]


#
# Globals
#


data: dict[str, Data] = {}
lock = RLock()

app = Flask(__name__)
app.url_map.strict_slashes = False

PRUNE_PERIOD: int = 60


#
# Helpers
#


def _version_to_tuple(version: str) -> tuple[int, int, int]:
    ret = tuple(int(i) for i in version.split("."))
    if len(ret) != 3:
        raise ValueError("Bad version")
    return ret


def _version_from_tuple(version: tuple[int, int, int]) -> str:
    return ".".join(str(i) for i in version)


def _check_required_version(client_version: str) -> Response | None:
    if not client_version:
        return Response("Try updating your client", status=WriteCode.missing_version)
    try:
        if _version_to_tuple(client_version) < MIN_CLIENT_VERSION:
            raise ValueError()
    except (AttributeError, ValueError):
        return Response(_version_from_tuple(MIN_CLIENT_VERSION), status=WriteCode.illegal_version)
    return None


def _get(channel: str, headers: "HeadersType", delete: bool) -> Response:
    client_version: str = headers.get(Headers.client_version, "")
    if (ret := _check_required_version(client_version)) is not None:
        return ret
    with lock:
        got: Data | None = data.get(channel, None)
        if got is None:
            return Response(f"No data on channel {channel}", status=ReadCode.no_data)
        if _version_to_tuple(client_version) != got.client_version:
            if headers.get(Headers.version_override, "") != "True":
                return Response(_version_from_tuple(got.client_version), status=ReadCode.wrong_version)
        if got is not None and delete:
            del data[channel]
    return Response(got.data, status=ReadCode.ok)


def _periodic_prune() -> None:
    prune_age = timedelta(minutes=5)
    while True:
        old: datetime = datetime.now() - prune_age
        with lock:
            for i in [i for i, k in data.items() if k.when < old]:
                del data[i]
        time.sleep(PRUNE_PERIOD)


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


@app.route("/version")
def _show_version() -> str:
    return __version__


@app.route("/clear/<channel>")
def _clear(channel: str) -> Response:
    with lock:
        if channel in data:
            del data[channel]
    return Response(status=202)


@app.route("/peek/<channel>")
def _peek(channel: str) -> Response:
    return _get(channel, request.headers, False)


@app.route("/read/<channel>")
def _read(channel: str) -> Response:
    return _get(channel, request.headers, True)


@app.route("/write/<channel>", methods=["POST"])
def _write(channel: str) -> Response:
    client_version: str = request.headers.get(Headers.client_version, "")
    if (ret := _check_required_version(client_version)) is not None:
        return ret
    with lock:
        data[channel] = Data(request.get_data(), datetime.now(), _version_to_tuple(client_version))
    return Response(status=WriteCode.ok)


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
    parser.add_argument(
        "--min-client-version",
        action="version",
        version=f"rpipe>={_version_from_tuple(MIN_CLIENT_VERSION)}",
        help="Print the minimum supported client version then exit",
    )
    parser.add_argument("port", type=int, help="The port waitress will listen on")
    parser.add_argument("--host", default="0.0.0.0", help="The host waitress will bind to for listening")
    parser.add_argument("--debug", action="store_true", help="Run in debug mode")
    start(**vars(parser.parse_args(args)))


def cli() -> None:
    main(*sys.argv)


if __name__ == "__main__":
    cli()
