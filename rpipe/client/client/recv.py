from __future__ import annotations
from typing import TYPE_CHECKING
from logging import getLogger
from time import sleep
import sys

from zstandard import ZstdDecompressor

from ...shared import DownloadRequestParams, DownloadResponseHeaders, DownloadEC, LFS, version
from .errors import MultipleClients, ReportThis, VersionError, StreamError, NoData
from .util import wait_delay_sec, request, channel_url
from .delete import DeleteOnFail
from .crypt import decrypt
from .pbar import PBar

if TYPE_CHECKING:
    from requests import Response
    from ..config import Config


_LOG = "recv"


# pylint: disable=too-many-arguments
def _recv_error_helper(r: Response, config: Config, peek: bool, put: bool, waited: bool) -> None:
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
            raise NoData(f"The channel {config.channel} is empty.")
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


def _recv_body(
    config: Config,
    block: bool,
    peek: bool,
    url: str,
    params: DownloadRequestParams,
    pbar: PBar,
    lvl: int,
    dof: DeleteOnFail,
) -> int | None:
    log = getLogger(_LOG)
    decompress = ZstdDecompressor().decompress
    r = request("GET", url, params=params.to_dict())
    if r.ok:
        dof.armed = True
        headers = DownloadResponseHeaders.from_dict(r.headers)
        log.info("Received %s", LFS(r.content))
        got: bytes = decrypt(r.content, decompress, config.password if headers.encrypted else None)
        sys.stdout.buffer.write(got)
        sys.stdout.flush()
        pbar.update(len(got))
        if headers.final:
            return None  # Stream complete
        params.stream_id = headers.stream_id
        return 0
    elif (block and r.status_code == DownloadEC.no_data) or (r.status_code == DownloadEC.wait):
        delay = wait_delay_sec(lvl)
        log.info("No data available yet, sleeping for %s second(s)", delay)
        sleep(delay)
        return lvl + 1
    else:
        log.error("Error reading from channel %s. Status Code: %s", config.channel, r.status_code)
        _recv_error(r, config, peek, params.stream_id is not None, lvl != 0)
        raise NotImplementedError("Unreachable code")


def recv(config: Config, block: bool, peek: bool, force: bool, progress: bool | int) -> None:
    """
    Receive data from the remote pipe
    """
    log = getLogger(_LOG)
    url = channel_url(config)
    log.info("Reading from channel %s with peek=%s and force=%s", config.channel, peek, force)
    params = DownloadRequestParams(version=version, override=force, delete=not peek)
    lvl: int | None = 0
    try:
        with DeleteOnFail(config) as dof:
            with PBar(progress) as pbar:
                while lvl is not None:
                    if (lvl := _recv_body(config, block, peek, url, params, pbar, lvl, dof)) == 0:
                        block = False  # Stop blocking after first successful read
    except BrokenPipeError:
        log.warning("BrokenPipeError: stdout pipe closed")
    else:
        log.info("Stream complete")
