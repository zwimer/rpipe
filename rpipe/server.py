from __future__ import annotations
from typing import NamedTuple, TYPE_CHECKING
from datetime import datetime, timedelta
from threading import Thread, RLock
from pathlib import Path
import argparse
import time
import sys

from flask import Flask, Response, request
import waitress

from ._shared import ENCRYPTED_HEADER, WEB_VERSION, RequestParams, ErrorCode
from ._version import __version__

if TYPE_CHECKING:
    from werkzeug.wrappers import Response as BaseResponse


#
# Globals
#


data: dict[str, Data] = {}
lock = RLock()

app = Flask(__name__)

MIN_VERSION = (4, 0, 0)
PRUNE_DELAY: int = 5


#
# Types
#


class Data(NamedTuple):
    """
    A timestamped bytes class
    """

    data: bytes
    when: datetime
    encrypted: bool
    client_version: tuple[int, int, int]


#
# Helpers
#


def _version_tup(version: str) -> tuple[int, int, int]:
    ret = tuple(int(i) for i in version.split("."))
    if len(ret) != 3:
        raise ValueError("Bad version")
    return ret


def _version_str(version: tuple[int, int, int]) -> str:
    return ".".join(str(i) for i in version)


def _check_version(version: str) -> Response | None:
    """
    :param client_version: The version to check
    :return: A flask Response if the version is not acceptable
    """
    try:
        if _version_tup(version) < MIN_VERSION:
            raise ValueError()
    except (AttributeError, ValueError):
        msg = f"Bad version: {_version_str(MIN_VERSION)}"
        return Response(msg, status=ErrorCode.illegal_version)
    return None


def _get(channel: str, args: RequestParams, delete: bool) -> Response:
    """
    Get the data from channel, delete it afterwards if required
    If web version: Fail if not encrypted, bypass version checks
    Otherwise: Version check
    """
    if args.version != WEB_VERSION and (ret := _check_version(args.version)) is not None:
        return ret
    with lock:
        got: Data | None = data.get(channel, None)
        # No data found?
        if got is None:
            return Response(f"No data on channel {channel}", status=ErrorCode.no_data)
        # Web version cannot handle encryption
        if args.version == WEB_VERSION and got.encrypted:
            msg = "Web version cannot read encrypted data. Use the CLI: pip install rpipe"
            return Response(msg, status=422)
        # Version comparison; bypass if web version or override requested
        got_ver = _version_str(got.client_version)
        if args.version not in (WEB_VERSION, got_ver) and not args.override:
            return Response(got_ver, status=ErrorCode.wrong_version)
        # Delete data from channel if needed
        if got is not None and delete:
            del data[channel]
    return Response(got.data, headers={ENCRYPTED_HEADER: str(got.encrypted)})


def _periodic_prune() -> None:
    """
    Remove items added to rpipe too long ago
    """
    prune_age = timedelta(minutes=PRUNE_DELAY)
    while True:
        old: datetime = datetime.now() - prune_age
        with lock:
            for i, k in data.items():
                if k.when < old:
                    del data[i]
        time.sleep(60)


#
# Routes
#


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


@app.route("/clear/<channel>", methods=["DELETE"])
def _clear(channel: str) -> BaseResponse:
    with lock:
        if channel in data:
            del data[channel]
    return Response("Cleared", status=202)


@app.route("/peek/<channel>")
def _peek(channel: str) -> BaseResponse:
    return _get(channel, RequestParams.from_dict(request.args.to_dict()), False)


@app.route("/read/<channel>")
def _read(channel: str) -> BaseResponse:
    return _get(channel, RequestParams.from_dict(request.args.to_dict()), True)


@app.route("/write/<channel>", methods=["POST"])
def _write(channel: str) -> BaseResponse:
    args = RequestParams.from_dict(request.args.to_dict())
    if args.version != WEB_VERSION and (ret := _check_version(args.version)) is not None:
        return ret
    with lock:
        data[channel] = Data(request.get_data(), datetime.now(), args.encrypted, _version_tup(args.version))
    return Response(status=201)


#
# Main
#


def start(host: str, port: int, debug: bool) -> None:
    Thread(target=_periodic_prune, daemon=True).start()
    app.url_map.strict_slashes = False
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
        version=f"rpipe>={_version_str(MIN_VERSION)}",
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
