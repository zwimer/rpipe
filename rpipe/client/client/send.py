from __future__ import annotations
from typing import TYPE_CHECKING
from logging import getLogger
from time import sleep
import sys

from ...shared import UploadRequestParams, UploadResponseHeaders, UploadErrorCode, version
from .errors import MultipleClients, ReportThis, VersionError
from .util import wait_delay_sec, request, channel_url
from .delete import DeleteOnFail
from .crypt import encrypt
from .pbar import PBar
from .io import IO

if TYPE_CHECKING:
    from requests import Response
    from ..config import Config


_LOG = "send"


def _send_known_error(r: Response) -> None:
    """
    Raise an exception according to the send response error
    """
    match UploadErrorCode(r.status_code):
        case UploadErrorCode.illegal_version:
            raise VersionError(f"Server requires version >= {r.text}")
        case UploadErrorCode.conflict:
            raise MultipleClients("The stream ID changed mid-upload; maybe the receiver broke the pipe?")
        case (
            UploadErrorCode.wrong_version
            | UploadErrorCode.too_big
            | UploadErrorCode.forbidden
            | UploadErrorCode.stream_id
        ):
            raise ReportThis(r.text)


def _send_block(data: bytes, config: Config, params: UploadRequestParams, *, lvl: int = 0) -> Response:
    """
    Upload the given block of data; updates params for next block
    """
    r = request("PUT", channel_url(config), params=params.to_dict(), data=data)
    if r.ok:
        return r
    elif r.status_code == UploadErrorCode.wait.value:
        delay = wait_delay_sec(lvl)
        getLogger(_LOG).info("Pipe full, sleeping for %s second(s).", delay)
        sleep(delay)
        return _send_block(data, config, params, lvl=lvl + 1)
    else:
        _send_known_error(r)
        raise RuntimeError(r)  # Fallback


def _send(config: Config, ttl: int | None, progress: bool | int) -> None:
    log = getLogger(_LOG)
    # Configure params
    params = UploadRequestParams(version=version, final=False, ttl=ttl, encrypted=config.password is not None)
    r = request("POST", channel_url(config), params=params.to_dict())
    if not r.ok:
        raise RuntimeError(r)
    headers = UploadResponseHeaders.from_dict(r.headers)
    params.stream_id = headers.stream_id
    # Send
    eof: bool = False
    io = IO(sys.stdin.fileno(), headers.max_size)
    log.info("Writing to channel %s", config.channel)
    with PBar(progress) as pbar:
        while block := io.read():
            if eof := io.eof():
                params.final = True
            if block:  # Else: no data + EOF
                log.info("Processing block of %s bytes", len(block))
                r = _send_block(encrypt(block, config.password), config, params)
                assert UploadResponseHeaders.from_dict(r.headers).stream_id == params.stream_id
                pbar.update(len(block))
    # Finalize
    if not eof:  # If eof was already set, we've already sent the final header
        assert io.eof()
        params.final = True
        try:
            _send_block(b"", config, params)
        except MultipleClients:  # We might have hung after sending our data until the program closed
            log.warning("Received MultipleClients error on final PUT")


def send(config: Config, ttl: int | None, progress: bool | int) -> None:
    """
    Send data to the remote pipe
    """
    with DeleteOnFail(config):
        _send(config, ttl, progress)
    getLogger(_LOG).info("Stream complete")
