from __future__ import annotations
from typing import TYPE_CHECKING
from logging import getLogger

from flask import request

from ..server import ServerShutdown
from ..util import plaintext
from .write import write
from .read import read

if TYPE_CHECKING:
    from flask import Response
    from ..server import State


def channel_handler(state: State, channel: str) -> Response:
    log = getLogger("channel")
    try:
        log.info("Invoking channel command %s", request.method)
        match request.method:
            case "DELETE":
                with state as rw_state:
                    if channel in rw_state.streams:
                        log.info("Deleting channel %s", channel)
                        del rw_state.streams[channel]
                return plaintext("Cleared", status=202)
            case "GET":
                return read(state, channel)
            case "POST" | "PUT":
                return write(state, channel)
            case _:
                log.info("404: bad method: %s", request.method)
                return plaintext(f"Unknown method: {request.method}", status=404)
    except ServerShutdown:
        return plaintext("Server is shutting down", status=503)
