from typing import TYPE_CHECKING
from logging import getLogger
from functools import cache

from requests import Session, Request

from .errors import BlockedError
from ...shared import BLOCKED_EC

if TYPE_CHECKING:
    from requests import Response


_DEFAULT_TIMEOUT: int = 60
_WAIT_DELAY_SEC: dict[int, float] = {0: 0.3, 1: 0.5, 5: 1.0, 60: 2.0, 300: 5.0}


def wait_delay_sec(lvl: int) -> float:
    """
    :return: The number of seconds to wait before retrying a request
    """
    if lvl < 0:
        raise ValueError("Invalid level")
    return _WAIT_DELAY_SEC[max(i for i in _WAIT_DELAY_SEC if i <= lvl)]


@cache
def _session() -> Session:
    return Session()


def request(*args, timeout: int | None, **kwargs) -> Response:
    r = Request(*args, **kwargs).prepare()
    if r.body:
        getLogger("request").debug("Making %s request with %d bytes of data", r.method, len(r.body))
    ret = _session().send(r, timeout=_DEFAULT_TIMEOUT if timeout is None else timeout)
    if ret.status_code == BLOCKED_EC:
        raise BlockedError()
    return ret
