from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
import random
import string

if TYPE_CHECKING:
    from ...version import Version
    from collections import deque


CHARSET = string.ascii_lowercase + string.ascii_uppercase + string.digits
_PIPE_MAX_BYTES: int = 2**30


def _uid() -> str:
    return "".join(random.choices(CHARSET, k=32))  # nosec B311


@dataclass(kw_only=True)
class Stream:  # pylint: disable=too-many-instance-attributes
    """
    Holds data about a stream
    """

    ttl: int
    data: deque[bytes]
    upload_complete: bool  # If more data will be added
    new: bool = True  # If no data has been read
    # Constants
    encrypted: bool
    version: Version
    capacity: int = _PIPE_MAX_BYTES
    id_: str = field(init=False, default_factory=_uid)

    def __post_init__(self) -> None:
        self._capacity: int = _PIPE_MAX_BYTES
        self._CONSTANTS = ("encrypted", "version", "id_", "_CONSTANTS")

    def __setattr__(self, key, value):
        """
        __setattr__ override to prevent changing constants and updates _expired
        """
        if key in getattr(self, "_CONSTANTS", {}):
            raise AttributeError("Cannot change constant values")
        super().__setattr__(key, value)
        if key != "_expire" and hasattr(self, "ttl"):  # hasattr b/c we might not during init
            # pylint: disable=attribute-defined-outside-init
            self._expire = datetime.now() + timedelta(self.ttl)

    def expired(self) -> bool:
        """
        Return true if the stream is expired
        """
        return self._expire < datetime.now()

    def __len__(self) -> int:
        """
        :return: The number of bytes in the pipe
        """
        return sum(len(i) for i in self.data)

    def full(self) -> bool:
        """
        :return: True if the server pipe is full, else False
        """
        return len(self) >= self._capacity
