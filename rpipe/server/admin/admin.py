from __future__ import annotations
from typing import TYPE_CHECKING, override
from dataclasses import asdict
from logging import getLogger
from time import sleep
import json

from cryptography.hazmat.primitives.serialization import load_ssh_public_key
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from flask import Response, request

from ...shared import ChannelInfo
from ..util import plaintext

if TYPE_CHECKING:
    from typing import Protocol, Any, cast
    from collections.abc import Callable
    from pathlib import Path
    from ..server import State


_LOG = "admin"
if TYPE_CHECKING:

    class Verifier(Protocol):
        def __call__(self, signature: bytes, *, data: bytes) -> None: ...


class Methods:
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
    """

    def __init__(self) -> None:
        self._log = getLogger(_LOG)
        self._verifiers: tuple[Verifier, ...] = ()
        self._methods: Methods = Methods()

    def _load_verifier(self, key_file: Path) -> Verifier | None:
        try:
            if not key_file.exists():
                self._log.error("Key file %s does not exist", key_file)
                return None
            key: Any = load_ssh_public_key(key_file.read_bytes())
            if ret := getattr(key, "verify", None):
                if TYPE_CHECKING:
                    ret = cast(Verifier, ret)
            return ret
        except UnsupportedAlgorithm:
            pass
        self._log.error("Signature verification is not supported for %s - Skipping", key_file)
        return None

    def load_keys(self, key_files: list[Path]):
        """
        Load the public key files that are used for signature verification
        """
        self._log.debug("Loading allowed signing keys")
        self._verifiers = tuple(i for i in (self._load_verifier(k) for k in key_files) if i)
        self._log.debug("Signing key load complete")

    @override
    def __getattribute__(self, item: str) -> Any:
        """
        Override the getattribute method to expose all methods of Methods and protect them with signature verification
        """
        if item.startswith("_") or item == "load_keys":
            return super().__getattribute__(item)
        return self._verify_wrap(getattr(self._methods, item))

    def _verify(self, signature: bytes, *, msg: bytes) -> bool:
        self._log.debug("Verifying signature message: %s", msg)
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

        def _wrap(*args, **kwargs) -> Response:
            self._log.debug("Extracting request signature and message")
            signature = request.get_data()
            msg = request.full_path.encode() + f"|{dict(request.args)}".encode()
            sleep(0.01)  # Slow down brute force attacks
            if not self._verify(signature, msg=msg):
                self._log.warning("Signature verification failed.")
                return Response(status=401)
            self._log.debug("Signature verified.")
            self._log.info("Executing %s", request.full_path)
            return func(*args, **kwargs)

        return _wrap
