from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
import random
import string

if TYPE_CHECKING:
    from datetime import datetime
    from collections import deque
    from ..version import Version


CHARSET = string.ascii_lowercase + string.ascii_uppercase + string.digits


def _uid() -> str:
    return "".join(random.choices(CHARSET, k=32))  # nosec B311


@dataclass(kw_only=True)
class Stream:
    """
    Holds data about a stream
    """

    data: deque[bytes]
    expire: datetime
    encrypted: bool
    version: Version
    upload_complete: bool  # If more data will be added
    new: bool = True  # If no data has been read
    id_: str = field(init=False, default_factory=_uid)
