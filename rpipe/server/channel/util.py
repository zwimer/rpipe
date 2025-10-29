from logging import getLogger, Logger, DEBUG
from typing import TYPE_CHECKING
from dataclasses import fields

from flask import Response

if TYPE_CHECKING:
    from ...shared import UploadRequestParams, DownloadRequestParams
    from collections.abc import Callable
    from typing import TypeVar

    _ArgsT = TypeVar("_ArgsT", bound=Callable)


def log_params(log: Logger, p: UploadRequestParams | DownloadRequestParams) -> None:
    if not log.isEnabledFor(DEBUG):
        return
    log.debug("Request URL parameters:")
    for i in (k.name for k in fields(p)):
        log.debug("  %s: %s", i, getattr(p, i))


def log_response(log_name: str = "util"):
    """
    A decorator that logs the returned flask Responses to the log log_name
    """

    def decorator(func: Callable[[_ArgsT], Response]) -> Callable[[_ArgsT], Response]:
        def inner(*args, **kwargs) -> Response:
            ret: Response = func(*args, **kwargs)
            log = getLogger(log_name)
            if log.isEnabledFor(DEBUG):
                log.debug("Response:")
                log.debug("  Headers:")
                for i, k in ret.headers.items():
                    log.debug("    %s: %s", i, k)
                log.debug("  Status: %s", ret.status)
            return ret

        return inner

    return decorator
