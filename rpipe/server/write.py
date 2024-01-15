from collections import deque
from datetime import datetime
from logging import getLogger
from typing import cast
import random
import string

from flask import Response, request

from ..shared import WEB_VERSION, UploadResponseHeaders, UploadRequestParams, UploadErrorCode
from .util import log_response, log_params, log_pipe_size, pipe_full
from .constants import MAX_SIZE_HARD, MAX_SIZE_SOFT, MIN_VERSION
from .globals import lock, streams
from .data import Stream


CHARSET = string.ascii_lowercase + string.ascii_uppercase + string.digits
_LOG = "write"


def _put_error_check(s: Stream | None, args: UploadRequestParams) -> Response | None:
    if s is None or s.id_ != args.stream_id:
        return Response("Stream ID mistmatch.", status=UploadErrorCode.conflict)
    if s.upload_complete:
        return Response("Cannot write to a completed stream.", status=UploadErrorCode.forbidden)
    if args.version != s.version and not args.override:
        msg = f"Override = False. Version should be: {s.version}"
        return Response(msg, status=UploadErrorCode.wrong_version)
    if pipe_full(s.data):
        return Response("Pipe full; wait for the downloader to download more.", status=UploadErrorCode.wait)
    return None


# pylint: disable=too-many-return-statements
@log_response(_LOG)
def write(channel: str) -> Response:
    args = UploadRequestParams.from_dict(request.args)
    log = getLogger(_LOG)
    log_params(log, args)
    # Version and size check
    if args.version != WEB_VERSION and (args.version < MIN_VERSION or args.version.invalid()):
        return Response(f"Bad version. Requires >= {MIN_VERSION}", status=UploadErrorCode.illegal_version)
    add = request.get_data()
    if len(add) > MAX_SIZE_HARD:
        return Response(f"Too much data sent. Max data size: {MAX_SIZE_SOFT}", status=UploadErrorCode.too_big)
    # Starting a new stream, no stream ID should be present
    if request.method == "POST":
        if args.stream_id is not None:
            return Response("POST request should not have a stream_id", status=UploadErrorCode.stream_id)
        with lock:
            sid = "".join(random.choices(CHARSET, k=32))
            streams[channel] = Stream(
                data=deque([] if not add else [add]),
                when=datetime.now(),
                encrypted=args.encrypted,
                version=args.version,
                upload_complete=args.final,
                id_=sid,
            )
        headers = UploadResponseHeaders(stream_id=sid, max_size=MAX_SIZE_SOFT)
        return Response(status=201, headers=headers.to_dict())
    if args.stream_id is None:
        return Response("PUT request missing stream id", status=UploadErrorCode.stream_id)
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
    return Response(status=202, headers=headers.to_dict())
