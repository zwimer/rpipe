from __future__ import annotations
from logging import getLogger, DEBUG
from typing import TYPE_CHECKING
from datetime import datetime
from threading import RLock
import pickle

if TYPE_CHECKING:
    from .stream import Stream
    from pathlib import Path


class ServerShutdown(RuntimeError):
    """
    Raised when trying to acquire the lock on a server that is already shut down
    """


class UnlockedState:
    """
    A class that holds the state of a server
    This class is not thread safe and access to it should be protected by a lock
    """

    _log = getLogger("server_state")

    def __init__(self) -> None:
        self.streams: dict[str, Stream] = {}
        self.shutdown: bool = False
        self._debug: bool = False

    def load(self, file: Path) -> None:
        """
        Save the state of the server
        """
        if len(self.streams):
            raise RuntimeError("Do not load a state on top of an existing state")
        self._log.debug("Loading %s", file)
        with file.open("rb") as f:
            timestamp, self.streams = pickle.load(f)
        # Extend TTLs by the amount of time since the last save
        offset = datetime.now() - timestamp
        self._log.debug("Extending saved TTLs by %s to account for server downtime...", offset)
        for i in self.streams.values():
            i.expire += offset
        self._log.debug("State loaded successfully")

    def save(self, file: Path) -> None:
        """
        Save the program state
        Do not call this unless the server is shutdown!
        Assumes self.RLock is acquired
        """
        if not self.shutdown:
            raise RuntimeError("Do save state before shutdown")
        if file.exists():
            self._log.debug("Purging old program state...")
            file.unlink()
        self._log.info("Saving program state...")
        if not self.streams:
            return
        self._log.debug("Saving state to: %s", file)
        with file.open("wb") as f:  # Save timestamp so we can extend TTLs on load
            pickle.dump((datetime.now(), self.streams), f)
        if self._log.isEnabledFor(DEBUG):
            self._log.debug("Channels saved: %s", ", ".join(self.streams.keys()))
        self._log.debug("State saved successfully")

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

    def __init__(self):
        self._lock = RLock()
        self._state = UnlockedState()

    def __enter__(self) -> UnlockedState:
        self._lock.acquire()
        if self._state.shutdown:
            self._lock.release()
            raise ServerShutdown()
        return self._state

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._lock.release()
