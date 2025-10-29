from typing import TYPE_CHECKING, cast
from collections import deque
from logging import getLogger

from flask import Response, request

from ...shared import (
    WEB_VERSION,
    DownloadResponseHeaders,
    DownloadRequestParams,
    DownloadEC,
    total_len,
    TRACE,
    LFS,
)
from ..util import MIN_VERSION, MAX_SIZE_SOFT, plaintext
from .util import log_response, log_params

if TYPE_CHECKING:
    from collections.abc import Sequence
    from ..server import Stream
    from ..server import State


_LOG: str = "read"


def _check_if_aio(s: Stream, args: DownloadRequestParams) -> Response | None:
    if not args.delete or args.version == WEB_VERSION:
        mode = "web client" if args.delete else "peek"
        if args.stream_id is not None:
            return plaintext("Stream ID not allowed when using {mode}.", DownloadEC.forbidden)
        if not s.new:
            return plaintext("Another client has already connected to this pipe.", DownloadEC.in_use)
        if not s.upload_complete:
            if s.full():
                msg = f"Must wait until uploader completes upload when using {mode}"
                return plaintext(msg, DownloadEC.wait)
            msg = f"Too much data to read all at once: when using {mode}; data can only be read all at once."
            return plaintext(msg, DownloadEC.cannot_peek)
    return None


# pylint: disable=too-many-return-statements
def _read_error_check(s: Stream | None, args: DownloadRequestParams) -> Response | None:
    """
    :return: A response if the data in s should not be returned due to an error, else None
    """
    # No data found?
    if s is None:
        return plaintext("This channel is currently empty", DownloadEC.no_data)
    # If data must be all at once, handle it
    if err := _check_if_aio(s, args):
        return err
    # Stream ID check
    if args.stream_id is None and s.new is False:
        return plaintext("Another client has already connected to this pipe.", DownloadEC.in_use)
    if args.stream_id is not None and args.stream_id != s.id_:
        return plaintext("Stream ID mismatch", DownloadEC.conflict)
    # Web version cannot handle encryption
    if args.version == WEB_VERSION and s.encrypted:
        return plaintext("Web version cannot read encrypted data. Use the CLI: pip install rpipe", 422)
    # Version comparison; bypass if web version or override requested
    if args.version not in (WEB_VERSION, s.version) and not args.override:
        return plaintext(f"Override = False. Version should be: {s.version}", DownloadEC.wrong_version)
    # Not data currently available
    if not s.upload_complete and not s.data:
        return plaintext("No data available; wait for the uploader to send more", DownloadEC.wait)
    # Lock check
    if s.locked and args.delete:
        return plaintext("This channel is locked and cannot be edited; consider --peek", DownloadEC.locked)
    return None


@log_response(_LOG)
def read(state: State, channel: str) -> Response:
    """
    Get the data from channel, delete it afterward if required
    If web version: Fail if not encrypted, bypass version checks
    Otherwise: Version check
    """
    log = getLogger(_LOG)
    args = DownloadRequestParams.from_dict(request.args)
    log_params(log, args)
    if args.version != WEB_VERSION and (args.version < MIN_VERSION or args.version.invalid()):
        return plaintext(f"Bad version. Server requires >= {MIN_VERSION}", DownloadEC.illegal_version)
    with state as u:
        s: Stream | None = u.streams.get(channel, None)
        if (err := _read_error_check(s, args)) is not None:
            return err
        if TYPE_CHECKING:
            s = cast(Stream, s)  # For type checker
        # Read all at once if required
        if not args.delete:  # Peek mode (could also be web version)
            log.debug("Reading channel %s in peek mode", channel)
            u.stats.peek(channel)
            rdata: Sequence[bytes] = s.data
            final = True
        elif args.version == WEB_VERSION:
            log.debug("Reading channel %s from WEB_VERSION", channel)
            u.stats.read(channel)
            rdata = s.data
            s.data = deque()
            final = True
        # Standard read mode
        else:
            log.log(TRACE, "Reading channel %s in standard mode", channel)
            if s.new:
                s.new = False
                u.stats.read(channel)
            rdata = [s.data.popleft()] if s.data else []  # Ensure at least one packet if available
            while s.data and (len(s.data[0]) + total_len(rdata)) < MAX_SIZE_SOFT:
                rdata.append(s.data.popleft())
            final = s.upload_complete and not s.data
        if args.delete and final:
            log.debug("Channel %s empty and final; removing", channel)
            del u.streams[channel]
    log.log(TRACE, "Merging %d piece(s) of data; total length: %s", len(rdata), LFS(rdata))
    headers = DownloadResponseHeaders(encrypted=s.encrypted, stream_id=s.id_, final=final).to_dict()
    return Response(b"".join(rdata), mimetype="application/octet-stream", headers=headers)
