from __future__ import annotations
from typing import TYPE_CHECKING
from urllib.parse import quote
from logging import getLogger
from functools import cache

from requests import Session, Request

from .config import Config

if TYPE_CHECKING:
    from requests import Response


WAIT_DELAY_SEC: float = 0.25
REQUEST_TIMEOUT: int = 60


def channel_url(c: Config) -> str:
    return f"{c.url}/c/{quote(c.channel)}"


@cache
def _session() -> Session:
    return Session()


def request(*args, **kwargs) -> Response:
    r = Request(*args, **kwargs).prepare()
    if r.body:
        getLogger("request").debug("Sending %d bytes of data", len(r.body))
    ret = _session().send(r, timeout=REQUEST_TIMEOUT)
    return ret
