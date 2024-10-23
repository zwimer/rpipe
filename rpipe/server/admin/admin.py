from __future__ import annotations
from logging import getLevelNamesMapping, getLevelName, getLogger
from typing import TYPE_CHECKING, Any
from dataclasses import asdict
from json import loads
import zlib

from flask import Response

from ...shared import AdminEC
from ..util import plaintext, json_response
from .verify import Verify

if TYPE_CHECKING:
    from pathlib import Path
    from ..server import State


_UIDS_PER_QUERY: int = 2


class Methods:
    """
    Protected methods that can be accessed by the Admin class
    """

    def __init__(self, log_file: Path | None) -> None:
        self._log = getLogger("Admin")
        self._log_file = log_file
        self._log.debug("Log file set to %s", log_file)

    @staticmethod
    def debug(state: State, _: str) -> Response:
        return plaintext(str(state.debug))

    def log(self, *_) -> Response:
        for i in getLogger().handlers:
            i.flush()
        if self._log_file is None:
            return Response("Missing log file", status=500, mimetype="text/plain")
        data = zlib.compress(self._log_file.read_bytes().strip())
        self._log.debug("Sending compressed log of size: %s", len(data))
        return Response(data, status=200, mimetype="application/octet-stream")

    def log_level(self, state: State, body: str) -> Response:
        root = getLogger()
        new = (old := getLevelName(root.getEffectiveLevel()))
        if body:
            try:
                new = getLevelName(lvl := int(getLevelNamesMapping().get(body.upper(), body)))
                self._log.info("Setting log level to %s", new)
                root.setLevel(lvl)
                if state.debug:
                    getLogger("werkzeug").setLevel(lvl)
                self._log.debug("Log level set to %s", new)
            except ValueError:
                return Response(f"Invalid log level: {body}", status=AdminEC.invalid, mimetype="text/plain")
        return Response(f"{old}\n{new}", status=200, mimetype="text/plain")

    @staticmethod
    def stats(state: State, _: str) -> Response:
        with state as s:
            stats = asdict(s.stats)
        return json_response(stats)

    def channels(self, state: State, _: str) -> Response:
        """
        Return a list of the server's current channels and stats
        """
        with state as s:
            output = {i: asdict(k.query()) for i, k in s.streams.items()}
        return json_response(output)

    def lock(self, state: State, body: str) -> Response:
        js = loads(body.strip())
        with state as unlocked:
            if (s := unlocked.streams.get(channel := js["channel"], None)) is None:
                return Response(f"Channel {channel} not found", status=AdminEC.invalid)
            lock_s = f"{('' if (lock := js['lock']) else 'UN')}LOCKED"
            self._log.info("Setting channel %s to %s", channel, lock_s)
            s.locked = lock
        return Response(f"Channel {channel} is now {lock_s}", status=200)


class Admin:
    """
    Admin class that protects the server from unauthorized access
    It requires a valid signature to access any method from the Methods class
    Any public method from the method class is a member of this class, wrapped in a signature verification
    Signed requests must contain a valid signed UID that is only valid for a short period of time
    """

    __slots__ = ("_verify", "_methods")

    def __init__(self, log_file: Path, key_files: list[Path]) -> None:
        self._verify = Verify(key_files)
        self._methods = Methods(log_file)

    def __getattr__(self, item: str) -> Any:
        """
        Override the getattribute method to wrap most public members with signature verification
        """
        if item.startswith("_"):
            raise AttributeError(f"{item} is a private member")

        def wrapper(state: State) -> Response:
            assert self._verify is not None, "Admin not initialized"
            if isinstance(rv := self._verify(item, state), str):
                return getattr(self._methods, item)(state, rv)
            return rv

        return wrapper

    def uids(self) -> Response:
        """
        Get a few UIDSs that may each be used in a signature to access the server exactly once
        """
        return json_response(self._verify.uid.new(_UIDS_PER_QUERY))
