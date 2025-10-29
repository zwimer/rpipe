from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
import random
import string

from ...shared import QueryResponse, total_len

if TYPE_CHECKING:
    from ...version import Version
    from collections import deque


CHARSET = string.ascii_lowercase + string.ascii_uppercase + string.digits
_PIPE_MAX_BYTES: int = 10**9


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
    locked: bool = False  # May only be set by admin
    # Constants
    encrypted: bool
    version: Version
    capacity: int = _PIPE_MAX_BYTES
    id_: str = field(default_factory=_uid)

    def __post_init__(self) -> None:
        self.expire: datetime  # Set by __setattr__
        self._capacity: int = _PIPE_MAX_BYTES
        self._constants = ("encrypted", "version", "id_", "_constants")

    def __setattr__(self, key, value):
        """
        __setattr__ override to prevent changing constants and updates self.expire
        """
        if key == "expire":
            raise AttributeError("Expiration date is automatically set; do not change it manually")
        if key in getattr(self, "_constants", {}):
            raise AttributeError("Cannot change constant values")
        super().__setattr__(key, value)
        if hasattr(self, "ttl"):  # hasattr b/c we might not during init
            # pylint: disable=attribute-defined-outside-init
            super().__setattr__("expire", datetime.now() + timedelta(seconds=self.ttl))

    def expired(self) -> bool:
        """
        Return true if the stream is expired and unlocked
        """
        return not self.locked and self.expire < datetime.now()

    def __len__(self) -> int:
        """
        :return: The number of bytes in the pipe
        """
        return total_len(self.data)

    def full(self) -> bool:
        """
        :return: True if the server pipe is full, else False
        """
        return len(self) >= self._capacity

    def query(self) -> QueryResponse:
        return QueryResponse(
            new=self.new,
            upload_complete=self.upload_complete,
            packets=len(self.data),
            size=len(self),
            encrypted=self.encrypted,
            version=self.version,
            expiration=self.expire,
            locked=self.locked,
        )
