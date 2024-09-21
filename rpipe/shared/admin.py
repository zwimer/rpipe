from __future__ import annotations
from dataclasses import dataclass, field, asdict, astuple
from typing import TYPE_CHECKING

from .version_ import Version

if TYPE_CHECKING:
    from datetime import datetime


@dataclass(kw_only=True, frozen=True)
class AdminMessage:
    args: dict[str, str] = field(default_factory=dict)
    path: str
    uid: str

    def bytes(self) -> bytes:
        return str(astuple(self)).encode()


@dataclass(kw_only=True, frozen=True)
class AdminPOST:
    signature: bytes
    version: str
    uid: str

    @classmethod
    def from_json(cls, d: dict[str, str]) -> AdminPOST:
        s = bytes.fromhex(d.pop("signature"))
        return cls(signature=s, **d)

    def json(self) -> dict[str, str]:
        ret = asdict(self)
        ret["signature"] = self.signature.hex()
        return ret


@dataclass(kw_only=True)
class ChannelInfo:
    version: Version
    packets: int
    size: int
    encrypted: bool
    expire: datetime
