from __future__ import annotations
from typing import TYPE_CHECKING
from logging import getLogger
from time import sleep
import sys

from ..version import version
from ..shared import DownloadRequestParams, DownloadResponseHeaders, DownloadErrorCode
from .errors import MultipleClients, ReportThis, VersionError, StreamError, NoData
from .util import WAIT_DELAY_SEC, request, channel_url
from .crypt import decrypt

if TYPE_CHECKING:
    from requests import Response
    from .config import Config


_LOG = "recv"


# pylint: disable=too-many-arguments
def _recv_error(r: Response, config: Config, peek: bool, put: bool, waited: bool) -> None:
    """
    Raise an exception according to the recv response error
    """
    match r.status_code:
        case DownloadErrorCode.wrong_version:
            v = r.text.split(":")[-1].strip()
            raise VersionError(f"Version mismatch; uploader version = {v}; force a read with --force")
        case DownloadErrorCode.illegal_version:
            raise VersionError(f"Server requires version >= {r.text}")
        case DownloadErrorCode.no_data:
            if put:
                raise MultipleClients("This data stream no longer exists; maybe the channel was cleared?")
            raise NoData(f"The channel {config.channel} is empty.")
        case DownloadErrorCode.conflict:
            if put:
                raise MultipleClients("This data stream no longer exists; maybe the channel was cleared?")
            raise ReportThis(r.text)
        case DownloadErrorCode.cannot_peek:
            msg = "Too much data to peek; data is being streamed and does not all exist on server."
            raise StreamError(msg)
        case DownloadErrorCode.in_use:
            if peek and waited:
                raise MultipleClients("Another client started reading the data before peek was complete")
            raise MultipleClients(r.text)
        case DownloadErrorCode.forbidden:
            raise ReportThis("Attempt to read from stream with stream ID.")
        case _:
            raise RuntimeError(r)


def recv(config: Config, peek: bool, force: bool) -> None:
    """
    Receive data from the remote pipe
    """
    url = channel_url(config)
    log = getLogger(_LOG)
    log.debug("Reading from channel %s with peek=%s and force=%s", config.channel, peek, force)
    params = DownloadRequestParams(version=version, override=force, delete=not peek)
    waited: bool = False
    while True:
        r = request("GET", url, params=params.to_dict())
        if r.ok:
            headers = DownloadResponseHeaders.from_dict(r.headers)
            sys.stdout.buffer.write(decrypt(r.content, config.password if headers.encrypted else None))
            sys.stdout.flush()
            if headers.final:
                log.debug("Stream complete")
                return
            params.stream_id = headers.stream_id
        elif r.status_code == DownloadErrorCode.wait:
            log.debug("No data available yet, sleeping for %s seconds.", WAIT_DELAY_SEC)
            sleep(WAIT_DELAY_SEC)
            waited = True
        else:
            _recv_error(r, config, peek, params.stream_id is not None, waited)
