from __future__ import annotations
from typing import TYPE_CHECKING
from threading import RLock
from json import dumps

from flask import Response

from ..shared import MAX_SOFT_SIZE_MIN, Version

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Any
    from enum import Enum


MIN_VERSION = Version("6.3.0")

# Maximum size of a request
# Note: The soft limit is soft to allow overhead of encryption headers and such
MAX_SIZE_SOFT: int = 64 * (1000**2)
assert MAX_SIZE_SOFT >= MAX_SOFT_SIZE_MIN
MAX_SIZE_HARD: int = 2 * MAX_SIZE_SOFT + 0x200  # For packets sent to the server only


class Singleton(type):
    """
    A metaclass that makes a class a singleton
    """

    _instances: dict[type, Any] = {}
    _lock = RLock()

    def __call__(cls, *args, **kwargs):
        with cls._lock:
            if cls in cls._instances:
                raise RuntimeError("Singleton class already instantiated")
            cls._instances[cls] = super().__call__(*args, **kwargs)
            return cls._instances[cls]


def total_len(x: Sequence[bytes]) -> int:
    return sum(len(i) for i in x)


def plaintext(msg: str, status: Enum | int = 200, **kwargs) -> Response:
    """
    Return a plain text Response containing the arguments
    """
    code: int = status if isinstance(status, int) else status.value
    return Response(msg, status=code, mimetype="text/plain", **kwargs)


def json_response(js) -> Response:
    return Response(dumps(js, default=str), status=200, mimetype="application/json")
