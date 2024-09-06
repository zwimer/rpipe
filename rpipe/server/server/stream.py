from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
import random
import string

if TYPE_CHECKING:
    from ...version import Version
    from collections import deque
    from datetime import datetime


CHARSET = string.ascii_lowercase + string.ascii_uppercase + string.digits
_PIPE_MAX_BYTES: int = 2**30


def _uid() -> str:
    return "".join(random.choices(CHARSET, k=32))  # nosec B311


@dataclass(kw_only=True)
class Stream:  # pylint: disable=too-many-instance-attributes
    """
    Holds data about a stream
    """

    data: deque[bytes]
    expire: datetime
    encrypted: bool  # Constant
    version: Version  # Constant
    upload_complete: bool  # If more data will be added
    new: bool = True  # If no data has been read
    capacity: int = _PIPE_MAX_BYTES  # Constant
    id_: str = field(init=False, default_factory=_uid)  # Constant

    def __len__(self) -> int:
        """
        :return: The number of bytes in the pipe
        """
        return sum(len(i) for i in self.data)

    def full(self) -> bool:
        """
        :return: True if the server pipe is full, else False
        """
        return len(self) >= self.capacity
