from typing import TYPE_CHECKING
from json import dumps

from flask import Response

from ..shared import MAX_SOFT_SIZE_MIN, Version

if TYPE_CHECKING:
    from collections.abc import Sequence
    from enum import Enum


MIN_VERSION = Version("9.6.1")

# Maximum size of a request
# Note: The soft limit is soft to allow overhead of encryption headers and such
MAX_SIZE_SOFT: int = 64 * (1000**2)
assert MAX_SIZE_SOFT >= MAX_SOFT_SIZE_MIN
MAX_SIZE_HARD: int = 2 * MAX_SIZE_SOFT + 0x200  # For packets sent to the server only


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
