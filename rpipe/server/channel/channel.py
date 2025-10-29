from typing import TYPE_CHECKING
from dataclasses import asdict
from logging import getLogger

from flask import request

from ...shared import TRACE, DeleteEC, QueryEC
from ..util import plaintext, json_response
from ..server import ServerShutdown
from .write import write
from .read import read

if TYPE_CHECKING:
    from flask import Response
    from ..server import State


def _delete(state: State, channel: str) -> Response:
    log = getLogger("delete")
    with state as u:
        u.stats.delete(channel)
        if (s := u.streams.get(channel, None)) is None:
            return plaintext("Channel already gone", status=204)
        if s.locked:
            return plaintext("Channel is locked", status=DeleteEC.locked)
        log.info("Deleting channel %s", channel)
        del u.streams[channel]
    return plaintext("Deleted", status=202)


def _handler(state: State, channel: str) -> Response:
    log = getLogger("channel")
    try:
        match request.method:
            case "DELETE":
                return _delete(state, channel)
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
    log.debug("Invoking: %s %s", request.method, channel)
    ret = _handler(state, channel)
    if ret.status_code >= 300:
        log.debug("Sending: %s", ret)
        log.log(TRACE, "Body: %s", ret.get_data())
    return ret


def query(state: State, channel: str) -> Response:
    log = getLogger("query")
    log.debug("Query %s", channel)
    with state as u:
        if (s := u.streams.get(channel, None)) is None:
            log.debug("Channel not found: %s", channel)
            return plaintext("No data on this channel", status=QueryEC.no_data)
        q = s.query()
    log.debug("Channel found: %s", q)
    return json_response(asdict(q))
