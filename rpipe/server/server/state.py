from __future__ import annotations
from logging import getLogger, INFO
from typing import TYPE_CHECKING
from threading import RLock
import pickle

from ...shared import Stats, Version, version
from .shutdown_handler import ShutdownHandler

if TYPE_CHECKING:
    from .stream import Stream
    from pathlib import Path


MIN_SAVE_STATE_VERSION = Version("7.3.0")


class ServerShutdown(RuntimeError):
    """
    Raised when trying to acquire the lock on a server that is already shut down
    """


class UnlockedState:
    """
    A class that holds the state of a server
    This class is not thread safe and access to it should be protected by a lock
    """

    _log = getLogger("UnlockedState")

    def __init__(self) -> None:
        self.streams: dict[str, Stream] = {}
        self.shutdown: bool = False
        self._debug: bool = False
        self.stats = Stats()

    def load(self, file: Path) -> None:
        """
        Save the state of the server (does not load stats)
        """
        if len(self.streams):
            self._log.error("Existing state detected; will not overwrite")
            raise RuntimeError("Do not load a state on top of an existing state")
        if not file.exists():
            self._log.warning("State file %s not found. State is set to empty", file)
            return
        self._log.info("Loading %s", file)
        with file.open("rb") as f:
            if (ver := Version(f.readline().strip())) < MIN_SAVE_STATE_VERSION:
                self._log.error("State version too old: %s", ver)
                self._log.warning("Failed to load saved state. State is set to empty.")
                return
            self.streams = pickle.load(f)
        self._log.debug("Creating server Stats")
        self.stats = Stats()
        _ = tuple(self.stats.channels[i] for i in self.streams)
        self._log.info("State loaded successfully")

    def save(self, file: Path) -> None:
        """
        Save the program state (does not save stats)
        Do not call this unless the server is shutdown!
        Assumes self.RLock is acquired
        """
        if not self.shutdown:
            raise RuntimeError("Do save state before shutdown")
        if file.exists():
            self._log.info("Purging old program state...")
            file.unlink()
        self._log.info("Saving state to: %s", file)
        with file.open("wb") as f:
            f.write(bytes(version) + b"\n")
            pickle.dump(self.streams, f)
        if self._log.isEnabledFor(INFO):
            self._log.info("Channels saved: %s", ", ".join(self.streams.keys()))
        self._log.info("State saved successfully")

    @property
    def debug(self):
        return self._debug

    @debug.setter
    def debug(self, value: bool):
        """
        Allow enabling of debug mode- disabling is not allowed
        """
        if not value and self._debug:
            raise ValueError("Cannot unset debug mode")
        if value:
            self._debug = True
            self._log.warning("Debug mode enabled")


class State:
    """
    A thread safe wrapper for ServerState
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._shutdown_handler: ShutdownHandler | None = None
        self._log = getLogger("State")
        self._state = UnlockedState()

    def install_shutdown_handler(self, state_file: Path) -> None:
        with self._lock:
            if self._shutdown_handler is not None:
                self._log.error("Shutdown handler already installed")
                raise RuntimeError("Shutdown handler already installed")
            self._log.info("Installing shutdown handler")
            self._shutdown_handler = ShutdownHandler(self, state_file)

    def __enter__(self) -> UnlockedState:
        """
        Acquire the lock and return the state; will fail if the server is shutdown
        """
        self._lock.acquire()
        if self._state.shutdown:
            self._log.error("Lock acquired, but server is shut down")
            self._lock.release()
            raise ServerShutdown()
        return self._state

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._lock.release()
