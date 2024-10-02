from __future__ import annotations
from typing import TYPE_CHECKING
from threading import RLock

from flask import Response

from ..shared import Version

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Any
    from enum import Enum


MIN_VERSION = Version("6.3.0")
MAX_SIZE_SOFT: int = 64 * (2**20)
MAX_SIZE_HARD: int = 2 * MAX_SIZE_SOFT + 0x200


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
