from __future__ import annotations
from typing import TYPE_CHECKING
from urllib.parse import quote
from logging import getLogger

from requests import Session, Request

from .config import Config

if TYPE_CHECKING:
    from requests import Response


WAIT_DELAY_SEC: float = 0.25
REQUEST_TIMEOUT: int = 60


def channel_url(c: Config) -> str:
    return f"{c.url}/c/{quote(c.channel)}"


def request(*args, **kwargs) -> Response:
    r = Request(*args, **kwargs).prepare()
    if r.body:
        getLogger("request").debug("Preparing to send %d bytes of data", len(r.body))
    ret = Session().send(r, timeout=REQUEST_TIMEOUT)
    return ret
