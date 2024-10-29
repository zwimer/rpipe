from __future__ import annotations
from typing import TYPE_CHECKING
from logging import getLogger
from time import sleep

from zstandard import ZstdDecompressor

from ...shared import DownloadRequestParams, DownloadResponseHeaders, DownloadEC, LFS, version
from .errors import MultipleClients, ChannelLocked, ReportThis, VersionError, StreamError, NoData
from .util import wait_delay_sec, request
from .progress import Progress
from .crypt import decrypt

if TYPE_CHECKING:
    from requests import Response
    from .data import Result, Config, Mode


_LOG = "recv"


# pylint: disable=too-many-arguments
def _recv_error_helper(r: Response, conf: Config, peek: bool, put: bool, waited: bool) -> None:
    """
    Raise an exception according to the recv response error
    """
    match r.status_code:
        case DownloadEC.wrong_version:
            v = r.text.split(":")[-1].strip()
            raise VersionError(f"Version mismatch; uploader version = {v}; force a read with --force")
        case DownloadEC.illegal_version:
            raise VersionError(r.text)
        case DownloadEC.no_data:
            if put:
                msg = "This data stream no longer exists; maybe the sender cancelled sending?"
                raise MultipleClients(msg)
            raise NoData(f"The channel {conf.channel} is empty.")
        case DownloadEC.conflict:
            if put:
                raise MultipleClients("This data stream no longer exists; maybe the channel was deleted?")
            raise ReportThis(r.text)
        case DownloadEC.cannot_peek:
            msg = "Too much data to peek; data is being streamed and does not all exist on server."
            raise StreamError(msg)
        case DownloadEC.in_use:
            if peek and waited:
                raise MultipleClients("Another client started reading the data before peek was complete")
            raise MultipleClients(r.text)
        case DownloadEC.locked:
            raise ChannelLocked(r.text)
        case DownloadEC.forbidden:
            raise ReportThis("Attempt to read from stream with stream ID.")
        case _:
            raise RuntimeError(f"Error {r.status_code}", r.text)


def _recv_error(*args, **kwargs) -> None:
    """
    Wrapper for _recv_error_helper
    """
    try:
        _recv_error_helper(*args, **kwargs)
    except (VersionError, NoData, ReportThis, MultipleClients, RuntimeError) as e:
        getLogger(_LOG).error(", ".join(e.args))
        raise e


# pylint: disable=too-many-positional-arguments
def _recv_body(
    conf: Config,
    progress: Progress,
    block: bool,
    peek: bool,
    params: DownloadRequestParams,
    lvl: int,
) -> int | None:
    log = getLogger(_LOG)
    decompress = ZstdDecompressor().decompress
    r = request("GET", conf.channel_url(), params=params.to_dict(), timeout=conf.timeout)
    if r.ok:
        progress.dof = True
        headers = DownloadResponseHeaders.from_dict(r.headers)
        log.info("Received %s", LFS(r.content))
        got: bytes = decrypt(r.content, decompress, conf.password if headers.encrypted else None)
        progress.update(got, stdout=True)
        if headers.final:
            return None  # Stream complete
        params.stream_id = headers.stream_id
        return 0
    if (block and r.status_code == DownloadEC.no_data) or (r.status_code == DownloadEC.wait):
        delay = wait_delay_sec(lvl)
        log.info("No data available yet, sleeping for %s second(s)", delay)
        sleep(delay)
        return lvl + 1
    log.error("Error reading from channel %s. Status Code: %s", conf.channel, r.status_code)
    _recv_error(r, conf, peek, params.stream_id is not None, lvl != 0)
    raise NotImplementedError("Unreachable code")


def recv(conf: Config, mode: Mode) -> Result:
    """
    Receive data from the remote pipe
    """
    block: bool = mode.block
    log = getLogger(_LOG)
    log.info("Reading from channel %s with peek=%s and force=%s", conf.channel, mode.peek, mode.force)
    params = DownloadRequestParams(version=version, override=mode.force, delete=not mode.peek)
    lvl: int | None = 0
    try:
        with Progress(conf, mode) as progress:
            while lvl is not None:
                if (lvl := _recv_body(conf, progress, block, mode.peek, params, lvl)) == 0:
                    block = False  # Stop blocking after first successful read
    except BrokenPipeError:
        log.warning("BrokenPipeError: stdout pipe closed")
    else:
        log.info("Stream complete")
    return progress.result
