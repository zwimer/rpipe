from __future__ import annotations
from typing import TYPE_CHECKING
from logging import getLogger
from time import sleep
import sys

from ..version import version
from ..shared import UploadRequestParams, UploadResponseHeaders, UploadErrorCode
from .errors import MultipleClients, ReportThis, VersionError
from .util import WAIT_DELAY_SEC, request, channel_url
from .crypt import encrypt
from .io import IO

if TYPE_CHECKING:
    from requests import Response
    from .config import Config


_LOG = "send"


def _send_error(r: Response) -> None:
    """
    Raise an exception according to the send response error
    """
    match r.status_code:
        case UploadErrorCode.illegal_version:
            raise VersionError(f"Server requires version >= {r.text}")
        case UploadErrorCode.conflict:
            raise MultipleClients("The stream ID changed mid-upload; maybe the channel was cleared?")
        case UploadErrorCode.wrong_version | UploadErrorCode.too_big | UploadErrorCode.forbidden | UploadErrorCode.stream_id:
            raise ReportThis(r.text)
        case _:
            raise RuntimeError(r)


def _send_block(data: bytes, config: Config, params: UploadRequestParams) -> None:
    """
    Upload the given block of data; updates params for next block
    """
    r = request("PUT", channel_url(config), params=params.to_dict(), data=data)
    if r.ok:
        headers = UploadResponseHeaders.from_dict(r.headers)
        assert params.stream_id == headers.stream_id
    elif r.status_code == UploadErrorCode.wait:
        getLogger(_LOG).debug("Pipe full, sleeping for %s seconds.", WAIT_DELAY_SEC)
        sleep(WAIT_DELAY_SEC)
        _send_block(data, config, params)
    else:
        _send_error(r)


def send(config: Config) -> None:
    """
    Send data to the remote pipe
    """
    # Open stream and get block size
    params = UploadRequestParams(version=version, final=False, encrypted=config.password is not None)
    r = request("POST", channel_url(config), params=params.to_dict(), data="")
    if not r.ok:
        raise RuntimeError(r)
    headers = UploadResponseHeaders.from_dict(r.headers)
    block_size: int = headers.max_size
    log = getLogger(_LOG)
    log.debug("Writing to channel %s with block size of %s", config.channel, block_size)
    # Send
    params.stream_id = headers.stream_id
    io = IO(sys.stdin.fileno(), block_size)
    while block := io.read():
        _send_block(encrypt(block, config.password), config, params)
    # Finalize
    params.final = True
    try:
        _send_block(b"", config, params)
    except MultipleClients:  # We might have hung after sending our data until the program closed
        log.debug("Received MultipleClients error on final PUT")
    log.debug("Stream complete")
