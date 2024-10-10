from __future__ import annotations
from typing import TYPE_CHECKING
from dataclasses import asdict
from logging import getLogger

from flask import request

from ...shared import QueryEC
from ..util import plaintext, json_response
from ..server import ServerShutdown
from .write import write
from .read import read

if TYPE_CHECKING:
    from flask import Response
    from ..server import State


def _handler(state: State, channel: str) -> Response:
    log = getLogger("channel")
    try:
        match request.method:
            case "DELETE":
                with state as u:
                    u.stats.delete(channel)
                    if channel in u.streams:
                        log.info("Deleting channel %s", channel)
                        del u.streams[channel]
                return plaintext("Deleted", status=202)
            case "GET":
                return read(state, channel)
            case "POST" | "PUT":
                return write(state, channel)
            case _:
                log.warning("404: bad method: %s", request.method)
                return plaintext(f"Unknown method: {request.method}", status=404)
    except ServerShutdown:
        log.warning("Ignoring request, server is shutting down")
        return plaintext("Server is shutting down", status=503)


def handler(state: State, channel: str) -> Response:
    log = getLogger("channel")
    log.info("Invoking: %s %s", request.method, channel)
    ret = _handler(state, channel)
    log.info("Sending: %s", ret)
    if ret.status_code >= 400:
        log.debug("  body: %s", ret.get_data())
    return ret


def query(state: State, channel: str) -> Response:
    log = getLogger("query")
    log.info("Query %s", channel)
    with state as u:
        if (s := u.streams.get(channel, None)) is None:
            log.debug("Channel not found: %s", channel)
            return plaintext("No data on this channel", status=QueryEC.no_data)
        q = s.query()
    log.debug("Channel found: %s", q)
    return json_response(asdict(q))
