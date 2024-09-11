from __future__ import annotations
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from dataclasses import asdict
from threading import RLock
from time import sleep
from os import urandom
import logging
import json

from cryptography.hazmat.primitives.serialization import load_ssh_public_key
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from flask import Response, request

from ..shared import ChannelInfo, AdminMessage, AdminPOST
from ..version import Version
from .util import plaintext

if TYPE_CHECKING:
    from typing import Protocol, Any, cast
    from collections.abc import Callable
    from pathlib import Path
    from .server import State


MIN_VERSION = Version("7.1.5")


if TYPE_CHECKING:

    class _Verifier(Protocol):
        def __call__(self, signature: bytes, *, data: bytes) -> None: ...


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


class _Methods:
    """
    A list of admin methods that normal users should not be able to access
    These methods must be protected externally
    """

    def debug(self, state: State) -> Response:
        with state as s:
            debug = s.debug
        return plaintext(str(debug))

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
        return Response(json.dumps(output, default=str), status=200, mimetype="application/json")


class Admin:
    """
    Admin class that protects the server from unauthorized access
    It requires a valid signature to access any method from the Methods class
    Any method from the method class is a member of this class, but is wrapped in a signature verification
    Signed requests must contain a valid signed UID that is only valid for a short period of time
    """

    _UIDS_PER_QUERY: int = 2

    def __init__(self) -> None:
        self._log = logging.getLogger("Admin")
        self._verifiers: tuple[_Verifier, ...] = ()
        self._methods: _Methods = _Methods()
        self._uids = _UID()

    def uids(self) -> Response:
        """
        Get a few UIDSs that may each be used in a signature to access the server exactly once
        """
        data = json.dumps(self._uids.new(self._UIDS_PER_QUERY))
        return Response(data, status=200, mimetype="application/json")

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

    def load_keys(self, key_files: list[Path]):
        """
        Load the public key files that are used for signature verification
        """
        self._log.info("Loading allowed signing keys")
        self._verifiers = tuple(i for i in (self._load_verifier(k) for k in key_files) if i)
        self._log.info("Signing key load complete")

    def __getattribute__(self, item: str) -> Any:
        """
        Override the getattribute method to expose all methods of _Methods and protect them with signature verification
        """
        if item.startswith("_") or item in ("uids", "load_keys"):
            return super().__getattribute__(item)
        return self._verify_wrap(getattr(self._methods, item))

    def _verify_signature(self, signature: bytes, *, msg: bytes) -> bool:
        self._log.info("Verifying signature of message: %s", msg)
        for fn in self._verifiers:
            try:
                fn(signature, data=msg)
                return True
            except InvalidSignature:
                pass
        return False

    def _verify_wrap(self, func: Callable) -> Callable:
        """
        A decorator that wraps the method with signature verification
        """

        def _verify(*args, **kwargs) -> Response:
            try:
                self._log.info("Extracting request signature and message")
                try:
                    pm = AdminPOST.from_json(request.get_json())
                except Exception as e:  # pylint: disable=broad-except
                    logging.error(e, exc_info=True)
                    return Response("Failed to parse POST body", status=400)
                if Version(pm.version) < MIN_VERSION:
                    return Response(f"Minimum supported client version: {MIN_VERSION}", status=426)
                if not self._uids.verify(pm.uid):
                    self._log.warning("Rejecting request due to invalid UID: %s", pm.uid)
                    return Response(status=401)
                msg = AdminMessage(path=request.path, args=dict(request.args), uid=pm.uid).bytes()
                sleep(0.01)  # Slow down brute force attacks
                if not self._verify_signature(pm.signature, msg=msg):
                    self._log.warning("Signature verification failed.")
                    return Response(status=401)
                self._log.info("Signature verified. Executing %s", request.full_path)
                return func(*args, **kwargs)
            except Exception as e:  # pylint: disable=broad-except
                self._log.error(e, exc_info=True)
                return Response(status=500)

        return _verify
