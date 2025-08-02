from __future__ import annotations
from typing import TYPE_CHECKING
from dataclasses import replace
from logging import getLogger
from time import sleep
import tarfile
import sys

from zstandard import ZstdCompressor

from ...shared import (
    MAX_SOFT_SIZE_MIN,
    LFS,
    UploadRequestParams,
    UploadResponseHeaders,
    UploadEC,
    mk_temp_f,
    version,
)
from .errors import MultipleClients, ChannelLocked, ReportThis, VersionError
from .util import wait_delay_sec, request
from .progress import Progress
from .crypt import encrypt
from .io import IO

if TYPE_CHECKING:
    from requests import Response
    from collections.abc import Callable
    from .data import Result, Config, Mode


_LOG = "send"
_DEFAULT_LVL: int = 3


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
        case UploadEC.locked:
            raise ChannelLocked(r.text)


def _send_block(data: bytes, conf: Config, params: UploadRequestParams, *, lvl: int = 0) -> Response:
    """
    Upload the given block of data; updates params for next block
    """
    typ = "POST" if params.stream_id is None else "PUT"
    r = request(typ, conf.channel_url(), params=params.to_dict(), data=data, timeout=conf.timeout)
    if r.ok:
        return r
    if r.status_code == UploadEC.wait:
        delay = wait_delay_sec(lvl)
        getLogger(_LOG).info("Pipe full, sleeping for %s second(s).", delay)
        sleep(delay)
        return _send_block(data, conf, params, lvl=lvl + 1)
    _send_known_error(r)
    raise RuntimeError(f"Error {r.status_code}", r.text)


def _send_data(
    conf: Config, progress: Progress, io: IO, compress: Callable[[bytes], bytes], params: UploadRequestParams
) -> None:
    """
    Send data to the remote pipe, using the preconfigured parameters provided
    """
    log = getLogger(_LOG)
    while not params.final:
        block, params.final = io.read()
        log.info("Processing block of %s", LFS(block))
        enc = encrypt(block, compress, conf.password)
        r = _send_block(enc, conf, params)
        progress.update(block)
        if params.stream_id is None:  # configure following PUTs
            if params.final:
                return
            headers = UploadResponseHeaders.from_dict(r.headers)
            params.stream_id = headers.stream_id
            io.increase_chunk(headers.max_size)
            sleep(0.025)  # Avoid being over-eager with sending data; let the read thread read


def _send(conf: Config, mode: Mode, fd: int) -> Result:
    """
    Send data to the remote pipe reading from fd fd
    """
    log = getLogger(_LOG)
    lvl = _DEFAULT_LVL if mode.zstd is None else mode.zstd
    log.debug("Using compression level %d and %d threads", lvl, mode.threads)
    compress = ZstdCompressor(write_checksum=True, level=lvl, threads=mode.threads).compress
    io = IO(fd, MAX_SOFT_SIZE_MIN)
    sleep(0.025)  # Avoid being over-eager with sending data; let the read thread read
    params = UploadRequestParams(
        version=version,
        final=False,
        ttl=mode.ttl,
        encrypted=conf.password is not None,
    )
    log.info("Writing to channel %s", conf.channel)
    with Progress(conf, mode) as progress:
        _send_data(conf, progress, io, compress, params)
    log.info("Stream complete")
    return progress.result


def send(conf: Config, mode: Mode) -> Result:
    """
    Send data to the remote pipe
    """
    log = getLogger(_LOG)
    # Tarball dir
    old = mode
    if mode.dir is not None:
        if not mode.dir.is_dir():
            raise FileNotFoundError(f"Upload directory missing: {mode.dir}")
        temp_f = mk_temp_f(suffix=f" {mode.dir}.tar.gz")
        log.info("Adding dir %s to tarball %s", mode.dir, temp_f)
        with tarfile.open(temp_f, mode="w:gz") as tb:
            tb.add(mode.dir, recursive=True)
        mode = replace(mode, dir=None, file=temp_f)
    # Update progress
    if mode.file and not mode.progress:
        size = mode.file.stat().st_size
        log.debug("Setting: --progress %d", size)
        mode = replace(mode, progress=size)
    # Send file
    with mode.file.open("rb") if mode.file else sys.stdin as fp:
        ret = _send(conf, mode, fp.fileno())
    if old.dir:
        log.debug("Removing tarball %s", mode.file)
        temp_f.unlink()
    return ret
