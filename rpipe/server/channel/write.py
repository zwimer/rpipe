from __future__ import annotations
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, cast
from collections import deque
import logging

from flask import request

from ...shared import WEB_VERSION, UploadResponseHeaders, UploadRequestParams, UploadErrorCode
from ..util import MIN_VERSION, MAX_SIZE_HARD, MAX_SIZE_SOFT, plaintext
from .util import log_response, log_params
from ..server import Stream

if TYPE_CHECKING:
    from logging import Logger
    from flask import Response
    from ..server import State


DEFAULT_TTL: int = 300
_LOG = "write"


def _hsize(n: int) -> str:
    """
    Convert n (number of bytes) into a string such as: 12.3 MiB
    """
    sizes = (("GiB", 2**30), ("MiB", 2**20), ("KiB", 2**10))
    for i, k in sizes:
        if n > k:
            return f"{n/k:.2f} {i}"
    return f"{n} B"


def _log_pipe_size(log: Logger, s: Stream) -> None:
    if log.isEnabledFor(logging.DEBUG):
        n = len(s)
        msg = "Pipe now contains %s/%s bytes. It is %.2f%% full."
        log.debug(msg, _hsize(n), _hsize(s.capacity), 100 * n / s.capacity)


def _put_error_check(s: Stream | None, args: UploadRequestParams) -> Response | None:
    if s is None or s.id_ != args.stream_id:
        return plaintext("Stream ID mismatch.", UploadErrorCode.conflict)
    if s.upload_complete:
        return plaintext("Cannot write to a completed stream.", UploadErrorCode.forbidden)
    if args.version != s.version and not args.override:
        return plaintext(f"Override = False. Version should be: {s.version}", UploadErrorCode.wrong_version)
    if s.full():
        return plaintext("Pipe full; wait for the downloader to download more.", UploadErrorCode.wait)
    return None


# pylint: disable=too-many-return-statements
@log_response(_LOG)
def write(state: State, channel: str) -> Response:
    args = UploadRequestParams.from_dict(request.args)
    log = logging.getLogger(_LOG)
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
        with state as rw_state:
            new = Stream(
                data=deque([] if not add else [add]),
                expire=datetime.now() + timedelta(seconds=DEFAULT_TTL if args.ttl is None else args.ttl),
                encrypted=args.encrypted,
                version=args.version,
                upload_complete=args.final,
            )
            rw_state.streams[channel] = new
            headers = UploadResponseHeaders(stream_id=new.id_, max_size=MAX_SIZE_SOFT)
        return plaintext("", 201, headers=headers.to_dict())
    # Continuing an existing stream, stream ID should be present
    if args.stream_id is None:
        return plaintext("PUT request missing stream id", UploadErrorCode.stream_id)
    with state as rw_state:
        s: Stream | None = rw_state.streams.get(channel, None)
        if (err := _put_error_check(s, args)) is not None:
            return err
        if TYPE_CHECKING:
            s = cast(Stream, s)  # For type checker
        s.upload_complete = args.final
        if add:
            s.data.append(add)
            _log_pipe_size(log, s)
        headers = UploadResponseHeaders(stream_id=s.id_, max_size=MAX_SIZE_SOFT)
    return plaintext("", 202, headers=headers.to_dict())