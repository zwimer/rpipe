from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime
    from collections import deque
    from ..version import Version


@dataclass(kw_only=True)
class Stream:
    """
    Holds data about a stream
    """

    data: deque[bytes]
    when: datetime
    encrypted: bool
    version: Version
    id_: str
    upload_complete: bool  # If more data will be added
    new: bool = True  # If no data has been read
