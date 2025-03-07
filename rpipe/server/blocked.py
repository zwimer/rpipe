from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import TYPE_CHECKING, cast
from logging import getLogger
from datetime import datetime
from os.path import normpath
from threading import RLock
import atexit
import json

from werkzeug.serving import is_running_from_reloader
from flask import request
from wcmatch import glob

from ..shared import TRACE, Version, version, __version__

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(kw_only=True, slots=True)
class Data:
    """
    Contains blocklist data such as ips, routes, whitelists, etc
    """

    version: Version = field(default_factory=lambda: Version("0.0.1"))
    ips: list[str] = field(default_factory=list)
    routes: list[str] = field(default_factory=list)
    whitelist: list[str] = field(default_factory=list)
    stats: dict[str, list[list[str]]] = field(default_factory=dict)


class Blocked:  # Move into server? Move stats into Stats?
    """
    Used to determine if requests should be blocked or not
    """

    _INIT = {"version": __version__}
    MIN_VERSION = Version("9.9.0")

    def __init__(self, file: Path | None, debug: bool) -> None:
        self._log = getLogger("Blocked")
        if file is not None:
            self._log.info("Loading blocklist: %s", file)
        js = self._INIT if file is None or not file.is_file() else json.loads(file.read_text())
        if (old := Version(js.pop("version", ""))) < self.MIN_VERSION:
            raise ValueError(f"Blocklist version too old: {old} <= {self.MIN_VERSION}")
        self._data = Data(version=version, **js)  # Use new version
        self._file: Path | None = file
        self._lock = RLock()
        # Initialize file as needed
        if file is None:
            self._log.warning("No blocklist is set, blocklist changes will not persist across restarts")
            return
        if not file.exists():
            self._log.warning("Blocklist %s not found. Using defaults", file)
        # Setup saving on exit
        if debug and not is_running_from_reloader():  # Flask will reload the program, skip atexit
            self._log.info("Skipping initialization until reload")
            return
        self._log.info("Installing atexit shutdown handler for saving blocklist")
        atexit.register(self._save)

    def __enter__(self) -> Data:
        """
        Returns the Data object of Blocked
        """
        self._lock.acquire()
        return self._data

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._lock.release()

    def _save(self) -> None:
        """
        Save data to blocklist
        This function assumes self._file is not None
        """
        if self._file is None:
            self._log.critical("_save called when blocklist file is not set; changes will not persist")
            return
        try:
            self._log.info("Saving blocklist: %s", self._file)
            with self as data:
                self._file.write_text(json.dumps(asdict(data), default=str, indent=4))
        except OSError:
            self._log.exception("Failed to save blocklist %s", self._file)

    def _notate(self, ip: str) -> None:
        """
        Record the blocked route (should be called by __call__)
        """
        pth = request.path
        self._log.log(TRACE, "%s blocked, attempted path: %s", ip, pth)
        with self as data:
            if ip not in data.stats:
                data.stats[ip] = []
            data.stats[ip].append([str(datetime.now()), pth])

    @staticmethod
    def _match(pth: str, patterns: list[str]) -> bool:
        """
        :param pth: The path string to check for matching
        :param patterns: The patterns to test s against
        :return: True iff s matches any of the given patterns
        """
        return glob.globmatch(normpath(pth), patterns, flags=glob.GLOBSTAR | glob.DOTGLOB | glob.IGNORECASE)

    def __call__(self) -> bool:
        """
        :return: True if the given request should be blocked
        """
        ip = cast(str, request.headers.get("X-Forwarded-For", request.remote_addr))
        with self as data:
            if ip in self._data.whitelist:
                return False
            if ip in self._data.ips:
                self._notate(ip)
                return True
            if self._match(pth := request.path, data.routes):
                self._log.info("Blocking IP %s based on route: %s", ip, pth)
                data.ips.append(ip)
                self._notate(ip)
                return True
        return False
