from dataclasses import dataclass, asdict
from logging import getLogger
from pathlib import Path
import json
import os

from .errors import UsageError


PASSWORD_ENV: str = "RPIPE_PASSWORD"
CONFIG_FILE_ENV = "RPIPE_CONFIG_FILE"

_DEFAULT = Path.home() / ".config" / "rpipe.json"


@dataclass(kw_only=True, frozen=True)
class Config:
    """
    Information about where the remote pipe is
    """

    url: str | None
    channel: str | None
    password: str | None


@dataclass(kw_only=True, frozen=True)
class ValidConfig:
    """
    Information about where the remote pipe is
    """

    url: str
    channel: str
    password: str | None


class ConfigFile:
    _log = getLogger("ConfigFile")

    def __init__(self):
        self.fname = Path(os.environ.get(CONFIG_FILE_ENV, _DEFAULT))

    def load_onto(self, conf: Config, plaintext: bool) -> Config:
        self._log.debug("Generating config...")
        password = None if plaintext else os.getenv(PASSWORD_ENV)
        raw = json.loads(self.fname.read_text(encoding="utf-8")) if self.fname.exists() else {}
        return Config(
            url=raw.get("url", None) if conf.url is None else conf.url,
            channel=raw.get("channel", None) if conf.channel is None else conf.channel,
            password=raw.get("password", None) if password is None and not plaintext else password,
        )

    def save(self, conf: Config, encrypt: bool) -> None:
        self._log.debug("Mode: save-config")
        if encrypt and os.environ.get(PASSWORD_ENV, None) is None:
            raise UsageError(f"--save-config --encrypt requires {PASSWORD_ENV} be set")
        parent = self.fname.parent
        if not parent.exists():
            self._log.debug("Creating directory %s", parent)
            parent.mkdir(exist_ok=True)
        self._log.debug("Saving config %s", conf)
        self.fname.write_text(json.dumps(asdict(conf)), encoding="utf-8")
        self._log.info("Config saved")

    def print(self) -> None:
        self._log.debug("Mode: print-config")
        print(f"Config file: {self.fname}")
        if not self.fname.exists():
            print("No saved config")
            return
        raw = self.fname.read_text(encoding="utf-8")
        try:
            print(Config(**json.loads(raw)))
        except TypeError:
            print(f"Failed to load config: {raw}")

    @classmethod
    def verify(cls, conf: Config, encrypt: bool) -> ValidConfig:
        cls._log.debug("Validating config...")
        if conf.url is None:
            raise UsageError("Missing: --url")
        if conf.channel is None:
            raise UsageError("Missing: --channel")
        if encrypt and conf.password is None:
            raise UsageError("Missing: --encrypt requires a password")
        return ValidConfig(**asdict(conf))
