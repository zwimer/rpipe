from dataclasses import dataclass, asdict
from logging import getLogger
from copy import deepcopy
from pathlib import Path
import json
import os

from .option import Option
from ..errors import UsageError


PASSWORD_ENV: str = "RPIPE_PASSWORD"
CONFIG_FILE_ENV = "RPIPE_CONFIG_FILE"

_DEFAULT = Path.home() / ".config" / "rpipe.json"


@dataclass(kw_only=True, frozen=True)
class PartialConfig:
    """
    Information about where the remote pipe is
    """

    ssl: Option[bool]
    url: Option[str]
    channel: Option[str]
    password: Option[str]


@dataclass(kw_only=True, frozen=True)
class Config:
    """
    Information about where the remote pipe is
    """

    ssl: bool
    url: str
    channel: str
    password: str


class ConfigFile:
    _log = getLogger("ConfigFile")

    def __init__(self):
        self.fname = Path(os.environ.get(CONFIG_FILE_ENV, _DEFAULT))

    def load_onto(self, conf: PartialConfig, plaintext: bool) -> PartialConfig:
        self._log.debug("Generating config...")
        ret = deepcopy(conf)
        raw = json.loads(self.fname.read_text(encoding="utf-8")) if self.fname.exists() else {}
        ret.ssl.opt(raw.get("ssl", True))
        ret.url.opt(raw.get("url", None))
        ret.channel.opt(raw.get("channel", None))
        if not plaintext:
            ret.password.opt(os.getenv(PASSWORD_ENV))
            ret.password.opt(raw.get("password", ""))
        return ret

    def save(self, conf: PartialConfig, encrypt: bool) -> None:
        self._log.debug("Mode: save-config")
        if encrypt and os.environ.get(PASSWORD_ENV, None) is None:
            raise UsageError(f"--save-config --encrypt requires {PASSWORD_ENV} be set")
        parent = self.fname.parent
        if not parent.exists():
            self._log.debug("Creating directory %s", parent)
            parent.mkdir(exist_ok=True)
        self._log.debug("Saving config %s", conf)
        self.fname.write_text(json.dumps({i: k.get() for i, k in asdict(conf).items()}), encoding="utf-8")
        self._log.info("Config saved")

    def print(self) -> None:
        self._log.debug("Mode: print-config")
        print(f"Config file: {self.fname}")
        if not self.fname.exists():
            print("No saved config")
            return
        raw = self.fname.read_text(encoding="utf-8")
        try:
            print(PartialConfig(**json.loads(raw)))
        except TypeError:
            print(f"Failed to load config: {raw}")

    @classmethod
    def verify(cls, conf: PartialConfig, encrypt: bool) -> Config:
        cls._log.debug("Validating config...")
        if conf.url.is_none():
            raise UsageError("Missing: --url")
        if conf.channel.is_none():
            raise UsageError("Missing: --channel")
        if encrypt and not conf.password:
            raise UsageError("Missing: --encrypt requires a password")
        ret = Config(
            url=conf.url.value,
            channel=conf.channel.value,
            ssl=conf.ssl.value,
            password=conf.password.value,
        )
        if ret.ssl and not ret.url.startswith("https://"):
            raise UsageError(
                "SSL is required but URL does not start https scheme."
                " If raw http is desired, consider --no-require-ssl"
            )
        return ret
