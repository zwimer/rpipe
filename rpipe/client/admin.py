from typing import TYPE_CHECKING, cast
from collections.abc import Callable
from collections import deque
from datetime import datetime
from logging import getLogger
from json import loads, dumps
from base64 import b85encode
from pathlib import Path
import json
import zlib

from cryptography.hazmat.primitives.serialization import load_ssh_private_key  # type: ignore[attr-defined]
from cryptography.exceptions import UnsupportedAlgorithm
from requests import Session

from ..shared import QueryResponse, AdminMessage, AdminEC, version
from .. import shared  # Let BLOCKED_EC be used in match statements
from .client import Config, UsageError, BlockedError

if TYPE_CHECKING:
    from requests import Response


ADMIN_REQUEST_TIMEOUT: int = 60
type _Signer = Callable[[bytes], bytes]
_LOG = "admin"


#
# Exceptions
#


class AccessDenied(RuntimeError):
    """
    Raised when the server denies an admin request
    """


#
# Main Classes
#


class _Methods:
    """
    Methods that can be called by the Admin class
    These methods may return sensitive data and should only be used with SSL
    Any public function may require SSL by invoke it with the prefix _VERIFY_SSL
    All public functions besides 'get' may access self._conf (it will not be None)
    """

    def __init__(self, sign: _Signer, conf: Config) -> None:
        self._log = getLogger(_LOG)
        self._uids: deque[str] = deque()
        self._session = Session()
        self._sign = sign
        self._conf = conf

    # Helpers

    def _require_ok(self, r: Response) -> None:
        if not r.ok:
            what = f"Error {r.status_code}: {r.text}"
            self._log.critical(what)
            raise RuntimeError(what)

    def _request(self, path: str, body: str = "") -> Response:
        """
        Send a request to the server
        """
        if len(self._uids) == 0:
            r = self._session.get(f"{self._conf.url}/admin/uid", timeout=ADMIN_REQUEST_TIMEOUT)
            self._require_ok(r)
            if r.status_code == shared.BLOCKED_EC:
                raise BlockedError()
            self._uids += r.json()
        uid: str = self._uids.popleft()
        # Sign and send POST request
        self._log.info("Signing request for path=%s with body=%s", path, body)
        msg = AdminMessage(path=path, body=body, uid=uid).bytes()
        data = b"\n".join((bytes(version), b85encode(self._sign(msg)), msg))
        ret = self._session.post(f"{self._conf.url}{path}", data=data, timeout=ADMIN_REQUEST_TIMEOUT)
        match ret.status_code:
            case shared.BLOCKED_EC:
                raise BlockedError()
            case AdminEC.unauthorized:
                self._log.critical("Admin access denied")
                raise AccessDenied()
            case AdminEC.illegal_version:
                raise UsageError(ret.text)
        self._require_ok(ret)
        assert not ret.status_code == AdminEC.invalid, "Sanity check failed"
        return ret

    # Non-SSL-Protected methods

    def debug(self) -> bool:
        """
        :return: True if the server is in debug mode, else False
        """
        return self._request("/admin/debug").text == "True"

    # SSL-Protected methods

    def log(self, output_file: Path | None = None) -> None:
        """
        Download the server log
        """
        out = zlib.decompress(self._request("/admin/log").content)
        if output_file is None:
            print(out.decode())
            return
        self._log.info("Writing log to %s", output_file)
        output_file.write_bytes(out)

    def log_level(self, level: int | str | None):
        old, new = self._request("/admin/log-level", "" if level is None else str(level)).text.split("\n")
        print(f"Log level: {old} -> {new}")

    def stats(self) -> None:
        """
        Give the client a bunch of stats about the server
        """
        print(dumps(loads(self._request("/admin/stats").text), indent=4))

    def channels(self) -> None:
        """
        Request information about the channels the server has
        """
        if not (raw := self._request("/admin/channels").json()):
            print("Server is empty")
            return
        for i in raw.values():
            i["expiration"] = datetime.fromisoformat(i["expiration"])
        data = {i: QueryResponse(**k) for i, k in raw.items()}
        mx = max(len(i) for i in data)
        print("\n".join(f"{i.ljust(mx)} : {k}" for i, k in data.items()))

    def _lock(self, lock_: bool) -> None:
        if not self._conf.channel:
            raise UsageError("Channel must be set to lock/unlock")
        print(self._request("/admin/lock", dumps({"channel": self._conf.channel, "lock": lock_})).text)

    def lock(self) -> None:
        """
        Lock a channel
        """
        self._lock(True)

    def unlock(self) -> None:
        """
        Unlock a channel
        """
        self._lock(False)

    def _block(self, name: str, block: list[str] | None, unblock: list[str] | None) -> None:
        if block is None and unblock is None:
            blocked = self._request(f"/admin/{name}", f'{{"{name}": null}}').text
            blocked = json.dumps(json.loads(blocked), indent=4)
            print(f"Blocked {name}s: {blocked}")
            return
        for lst, ban in ((block, True), (unblock, False)):
            if lst is None:
                continue
            for obj in lst:
                self._request(f"/admin/{name}", dumps({name: obj, "block": ban}))
                print(f"{"" if ban else "UN"}BLOCKED: {obj}")

    def ip(self, block: list[str] | None, unblock: list[str] | None) -> None:
        """
        Request the blocked ip addresses, or block / unblock an ip address
        """
        self._block("ip", block, unblock)

    def route(self, block: list[str] | None, unblock: list[str] | None) -> None:
        """
        Request the blocked routes, or block / unblock a route
        """
        fix = lambda b: None if b is None else [i if i.startswith("/") else f"/{i}" for i in b]
        self._block("route", fix(block), fix(unblock))


class Admin:
    """
    A class used to ask the server to run admin functions
    """

    def __init__(self, conf: Config):
        self._log = getLogger(_LOG)
        self._ssl: bool = any(i in conf.url for i in ("https", ":443/"))
        if not conf.url or not conf.key_file:
            raise UsageError("Admin mode requires a URL and key-file to be set")
        self._methods = _Methods(self._load_ssh_key_file(conf.key_file), conf)

    def _load_ssh_key_file(self, key_file: Path) -> _Signer:
        """
        Load a private key from a file
        :return: A function that can sign data using the key file
        """
        self._log.info("Extracting private key from %s", key_file)
        if not key_file.exists():
            raise UsageError(f"Key file {key_file} does not exist")
        try:
            key = load_ssh_private_key(key_file.read_bytes(), None)
        except UnsupportedAlgorithm as e:
            raise UsageError(f"Key file {key_file} is not a supported ssh key") from e
        if not hasattr(key, "sign"):
            raise UsageError(f"Key file {key_file} does not support signing")
        return cast(_Signer, key.sign)

    def __getitem__(self, item: str) -> Callable[..., None]:
        """
        Get the desired admin function
        """
        if item.startswith("_"):
            raise KeyError(f"Admin method {item} is private")
        debug = self._methods.debug()
        if item == "debug":
            return lambda: print(f"Server is running in {'DEBUG' if debug else 'RELEASE'} mode")
        if not debug and not self._ssl:
            raise RuntimeError("Refusing to send admin request to server in release mode over plaintext")
        return getattr(self._methods, item)
