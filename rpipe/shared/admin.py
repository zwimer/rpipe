from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import TYPE_CHECKING
from json import dumps

from .version_ import Version

if TYPE_CHECKING:
    from datetime import datetime


@dataclass(kw_only=True, frozen=True)
class AdminMessage:
    body: str
    path: str
    uid: str

    def bytes(self) -> bytes:
        return dumps(asdict(self)).encode()


@dataclass(kw_only=True)
class ChannelInfo:
    version: Version
    packets: int
    size: int
    encrypted: bool
    expire: datetime
