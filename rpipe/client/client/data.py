from dataclasses import dataclass, asdict, fields
from typing import TYPE_CHECKING
from urllib.parse import quote
from json import loads, dumps
from logging import getLogger
from hashlib import blake2s
from pathlib import Path

from human_readable import listing

from .errors import UsageError

if TYPE_CHECKING:
    from typing import Self


_CONFIG_LOG: str = "Config"
_CONFIG_FILE_PERMISSIONS: int = 0o600


@dataclass(init=False, slots=True)
class Result:
    """
    Result of a successful send/receive
    """

    checksum: blake2s | None
    total: int | None

    def __init__(self, total: bool, checksum: bool) -> None:
        self.checksum = blake2s(usedforsecurity=False) if checksum else None
        self.total = 0 if total else None


@dataclass(kw_only=True, frozen=True, slots=True)
class Config:
    """
    Information about where the remote pipe is
    """

    ssl: bool = True
    url: str = ""
    channel: str = ""
    password: str = ""
    timeout: int | None = None
    key_file: Path | None = None

    def __post_init__(self):
        if self.key_file and self.key_file.suffix == ".pub":
            getLogger(_CONFIG_LOG).warning("Signing key should be a private key: %s", self.key_file)

    def channel_url(self) -> str:
        return f"{self.url}/c/{quote(self.channel)}"

    @classmethod
    def keys(cls) -> list[str]:
        return [i.name for i in fields(cls)]

    @classmethod
    def load(cls, cli: dict[str, bool | str | Path | None], file: Path) -> Self:
        """
        Preference: CLI > Config file > Default
        """
        log = getLogger(_CONFIG_LOG)
        conf = asdict(Config())
        # Load config file then cli args
        if file.exists():
            file.chmod(_CONFIG_FILE_PERMISSIONS)  # Update permissions in case permissions are bad
            log.debug("Loading config file %s", file)
            conf.update(loads(file.read_text(encoding="utf-8")))
        else:
            log.warning("Config file does not exist: %s", file)
        conf.update({i: k for i, k in cli.items() if k is not None})
        # Finish
        if conf["key_file"] is not None:
            conf["key_file"] = Path(conf["key_file"])
        return cls(**conf)

    def save(self, file: Path) -> None:
        log = getLogger(_CONFIG_LOG)
        log.info("Mode: save-config")
        if not file.parent.exists():
            log.debug("Creating directory %s", file.parent)
            file.parent.mkdir(exist_ok=True)
        log.info("Saving config %s", self)
        if not file.exists():
            log.warning("Creating config file: %s", file)
            file.touch(mode=_CONFIG_FILE_PERMISSIONS)
            log.debug("Permissions set to: %s", oct(_CONFIG_FILE_PERMISSIONS))
        file.write_text(dumps(asdict(self), default=str), encoding="utf-8")
        file.chmod(_CONFIG_FILE_PERMISSIONS)  # Update permissions in case permissions are bad
        log.info("Config saved to %s", file)

    def validate(self) -> None:
        log = getLogger(_CONFIG_LOG)
        log.info("Validating config...")
        if missing := [i[1] for i in ((self.url, "URL"), (self.channel, "CHANNEL")) if not i[0]]:
            raise UsageError(f"Missing: {listing(missing, separator=",")}")
        if self.ssl and not self.url.startswith("https://"):
            raise UsageError(
                "SSL is required but URL does not start https scheme."
                " If raw http is desired, consider disabling SSL"
            )
        if self.key_file is not None and not self.key_file.exists():
            log.warning("Key file does not exist: %s", self.key_file)

    def __str__(self) -> str:
        d = asdict(self) | {"password": bool(self.password)}  # Do not leak password
        return "Config (with CLI overrides):\n  " + "\n  ".join(f"{i}: {k}" for i, k in d.items())

    def __repr__(self) -> str:
        return str(asdict(self))


# pylint: disable=too-many-instance-attributes
@dataclass(kw_only=True, frozen=True, slots=True)
class Mode:
    """
    Arguments used to decide how rpipe should operate
    Only one priority mode may be used at a time
    """

    # Priority modes
    print_config: bool
    update_config: bool
    outdated: bool
    server_version: bool
    blocked: bool
    query: bool
    # Recv/Send/Delete modes
    recv: bool
    send: bool
    delete: bool
    # Recv options
    block: bool
    peek: bool
    force: bool
    yes: bool
    # Send options
    file: Path | None  # None means sys.stdin if dir is None
    dir: Path | None
    ttl: int | None
    zstd: int | None
    threads: int
    # Recv / Send options
    encrypt: bool
    progress: bool | int | None  # None means 'False, but change as desired'
    total: bool
    checksum: bool

    @classmethod
    def keys(cls) -> list[str]:
        return [i.name for i in fields(cls)]

    def priority(self) -> bool:
        c = (
            self.print_config,
            self.update_config,
            self.outdated,
            self.server_version,
            self.blocked,
            self.query,
        ).count(True)
        assert c <= 1, "Sanity check on priority mode count failed"
        return c > 0
