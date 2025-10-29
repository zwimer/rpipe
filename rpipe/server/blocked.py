from dataclasses import dataclass, asdict, field
from typing import TYPE_CHECKING, cast
from logging import getLogger
from datetime import datetime
from threading import RLock
import atexit
import json
import re

from werkzeug.serving import is_running_from_reloader
from flask import request

from ..shared import TRACE, Version, version, __version__

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(kw_only=True, slots=True)
class Data:
    """
    Contains blocklist data such as ips, routes, whitelists, etc
    """

    version: Version = field(default_factory=lambda: Version("0.0.1"))
    ip_whitelist: set[str] = field(default_factory=set)
    ip_blacklist: set[str] = field(default_factory=set)
    route_whitelist: list[str] = field(default_factory=list)
    route_blacklist: list[str] = field(default_factory=list)
    stats: dict[str, list[list[str]]] = field(default_factory=dict)


class Blocked:  # Move into server? Move stats into Stats?
    """
    Used to determine if requests should be blocked or not
    """

    __slots__ = ("_log", "_data", "_file", "_lock", "_white_pat", "_black_pat")
    MIN_VERSION = Version("9.11.0")

    def __init__(self, file: Path | None, debug: bool) -> None:
        self._log = getLogger("Blocked")
        if file is not None:
            self._log.info("Loading blocklist: %s", file)
        js: dict
        js = {"version": __version__} if file is None or not file.is_file() else json.loads(file.read_text())
        if (old := Version(js.pop("version", ""))) < self.MIN_VERSION:
            raise ValueError(f"Blocklist version too old: {old} <= {self.MIN_VERSION}")
        js.update({i: set(k) for i, k in js.items() if i.startswith("ip_")})
        self._data = Data(version=version, **js)  # Use new version
        self._white_pat: list[re.Pattern[str]] = []
        self._black_pat: list[re.Pattern[str]] = []
        self._file: Path | None = file
        self._lock = RLock()
        with self as _:
            pass  # Generates patterns
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

    def _mk_pat_from(self, patterns: list[str]) -> list[re.Pattern[str]]:
        ret = []
        for i in patterns:
            try:
                ret.append(re.compile(i, re.IGNORECASE))
            except re.PatternError:
                self._log.error("Could not compile pattern: %s", i)
        return ret

    def __enter__(self) -> Data:
        """
        Returns the Data object of Blocked
        """
        self._lock.acquire()
        return self._data

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._white_pat = self._mk_pat_from(self._data.route_whitelist)
        self._black_pat = self._mk_pat_from(self._data.route_blacklist)
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
                sstr = lambda x: list(x) if isinstance(x, set) else str(x)
                self._file.write_text(json.dumps(asdict(data), default=sstr, indent=4))
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
    def _match(pth: str, patterns: list[re.Pattern[str]]) -> bool:
        """
        :param pth: The path string to check for matching
        :param patterns: The patterns to test s against
        :return: True iff s matches any of the given patterns
        """
        return any(re.fullmatch(i, pth) is not None for i in patterns)

    def __call__(self) -> bool:
        """
        :return: True if the given request should be blocked
        """
        ip = cast(str, request.headers.get("X-Forwarded-For", request.remote_addr))
        with self as data:
            # Block / allow based on ip first, then routes
            if ip in data.ip_whitelist:
                return False
            if ip in data.ip_blacklist:
                self._notate(ip)
                return True
            pth = request.path
            if self._match(pth, self._white_pat):
                return False
            if self._match(pth, self._black_pat):
                self._log.info("Blocking IP %s based on route: %s", ip, pth)
                data.ip_blacklist.add(ip)
                self._notate(ip)
                return True
        return False
