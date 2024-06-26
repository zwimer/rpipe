from __future__ import annotations
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, cast
from collections import deque
from logging import getLogger

from flask import request

from ..shared import WEB_VERSION, UploadResponseHeaders, UploadRequestParams, UploadErrorCode
from .util import plaintext, log_response, log_params, log_pipe_size, pipe_full
from .constants import MAX_SIZE_HARD, MAX_SIZE_SOFT, MIN_VERSION
from .globals import lock, streams
from .data import Stream

if TYPE_CHECKING:
    from flask import Response


_LOG = "write"

DEFAULT_TTL: int = 300


def _put_error_check(s: Stream | None, args: UploadRequestParams) -> Response | None:
    if s is None or s.id_ != args.stream_id:
        return plaintext("Stream ID mismatch.", UploadErrorCode.conflict)
    if s.upload_complete:
        return plaintext("Cannot write to a completed stream.", UploadErrorCode.forbidden)
    if args.version != s.version and not args.override:
        return plaintext(f"Override = False. Version should be: {s.version}", UploadErrorCode.wrong_version)
    if pipe_full(s.data):
        return plaintext("Pipe full; wait for the downloader to download more.", UploadErrorCode.wait)
    return None


# pylint: disable=too-many-return-statements
@log_response(_LOG)
def write(channel: str) -> Response:
    args = UploadRequestParams.from_dict(request.args)
    log = getLogger(_LOG)
    log_params(log, args)
    # Version and size check
    if args.version != WEB_VERSION and (args.version < MIN_VERSION or args.version.invalid()):
        return plaintext(f"Bad version. Requires >= {MIN_VERSION}", UploadErrorCode.illegal_version)
    add = request.get_data()
    if len(add) > MAX_SIZE_HARD:
        return plaintext(f"Too much data sent. Max data size: {MAX_SIZE_SOFT}", UploadErrorCode.too_big)
    # Starting a new stream, no stream ID should be present
    if request.method == "POST":
        if args.stream_id is not None:
            return plaintext("POST request should not have a stream_id", UploadErrorCode.stream_id)
        with lock:
            new = Stream(
                data=deque([] if not add else [add]),
                expire=datetime.now() + timedelta(seconds=DEFAULT_TTL if args.ttl is None else args.ttl),
                encrypted=args.encrypted,
                version=args.version,
                upload_complete=args.final,
            )
            streams[channel] = new
            headers = UploadResponseHeaders(stream_id=new.id_, max_size=MAX_SIZE_SOFT)
        return plaintext("", 201, headers=headers.to_dict())
    if args.stream_id is None:
        return plaintext("PUT request missing stream id", UploadErrorCode.stream_id)
    with lock:
        s: Stream | None = streams.get(channel, None)
        if (err := _put_error_check(s, args)) is not None:
            return err
        s = cast(Stream, s)  # For type checker
        s.upload_complete = args.final
        if add:
            s.data.append(add)
            log_pipe_size(log, s.data)
        headers = UploadResponseHeaders(stream_id=s.id_, max_size=MAX_SIZE_SOFT)
    return plaintext("", 202, headers=headers.to_dict())
