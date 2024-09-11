from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import TYPE_CHECKING
from logging import getLogger
from copy import deepcopy
from pathlib import Path
import json
import os

from .option import Option

if TYPE_CHECKING:
    from collections.abc import Callable


PASSWORD_ENV: str = "RPIPE_PASSWORD"
CONFIG_FILE_ENV = "RPIPE_CONFIG_FILE"

_DEFAULT = Path.home() / ".config" / "rpipe.json"


class UsageError(ValueError):
    """
    Raised when the user used the client incorrectly (ex. CLI args)
    """

    def __init__(self, msg: str, log: Callable | None = None):
        if log is not None:
            log(msg)
        super().__init__(msg)


@dataclass(kw_only=True, frozen=True)
class PartialConfig:
    """
    Information about where the remote pipe is
    """

    ssl: Option[bool]
    url: Option[str]
    channel: Option[str]
    password: Option[str]
    key_file: Option[Path | None]

    def __repr__(self):
        d = asdict(self)
        d["password"] = d["password"] is not None
        return "Config:\n  " + "\n  ".join(f"{i}: {k}" for i, k in d.items())


@dataclass(kw_only=True, frozen=True)
class Config:
    """
    Information about where the remote pipe is
    """

    ssl: bool
    url: str
    channel: str
    password: str
    key_file: Path | None


class ConfigFile:
    _log = getLogger("ConfigFile")

    def __init__(self):
        self.path = Path(os.environ.get(CONFIG_FILE_ENV, _DEFAULT))

    def load_onto(self, conf: PartialConfig, plaintext: bool) -> PartialConfig:
        self._log.info("Generating config with plaintext=%s", plaintext)
        ret = deepcopy(conf)
        raw = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        ret.ssl.opt(raw.get("ssl", True))
        ret.url.opt(raw.get("url", None))
        ret.channel.opt(raw.get("channel", None))
        if not plaintext:
            ret.password.opt(os.getenv(PASSWORD_ENV))
            ret.password.opt(raw.get("password", ""))
        ret.password.opt("")
        kf = raw.get("key_file", None)
        ret.key_file.opt(None if kf is None else Path(kf))
        return ret

    def save(self, conf: PartialConfig, encrypt: bool) -> None:
        self._log.info("Mode: save-config")
        if encrypt and os.environ.get(PASSWORD_ENV, None) is None:
            raise UsageError(f"--save-config --encrypt requires {PASSWORD_ENV} be set")
        parent = self.path.parent
        if not parent.exists():
            self._log.info("Creating directory %s", parent)
            parent.mkdir(exist_ok=True)
        self._log.info("Saving config %s", conf)
        out_d = {i: k.get() for i, k in asdict(conf).items()}
        out_d["key_file"] = None if conf.key_file is None else str(conf.key_file)
        self.path.write_text(json.dumps(out_d), encoding="utf-8")
        self._log.info("Config saved")

    def print(self) -> None:
        self._log.info("Mode: print-config")
        print(f"Path: {self.path}")
        if not self.path.exists():
            print("No saved config")
            return
        raw = self.path.read_text(encoding="utf-8")
        try:
            kw = json.loads(raw)
            kf = kw.pop("key_file", None)
            kw["key_file"] = None if kf is None else Path(kf)
            print(PartialConfig(**kw))
        except TypeError:
            print(f"Failed to load config: {raw}")

    @classmethod
    def verify(cls, conf: PartialConfig, encrypt: bool) -> Config:
        cls._log.info("Validating config...")
        if conf.url.is_none():
            raise UsageError("Missing: --url")
        if conf.channel.is_none():
            raise UsageError("Missing: --channel")
        if encrypt and not conf.password:
            raise UsageError("Missing: --encrypt requires a password")
        if (kf := conf.key_file.get()) is not None and not kf.exists():
            cls._log.warning("Key file does not exist: %s", kf)
        ret = Config(
            url=conf.url.value,
            channel=conf.channel.value,
            ssl=conf.ssl.value,
            password=conf.password.value,
            key_file=conf.key_file.get(),
        )
        if ret.ssl and not ret.url.startswith("https://"):
            raise UsageError(
                "SSL is required but URL does not start https scheme."
                " If raw http is desired, consider --no-require-ssl"
            )
        return ret
