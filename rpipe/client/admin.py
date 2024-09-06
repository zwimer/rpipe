from __future__ import annotations
from typing import TYPE_CHECKING, override
from dataclasses import dataclass
from datetime import datetime
from logging import getLogger
from functools import cache
from pathlib import Path
from json import loads

from cryptography.hazmat.primitives.serialization import load_ssh_private_key
from cryptography.exceptions import UnsupportedAlgorithm
from requests import Session

from ..shared import ChannelInfo
from .config import ConfigFile, UsageError, Option

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any, cast


ADMIN_REQUEST_TIMEOUT: int = 60
_LOG = "admin"


@dataclass(frozen=True, kw_only=True)
class Conf:
    """
    A mini-config required to ask the server to run admin commands
    """

    sign: Callable[[bytes], bytes]
    url: str


class Methods:
    """
    Methods that can be called by the Admin class
    """

    def __init__(self):
        self._log = getLogger(_LOG)

    def _debug(self, conf: Conf, session: Session) -> bool:
        """
        Request the server to print debug information
        """
        path = "/admin/debug"
        self._log.debug("Signing request for path %s", path)
        signature: bytes = conf.sign(f"{path}?|{{}}".encode())
        r = session.post(f"{conf.url}{path}", data=signature, timeout=ADMIN_REQUEST_TIMEOUT)
        if not r.ok:
            msg = f"Failed to get debug information: {r.status_code}"
            self._log.error(msg)
            raise RuntimeError(msg)
        return r.text == "True"

    def debug(self, conf: Conf) -> None:
        """
        Request the server to print debug information
        """
        try:
            print(f"Server is running in {'DEBUG' if self._debug(conf, Session()) else 'RELEASE'} mode")
        except RuntimeError as e:
            print(e.args[0])

    def channels(self, conf: Conf) -> None:
        """
        Request information about the channels the server has
        """
        session = Session()
        if not self._debug(conf, session) and all(i not in conf.url for i in ("https", ":443/")):
            raise RuntimeError("Refusing to send admin request to server in release mode over plaintext")
        path = "/admin/channels"
        self._log.debug("Signing request for path %s", path)
        signature: bytes = conf.sign(f"{path}?|{{}}".encode())
        r = session.post(f"{conf.url}{path}", data=signature, timeout=ADMIN_REQUEST_TIMEOUT)
        match r.status_code:
            case 400:
                self._log.critical("Admin access denied")
                return
            case 200:
                raw = r.json()
            case _:
                self._log.error("Unknown error: %s", r.status_code)
                return
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
        self._methods = Methods()

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
        self._log.debug("Determining Conf; defaults: url=%s, key_file=%s", raw_url, raw_key_file)
        # Load data from config file
        try:
            path = ConfigFile().path
            self._log.debug("Querying config file %s if it exists", path)
            raw = loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            key_file = Path(Option(raw_key_file).opt(raw.get("key_file", None)).value)
            url: str = Option(raw_url).opt(raw.get("url", None)).value
        except Exception as e:
            msg = "Admin mode requires a URL and key file to be set or provided via the CLI"
            raise UsageError(msg, log=self._log.critical) from e
        self._log.debug("Found key file: %s, extracting private key", key_file)
        # Load ssh key
        return Conf(sign=self._load_ssh_key_file(key_file), url=url)

    def _wrap(self, func):
        def wrapper(*args, **kwargs):
            return func(*args, conf=self._get_conf(kwargs.pop("url"), kwargs.pop("key_file")), **kwargs)

        return wrapper

    @override
    def __getattribute__(self, item: str) -> Any:
        """
        Override the getattribute method to expose all methods of Methods
        """
        if item.startswith("_") or item == "load_keys":
            return super().__getattribute__(item)
        return self._wrap(getattr(self._methods, item))
