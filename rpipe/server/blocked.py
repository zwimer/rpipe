from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import TYPE_CHECKING
from logging import getLogger
from fnmatch import fnmatch
import json

from flask import request

from ..shared import Version, version, __version__

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(kw_only=True)
class Data:
    version: Version = field(default_factory=lambda: Version("0.0.1"))
    ips: list[str] = field(default_factory=list)
    routes: list[str] = field(default_factory=list)
    whitelist: list[str] = field(default_factory=list)


class Blocked:
    MIN_VERSION = Version("9.6.6")

    def __init__(self, file: Path | None) -> None:
        js = {"version": __version__} if file is None else json.loads(file.read_text())
        if (old := Version(js.pop("version", ""))) < self.MIN_VERSION:
            raise ValueError(f"Blocklist version too old: {old} <= {self.MIN_VERSION}")
        self.data = Data(version=version, **js)  # Use new version
        self.file: Path | None = file
        self._lg = getLogger("Blocked")

    def commit(self) -> None:
        if self.file is None:
            raise ValueError("Cannot save a block file when block-file not set")
        self.file.write_text(json.dumps(asdict(self.data), default=str, indent=4))

    def __call__(self) -> bool:
        if self.file is None:
            return False
        ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        if ip in self.data.whitelist:
            return False
        if ip in self.data.ips:
            return True
        pth = request.path
        if any(fnmatch(pth, i) for i in self.data.routes):
            self._lg.info("Blocking IP %s based on route: %s", ip, pth)
            self.data.ips.append(ip)  # type: ignore
            self.commit()
            return True
        return False
