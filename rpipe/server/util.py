from __future__ import annotations
from logging import getLogger, Logger, DEBUG
from typing import TYPE_CHECKING
from dataclasses import fields

from .constants import PIPE_MAX_BYTES

if TYPE_CHECKING:
    from typing import TypeVar
    from collections.abc import Callable, Iterable
    from flask import Response
    from ..shared import UploadRequestParams, DownloadRequestParams

if TYPE_CHECKING:
    ArgsT = TypeVar("ArgsT", bound=Callable)


def hsize(n: int) -> str:
    """
    Convert n (number of bytes) into a string such as: 12.3 MiB
    """
    sizes = (("GiB", 2**30), ("MiB", 2**20), ("KiB", 2**10))
    for i, k in sizes:
        if n > k:
            return f"{n/k:.2f} {i}"
    return f"{n} B"


def pipe_full(data: Iterable[bytes]) -> bool:
    """
    :return: True if the pipe is full, else False
    """
    return sum(len(i) for i in data) >= PIPE_MAX_BYTES


def log_pipe_size(log: Logger, data: Iterable[bytes]) -> None:
    if not log.isEnabledFor(DEBUG):
        return
    n = sum(len(i) for i in data)
    log.debug("Pipe now has %s/%s (%.2f%%) bytes.", hsize(n), hsize(PIPE_MAX_BYTES), 100 * n / PIPE_MAX_BYTES)


def log_params(log: Logger, p: UploadRequestParams | DownloadRequestParams) -> None:
    if not log.isEnabledFor(DEBUG):
        return
    log.debug("Request URL parameters:")
    for i in (k.name for k in fields(p)):
        log.debug("  %s: %s", i, getattr(p, i))


def _log_response(log: Logger, r: Response) -> None:
    if not log.isEnabledFor(DEBUG):
        return
    log.debug("Response:")
    log.debug("  Headers:")
    for i, k in r.headers.items():
        log.debug("    %s: %s", i, k)
    log.debug("  Status: %s", r.status)


def log_response(log_name: str = "util"):
    """
    A decorator that logs the returned flask Responses to the log log_name
    """

    def decorator(func: Callable[[ArgsT], Response]) -> Callable[[ArgsT], Response]:
        def inner(*args, **kwargs) -> Response:
            ret: Response = func(*args, **kwargs)
            _log_response(getLogger(log_name), ret)
            return ret

        return inner

    return decorator
