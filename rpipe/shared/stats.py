from dataclasses import dataclass, field
from collections import defaultdict
from typing import TYPE_CHECKING
from datetime import datetime

from .util import remote_addr

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(kw_only=True)
class ChannelStats:
    peeks: defaultdict[str, int] = field(default_factory=lambda: defaultdict(int))
    reads: defaultdict[str, int] = field(default_factory=lambda: defaultdict(int))
    writes: defaultdict[str, int] = field(default_factory=lambda: defaultdict(int))
    deletes: defaultdict[str, int] = field(default_factory=lambda: defaultdict(int))
    natime: datetime = field(default_factory=datetime.now)  # Last time a NEW read/write/delete occurred


@dataclass(kw_only=True)
class AdminStats:
    time: datetime = field(default_factory=datetime.now)
    version: str | None = None
    signer: Path | None = None
    uid_valid: bool = False
    uid: str | None = None
    command: str
    host: str


@dataclass(kw_only=True, frozen=True)  # Note that members are not frozen
class Stats:
    start: datetime = field(default_factory=datetime.now)
    channels: defaultdict[str, ChannelStats] = field(default_factory=lambda: defaultdict(ChannelStats))
    admin: list[AdminStats] = field(default_factory=list)

    def peek(self, channel: str) -> None:
        self._update(channel, "peeks")

    def read(self, channel: str) -> None:
        self._update(channel, "reads")

    def write(self, channel: str) -> None:
        self._update(channel, "writes")

    def delete(self, channel: str) -> None:
        self._update(channel, "deletes")

    def _update(self, channel: str, name: str) -> None:
        getattr(self.channels[channel], name)[remote_addr()] += 1
        self.channels[channel].natime = datetime.now()
