from __future__ import annotations
from logging import getLogger
from typing import cast

from flask import Response, request

from ..shared import WEB_VERSION, DownloadResponseHeaders, DownloadRequestParams, DownloadErrorCode
from .util import log_response, log_params, pipe_full
from .constants import MIN_VERSION
from .globals import streams, lock
from .data import Stream


_LOG: str = "read"


def _check_if_aio(s: Stream, args: DownloadRequestParams) -> Response | None:
    if not args.delete or args.version == WEB_VERSION:
        mode = "web client" if args.delete else "peek"
        if args.stream_id is not None:
            return Response("Stream ID not allowed when using {mode}.", status=DownloadErrorCode.forbidden)
        if not s.new:
            return Response(
                "Another client has already connected to this pipe.", status=DownloadErrorCode.in_use
            )
        if not s.upload_complete:
            if pipe_full(s.data):
                msg = f"Must wait until uploader completes upload when using {mode}"
                return Response(msg, status=DownloadErrorCode.wait)
            msg = f"Too much data to read all at once: when using {mode}; data can only be read all at once."
            return Response(msg, status=DownloadErrorCode.cannot_peek)
    return None


# pylint: disable=too-many-return-statements
def _read_error_check(s: Stream | None, args: DownloadRequestParams) -> Response | None:
    """
    :return: A response if the data in s should not be returned due to an error, else None
    """
    # No data found?
    if s is None:
        return Response("This channel is currently empty", status=DownloadErrorCode.no_data)
    # If data must be all at once, handle it
    if err := _check_if_aio(s, args):
        return err
    # Stream ID check
    if args.stream_id is None and s.new is False:
        return Response("Another client has already connected to this pipe.", status=DownloadErrorCode.in_use)
    if args.stream_id is not None and args.stream_id != s.id_:
        return Response("Stream ID mistmatch", status=DownloadErrorCode.conflict)
    # Web version cannot handle encryption
    if args.version == WEB_VERSION and s.encrypted:
        msg = "Web version cannot read encrypted data. Use the CLI: pip install rpipe"
        return Response(msg, status=422)
    # Version comparison; bypass if web version or override requested
    if args.version not in (WEB_VERSION, s.version) and not args.override:
        msg = f"Override = False. Version should be: {s.version}"
        return Response(msg, status=DownloadErrorCode.wrong_version)
    # Not data currently available
    if not s.upload_complete and not s.data:
        return Response(
            "No data available; wait for the uploader to send more", status=DownloadErrorCode.wait
        )
    return None


@log_response(_LOG)
def read(channel: str) -> Response:
    """
    Get the data from channel, delete it afterwards if required
    If web version: Fail if not encrypted, bypass version checks
    Otherwise: Version check
    """
    args = DownloadRequestParams.from_dict(request.args)
    log_params(getLogger(_LOG), args)
    if args.version != WEB_VERSION and (args.version < MIN_VERSION or args.version.invalid()):
        return Response(f"Bad version. Requires >= {MIN_VERSION}", status=DownloadErrorCode.illegal_version)
    with lock:
        s: Stream | None = streams.get(channel, None)
        if (err := _read_error_check(s, args)) is not None:
            return err
        s = cast(Stream, s)  # For type checker
        # Read all at once if required
        if not args.delete or args.version == WEB_VERSION:
            final = True
            rdata = b"".join(s.data)
        # Read mode
        else:
            rdata = s.data.popleft()
            s.new = False
            final = s.upload_complete and not s.data
        if args.delete and final:
            del streams[channel]
    headers = DownloadResponseHeaders(encrypted=s.encrypted, stream_id=s.id_, final=final).to_dict()
    return Response(rdata, headers=headers)
