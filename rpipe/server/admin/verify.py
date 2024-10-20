from __future__ import annotations
from typing import TYPE_CHECKING, Protocol, cast
from logging import getLogger
from base64 import b85decode
from pathlib import Path
from json import loads
from time import sleep

from cryptography.hazmat.primitives.serialization import load_ssh_public_key
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from flask import request

from ...shared import AdminMessage, AdminStats, AdminEC, Version, remote_addr
from .uid import UID


if TYPE_CHECKING:
    from flask import Response
    from ..server import State


MIN_VERSION = Version("8.8.0")


class _Verifier(Protocol):
    def __call__(self, signature: bytes, *, data: bytes) -> None: ...


class Verify:
    """
    A class to manage signature verification of Admin requests
    """

    __slots__ = ("uid", "_verifiers", "_log")

    def __init__(self, key_files: list[Path]):
        self._log = getLogger("Verify")
        self._log.info("Loading signing keys")
        verifiers = {self._load_verifier(k): k for k in key_files}
        _ = verifiers.pop(None, None)
        self._verifiers = cast(dict[_Verifier, Path], verifiers)
        self.uid = UID()

    def __call__(self, name: str, state: State) -> Response | str:
        try:
            return self._verify(name, state)
        except Exception:  # pylint: disable=broad-except
            self._log.error("Failed due to:", exc_info=True)
            return Response(status=500)

    # Private methods

    def _load_verifier(self, key_file: Path) -> _Verifier | None:
        try:
            if not key_file.exists():
                self._log.error("Key file %s does not exist", key_file)
                return None
            return cast(_Verifier | None, getattr(load_ssh_public_key(key_file.read_bytes()), "verify", None))
        except UnsupportedAlgorithm:
            self._log.error("Signature verification is not supported for %s - Skipping", key_file)
            return None

    def _verify_signature(self, signature: bytes, msg: bytes) -> Path | None:
        self._log.debug("Verifying signature of message: %s", msg)
        for fn in self._verifiers:
            try:
                fn(signature, data=msg)
                return self._verifiers[fn]
            except InvalidSignature:
                pass
        return None

    def _verify(self, name: str, state: State) -> Response | str:
        stat = AdminStats(host=remote_addr(), command=name)
        with state as s:
            s.stats.admin.append(stat)
        # Check version
        self._log.debug("Checking version")
        version, post = request.get_data().split(b"\n", 1)
        stat.version = version.decode()
        if Version(version) < MIN_VERSION:
            _msg = f"Minimum supported client version: {MIN_VERSION}"
            return Response(_msg, status=AdminEC.illegal_version)
        # Extract parameters
        self._log.info("Extracting request signature and message")
        signature, msg_bytes = post.split(b"\n", 1)
        msg = AdminMessage(**loads(msg_bytes.decode()))
        stat.uid = msg.uid
        # Verify UID
        sleep(0.01)  # Slow down brute force attacks
        if not self.uid.verify(msg.uid):
            self._log.warning("Rejecting request due to invalid UID: %s", msg.uid)
            return Response(status=AdminEC.unauthorized)
        stat.uid_valid = True
        # Verify signature
        if (key_file := self._verify_signature(b85decode(signature), msg_bytes)) is None:
            self._log.warning("Signature verification failed.")
            return Response(status=AdminEC.unauthorized)
        stat.signer = key_file
        # Success
        self._log.info("Signature verified. Executing %s", request.full_path.strip("?"))
        return msg.body
