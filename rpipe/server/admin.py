from __future__ import annotations
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, cast
from dataclasses import asdict
from threading import RLock
from time import sleep
from os import urandom
import logging
import json
import zlib

from cryptography.hazmat.primitives.serialization import load_ssh_public_key
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from flask import Response, request

from ..shared import ChannelInfo, AdminMessage, AdminPOST, AdminStats, Version
from .util import plaintext

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Protocol, Any
    from pathlib import Path
    from .server import State


MIN_VERSION = Version("7.1.5")


if TYPE_CHECKING:

    class _Verifier(Protocol):
        def __call__(self, signature: bytes, *, data: bytes) -> None: ...


def _json(d: dict) -> Response:
    return Response(json.dumps(d, default=str), status=200, mimetype="application/json")


class _UID:
    """
    A class to manage UIDs that are used for signature verification
    """

    _UID_EXPIRE: int = 300
    _UID_LEN: int = 32

    def __init__(self) -> None:
        self._uids: dict[str, datetime] = {}
        self._log = logging.getLogger("UID")
        self._lock = RLock()

    def new(self, n: int) -> list[str]:
        ret = [urandom(self._UID_LEN).hex() for i in range(n)]
        with self._lock:
            eol = datetime.now() + timedelta(seconds=self._UID_EXPIRE)
            self._uids.update({i: eol for i in ret})
        self._log.info("Generated %s new UIDs", n)
        return ret

    def verify(self, uid: str) -> bool:
        self._log.info("Verifying UID: %s", uid)
        with self._lock:
            if uid not in self._uids:
                self._log.error("UID not found: %s", uid)
                return False
            if datetime.now() > self._uids.pop(uid):
                self._log.warning("UID expired: %s", uid)
                return False
            self._log.info("UID verified.")
        return True


class Admin:
    """
    Admin class that protects the server from unauthorized access
    It requires a valid signature to access any method from the Methods class
    Any method from the method class is a member of this class, but is wrapped in a signature verification
    Signed requests must contain a valid signed UID that is only valid for a short period of time
    """

    _NO_WRAP = ("init", "uids")
    _UIDS_PER_QUERY: int = 2

    def __init__(self) -> None:
        self._verifiers: tuple[tuple[_Verifier, Path], ...] = ()
        self._log = logging.getLogger("Admin")
        self._log_file: Path | None = None
        self._uids = _UID()
        self._init = False

    def init(self, log_file: Path, key_files: list[Path]):
        """
        Set up the admin class
        Load the public key files that are used for signature verification
        """
        self._log.debug("Setting up admin class")
        self._log_file = log_file
        self._log.debug("Log file set to %s", self._log_file)
        self._log.info("Loading allowed signing keys")
        self._verifiers = tuple(i for i in ((self._load_verifier(k), k) for k in key_files) if i[0])  # type: ignore
        self._log.info("Signing key load complete")
        self._init = True

    def uids(self) -> Response:
        """
        Get a few UIDSs that may each be used in a signature to access the server exactly once
        """
        data = json.dumps(self._uids.new(self._UIDS_PER_QUERY))
        return Response(data, status=200, mimetype="application/json")

    #
    # Wrapped Methods
    #

    def debug(self, state: State) -> Response:
        with state as s:
            debug = s.debug
        return plaintext(str(debug))

    def log(self, _: State) -> Response:
        for i in logging.getLogger().handlers:
            i.flush()
        if self._log_file is None:
            return Response("Missing log file", status=500, mimetype="text/plain")
        data = zlib.compress(self._log_file.read_bytes().strip())
        self._log.debug("Sending compressed log of size: %s", len(data))
        return Response(data, status=200, mimetype="application/octet-stream")

    def stats(self, state: State) -> Response:
        with state as s:
            stats = asdict(s.stats)
        return _json(stats)

    def channels(self, state: State) -> Response:
        """
        Return a list of the server's current channels and stats
        """
        ci = lambda x: ChannelInfo(
            version=x.version,
            packets=len(x.data),
            size=len(x),
            encrypted=x.encrypted,
            expire=x.expire,
        )
        with state as s:
            output = {i: asdict(ci(k)) for i, k in s.streams.items()}
        return _json(output)

    #
    # Helpers
    #

    def _load_verifier(self, key_file: Path) -> _Verifier | None:
        try:
            if not key_file.exists():
                self._log.error("Key file %s does not exist", key_file)
                return None
            key: Any = load_ssh_public_key(key_file.read_bytes())
            if ret := getattr(key, "verify", None):
                if TYPE_CHECKING:
                    ret = cast(_Verifier, ret)
            return ret
        except UnsupportedAlgorithm:
            pass
        self._log.error("Signature verification is not supported for %s - Skipping", key_file)
        return None

    def __getattribute__(self, item: str) -> Any:
        """
        Override the getattribute method to wrap most public members with signature verification
        """
        ret = super().__getattribute__(item)
        if item.startswith("_") or item in self._NO_WRAP:
            return ret
        return self._wrap(ret, item)

    def _verify_signature(self, signature: bytes, *, msg: bytes) -> Path | None:
        self._log.info("Verifying signature of message: %s", msg)
        for fn, path in self._verifiers:
            try:
                fn(signature, data=msg)
                return path
            except InvalidSignature:
                pass
        return None

    def _wrap(self, func: Callable, name: str) -> Callable:
        """
        A decorator that wraps the method with signature verification
        """

        def _verify(state: State, *args) -> Response:
            try:
                # Log the request and verify initialization
                stat = AdminStats(host=request.remote_addr, command=name)
                with state as s:
                    s.stats.admin.append(stat)
                if not self._init:
                    raise AttributeError("Admin class not initialized")
                # Extract parameters
                self._log.info("Extracting request signature and message")
                try:
                    pm = AdminPOST.from_json(request.get_json())
                except Exception as e:  # pylint: disable=broad-except
                    logging.error(e, exc_info=True)
                    return Response("Failed to parse POST body", status=400)
                stat.version = pm.version
                stat.uid = pm.uid
                # Version check, UID check, Signature Verification
                if Version(pm.version) < MIN_VERSION:
                    return Response(f"Minimum supported client version: {MIN_VERSION}", status=426)
                sleep(0.01)  # Slow down brute force attacks
                if not self._uids.verify(pm.uid):
                    self._log.warning("Rejecting request due to invalid UID: %s", pm.uid)
                    return Response(status=401)
                stat.uid_valid = True
                msg = AdminMessage(path=request.path, args=dict(request.args), uid=pm.uid).bytes()
                if (key_file := self._verify_signature(pm.signature, msg=msg)) is None:
                    self._log.warning("Signature verification failed.")
                    return Response(status=401)
                stat.signer = key_file
                # Execute function
                self._log.info("Signature verified. Executing %s", request.full_path)
                return func(state, *args)
            except Exception as e:  # pylint: disable=broad-except
                self._log.error(e, exc_info=True)
                return Response(status=500)

        return _verify
