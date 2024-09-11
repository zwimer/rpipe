from __future__ import annotations
from typing import TYPE_CHECKING
from dataclasses import dataclass
from datetime import datetime
from collections import deque
from logging import getLogger
from functools import cache
from pathlib import Path
from json import loads

from cryptography.hazmat.primitives.serialization import load_ssh_private_key
from cryptography.exceptions import UnsupportedAlgorithm
from requests import Session

from ..version import version
from ..shared import ChannelInfo, AdminMessage, AdminPOST
from .config import ConfigFile, UsageError, Option

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any, cast
    from requests import Response


ADMIN_REQUEST_TIMEOUT: int = 60
_VERIFY_SSL: str = "_VERIFY_SSL_"
_LOG = "admin"

#
# Exceptions
#


class AccessDenied(RuntimeError):
    """
    Raised when the server denies an admin request
    """


class IllegalVersion(UsageError):
    """
    Raised when the server is running a version that is not supported
    """


#
# Helper Classes
#


@dataclass(frozen=True, kw_only=True)
class Conf:
    """
    A mini-config required to ask the server to run admin commands
    """

    sign: Callable[[bytes], bytes]
    session: Session
    url: str


class UIDGenerator:
    """
    A class to generate UIDs for admin requests
    """

    def __init__(self) -> None:
        self._uids: deque[str] = deque()

    def __call__(self, conf) -> str:
        if len(self._uids) == 0:
            r = conf.session.get(f"{conf.url}/admin/uid", timeout=ADMIN_REQUEST_TIMEOUT)
            self._uids += r.json()
        return self._uids.popleft()


#
# Main Classes
#


class _Methods:
    """
    Methods that can be called by the Admin class
    These methods may return sensitive data and should only be used with SSL
    Any public function may require SSL by invoke it with the prefix _VERIFY_SSL
    All functions require conf
    """

    def __init__(self):
        self._log = getLogger(_LOG)
        self._gen_uid = UIDGenerator()

    def __getattribute__(self, item: str) -> Any:
        """
        If a pulic methods is prefixed with _VERIFY_SSL, require SSL
        """
        if item.startswith(_VERIFY_SSL):
            return self._require_ssl(getattr(self, item[len(_VERIFY_SSL) :]))
        return super().__getattribute__(item)

    def _require_ssl(self, func: Callable) -> Callable:
        def wrapper(*args, conf: Conf, **kwargs):
            if not self._debug(conf) and all(i not in conf.url for i in ("https", ":443/")):
                raise RuntimeError("Refusing to send admin request to server in release mode over plaintext")
            return func(*args, conf=conf, **kwargs)

        return wrapper

    def _request(self, conf: Conf, path: str, args: dict[str, str] | None = None) -> Response:
        """
        Send a request to the server
        """
        args = {} if args is None else args
        uid: str = self._gen_uid(conf)
        self._log.info("Signing request for path=%s with args=%s", path, args)
        signature: bytes = conf.sign(AdminMessage(path=path, args=args, uid=uid).bytes())
        data = AdminPOST(signature=signature, uid=uid, version=str(version)).json()
        ret = conf.session.post(f"{conf.url}{path}", json=data, timeout=ADMIN_REQUEST_TIMEOUT)
        match ret.status_code:
            case 401:
                self._log.critical("Admin access denied")
                raise AccessDenied()
            case 426:
                raise IllegalVersion(ret.text, log=self._log.critical)
            case _:
                return ret

    def _debug(self, conf: Conf) -> bool:
        """
        :return: True if the server is in debug mode, else False
        """
        r = self._request(conf, "/admin/debug")
        if not r.ok:
            msg = f"Failed to get debug information: {r.status_code}"
            self._log.error(msg)
            raise RuntimeError(msg)
        return r.text == "True"

    def debug(self, conf: Conf) -> None:
        """
        Check to see if the server is in debug mode
        This method should only be used by an admin, but is safe to be used without SSL
        """
        print(f"Server is running in {'DEBUG' if self._debug(conf) else 'RELEASE'} mode")

    def channels(self, conf: Conf) -> None:
        """
        Request information about the channels the server has
        """
        r = self._request(conf, "/admin/channels")
        match r.status_code:
            case 200:
                raw = r.json()
            case 400:
                msg = f"Bad Request 400: {r.text}"
                self._log.critical(msg)
                raise RuntimeError(msg)
            case _:
                msg = f"Error {r.status_code}: {r.text}"
                self._log.critical(msg)
                raise RuntimeError(msg)
        if not raw:
            print("Server is empty")
            return
        for i in raw.values():
            i["expire"] = datetime.fromisoformat(i["expire"])
        data = {i: ChannelInfo(**k) for i, k in r.json().items()}
        mx = max(len(i) for i in data)
        print("\n".join(f"{i.ljust(mx)} : {k}" for i, k in data.items()))


class Admin:
    """
    A class used to ask the server to run admin functions
    """

    def __init__(self):
        self._log = getLogger(_LOG)
        self._methods = _Methods()

    def _load_ssh_key_file(self, key_file: Path) -> Callable[[bytes], bytes]:
        if not key_file.exists():
            raise UsageError(f"Key file {key_file} does not exist", log=self._log.critical)
        try:
            key = load_ssh_private_key(key_file.read_bytes(), None)
        except UnsupportedAlgorithm as e:
            raise UsageError(f"Key file {key_file} is not a supported ssh key", log=self._log.critical) from e
        if not hasattr(key, "sign"):
            raise UsageError(f"Key file {key_file} does not support signing", log=self._log.critical)
        if TYPE_CHECKING:
            return cast(Callable[[bytes], bytes], key.sign)
        return key.sign

    @cache  # pylint: disable=method-cache-max-size-none
    def _get_conf(self, raw_url: str | None, raw_key_file: Path | None):
        """
        Extract a Conf from the given arguments and existing config file
        Saves the config internally
        """
        self._log.info("Determining Conf; defaults: url=%s, key_file=%s", raw_url, raw_key_file)
        # Load data from config file
        try:
            path = ConfigFile().path
            self._log.info("Querying config file %s if it exists", path)
            raw = loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            key_file = Path(Option(raw_key_file).opt(raw.get("key_file", None)).value)
            url: str = Option(raw_url).opt(raw.get("url", None)).value
        except Exception as e:
            msg = "Admin mode requires a URL and key file to be set or provided via the CLI"
            raise UsageError(msg, log=self._log.critical) from e
        self._log.info("Found key file: %s, extracting private key", key_file)
        # Load ssh key
        return Conf(sign=self._load_ssh_key_file(key_file), url=url, session=Session())

    def _conf(self, func):
        def wrapper(*args, **kwargs):
            conf = self._get_conf(kwargs.pop("url"), kwargs.pop("key_file"))
            return func(*args, conf=conf, **kwargs)

        return wrapper

    def __getattribute__(self, item: str) -> Any:
        """
        Override the getattribute method to expose all methods of Methods
        """
        if item.startswith("_") or item == "load_keys":
            return super().__getattribute__(item)
        if item == "debug":
            return self._conf(self._methods.debug)
        return self._conf(getattr(self._methods, f"{_VERIFY_SSL}{item}"))
