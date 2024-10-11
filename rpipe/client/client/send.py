from __future__ import annotations
from typing import TYPE_CHECKING
from logging import getLogger
from time import sleep
import sys

from ...shared import (
    MAX_SOFT_SIZE_MIN,
    LFS,
    UploadRequestParams,
    UploadResponseHeaders,
    UploadEC,
    version,
)
from .errors import MultipleClients, ReportThis, VersionError
from .util import wait_delay_sec, request, channel_url
from .delete import DeleteOnFail
from .crypt import encrypt
from .pbar import PBar
from .io import IO

if TYPE_CHECKING:
    from collections.abc import Callable
    from requests import Response
    from ..config import Config


_LOG = "send"


def _send_known_error(r: Response) -> None:
    """
    Raise an exception according to the send response error
    If error is unknown, does nothing
    """
    match r.status_code:
        case UploadEC.illegal_version:
            raise VersionError(r.text)
        case UploadEC.conflict:
            raise MultipleClients("The stream ID changed mid-upload; maybe the receiver broke the pipe?")
        case UploadEC.wrong_version | UploadEC.too_big | UploadEC.forbidden | UploadEC.stream_id:
            raise ReportThis(r.text)


def _send_block(data: bytes, config: Config, params: UploadRequestParams, *, lvl: int = 0) -> Response:
    """
    Upload the given block of data; updates params for next block
    """
    typ = "POST" if params.stream_id is None else "PUT"
    r = request(typ, channel_url(config), params=params.to_dict(), data=data)
    if r.ok:
        return r
    elif r.status_code == UploadEC.wait:
        delay = wait_delay_sec(lvl)
        getLogger(_LOG).info("Pipe full, sleeping for %s second(s).", delay)
        sleep(delay)
        return _send_block(data, config, params, lvl=lvl + 1)
    else:
        _send_known_error(r)
        raise RuntimeError(f"Error {r.status_code}", r.text)


def _send(
    config: Config, io: IO, compress: Callable[[bytes], bytes], params: UploadRequestParams, pbar: PBar
) -> None:
    log = getLogger(_LOG)
    while not params.final:
        block, params.final = io.read()
        log.info("Processing block of %s", LFS(block))
        enc = encrypt(block, compress, config.password)
        r = _send_block(enc, config, params)
        pbar.update(len(block))
        if params.stream_id is None:  # Configure following PUTs
            if params.final:
                return
            headers = UploadResponseHeaders.from_dict(r.headers)
            params.stream_id = headers.stream_id
            io.increase_chunk(headers.max_size)
            sleep(0.025)  # Avoid being over-eager with sending data; let the read thread read


def send(config: Config, ttl: int | None, progress: bool | int, compress: Callable[[bytes], bytes]) -> None:
    """
    Send data to the remote pipe
    """
    log = getLogger(_LOG)
    io = IO(sys.stdin.fileno(), MAX_SOFT_SIZE_MIN)
    sleep(0.025)  # Avoid being over-eager with sending data; let the read thread read
    params = UploadRequestParams(
        version=version,
        final=False,
        ttl=ttl,
        encrypted=config.password is not None,
    )
    log.info("Writing to channel %s", config.channel)
    with PBar(progress) as pbar:
        with DeleteOnFail(config):
            _send(config, io, compress, params, pbar)
    log.info("Stream complete")
