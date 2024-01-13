from __future__ import annotations
from typing import NamedTuple, TYPE_CHECKING
from datetime import datetime, timedelta
from threading import Thread, RLock
from pathlib import Path
import argparse
import time
import sys

from flask import Flask, Response, request, redirect
import waitress

from ._shared import WriteCode, ReadCode, Headers
from ._version import __version__

if TYPE_CHECKING:
    from werkzeug.datastructures import Headers as HeadersType
    from werkzeug.wrappers import Response as BaseResponse


#
# Globals
#


data: dict[str, Data] = {}
lock = RLock()

app = Flask(__name__)

MIN_CLIENT_VERSION = (3, 0, 0)
WEB_VERSION = "0.0.0"
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


def _version_to_tuple(version: str) -> tuple[int, int, int]:
    ret = tuple(int(i) for i in version.split("."))
    if len(ret) != 3:
        raise ValueError("Bad version")
    return ret


def _version_from_tuple(version: tuple[int, int, int]) -> str:
    return ".".join(str(i) for i in version)


def _check_required_version(client_version: str) -> Response | None:
    """
    :param client_version: The version to check
    :return: A flask Response if the version is not acceptable
    """
    if not client_version:
        return Response("Try updating your client or visit /help if using a browser", status=WriteCode.missing_version)
    try:
        if _version_to_tuple(client_version) < MIN_CLIENT_VERSION:
            raise ValueError()
    except (AttributeError, ValueError):
        return Response(_version_from_tuple(MIN_CLIENT_VERSION), status=WriteCode.illegal_version)
    return None


def _get(channel: str, path: str, headers: HeadersType, delete: bool) -> Response:
    """
    Get the data from channel, delete it afterwards if required
    If web version: Fail if not encrypted, bypass version checks
    If non web-version, but should be: redirect to web version
    Otherwise: Version check
    """
    # Redirect non-client requests to the web version and mark the version as the web version
    if Headers.client_version not in request.headers:
        if not path.startswith("/web"):
            return redirect(f"/web{path}", code=308)  # type: ignore
        client_version = WEB_VERSION
    # For client requests, verify the version is new enough to accept
    else:
        client_version = headers.get(Headers.client_version, "")
        if (ret := _check_required_version(client_version)) is not None:
            return ret
    # Read data from the channel
    with lock:
        got: Data | None = data.get(channel, None)
        # No data found?
        if got is None:
            return Response(f"No data on channel {channel}", status=ReadCode.no_data)
        # Web version cannot handle encryption
        if client_version == WEB_VERSION and got.encrypted:
            return Response("Web version cannot read encrypted data. Use the CLI: pip install rpipe", status=422)
        # Version comparison; bypass if web version or override requested
        got_ver = _version_from_tuple(got.client_version)
        if client_version not in (WEB_VERSION, got_ver):
            if headers.get(Headers.version_override, "") != "True":
                return Response(got_ver, status=ReadCode.wrong_version)
        # Delete data from channel if needed
        if got is not None and delete:
            del data[channel]
    return Response(got.data, headers={Headers.encrypted: str(got.encrypted)}, status=ReadCode.ok)


def _periodic_prune() -> None:
    """
    Remove items added to rpipe too long ago
    """
    prune_age = timedelta(minutes=PRUNE_DELAY)
    while True:
        old: datetime = datetime.now() - prune_age
        with lock:
            for i in [i for i, k in data.items() if k.when < old]:
                del data[i]
        time.sleep(60)


#
# Routes
#


@app.route("/")
@app.route("/web")
@app.route("/help")
@app.route("/web/help")
def _help() -> str:
    return (
        "Write to /web/write, read from /web/read or /web/peek, clear with "
        "/web/clear; add a trailing /<channel> to specify the channel. "
        "Note: Using the /web/ API bypasses version consistenct checks "
        "and may result in safe but unexpected behavior (such as failing "
        "an uploaded message; if possible use the rpipe CLI instead. "
        "Install the CLI via: pip install rpipe"
    )


@app.route("/version")
def _show_version() -> str:
    return __version__


@app.route("/clear/<channel>")
@app.route("/web/clear/<channel>")
def _clear(channel: str) -> BaseResponse:
    if Headers.client_version not in request.headers:
        if not request.path.startswith("/web"):
            return redirect(f"/web{request.path}", code=308)
    with lock:
        if channel in data:
            del data[channel]
    return Response("Cleared", status=202)


@app.route("/peek/<channel>")
@app.route("/web/peek/<channel>")
def _peek(channel: str) -> BaseResponse:
    return _get(channel, request.path, request.headers, False)


@app.route("/read/<channel>")
@app.route("/web/read/<channel>")
def _read(channel: str) -> BaseResponse:
    return _get(channel, request.path, request.headers, True)


@app.route("/write/<channel>", methods=["POST"])
@app.route("/web/write/<channel>", methods=["POST"])
def _write(channel: str) -> BaseResponse:
    # Redirect non-client requests to web API, variables for web usage
    if Headers.client_version not in request.headers:
        if not request.path.startswith("/web"):
            return redirect(f"/web{request.path}", code=308)
        client_version = WEB_VERSION
        encrypted = False
    # Version check client, determine if message is encrypted
    else:
        client_version = request.headers.get(Headers.client_version, "")
        if (ret := _check_required_version(client_version)) is not None:
            return ret
        encrypted = request.headers.get(Headers.encrypted, "False") == "True"
    # Store the uploaded data
    with lock:
        data[channel] = Data(request.get_data(), datetime.now(), encrypted, _version_to_tuple(client_version))
    return Response(status=WriteCode.ok)


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
