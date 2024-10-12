from __future__ import annotations
from dataclasses import dataclass, asdict, fields
from typing import TYPE_CHECKING
from urllib.parse import quote
from json import loads, dumps
from logging import getLogger
from pathlib import Path

from human_readable import listing

from .errors import UsageError

if TYPE_CHECKING:
    from typing import Self


_CONFIG_LOG: str = "Config"


@dataclass(kw_only=True, frozen=True)
class Config:
    """
    Information about where the remote pipe is
    """

    ssl: bool = True
    url: str = ""
    channel: str = ""
    password: str = ""
    key_file: Path | None = None

    def __post_init__(self):
        if self.key_file and self.key_file.suffix == ".pub":
            getLogger(_CONFIG_LOG).warning("Signing key should be a private key: %s", self.key_file)

    def channel_url(self) -> str:
        return f"{self.url}/c/{quote(self.channel)}"

    @classmethod
    def keys(cls) -> tuple[str, ...]:
        return tuple(i.name for i in fields(cls))

    @classmethod
    def load(cls, cli: dict[str, bool | str | Path | None], file: Path) -> Self:
        """
        Preference: CLI > Config file > Default
        """
        log = getLogger(_CONFIG_LOG)
        conf = asdict(Config())
        # Load config file then cli args
        if file.exists():
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
        file.write_text(dumps(asdict(self), default=str), encoding="utf-8")
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
@dataclass(kw_only=True, frozen=True)
class Mode:
    """
    Arguments used to decide how rpipe should operate
    Only one priority mode may be used at a time
    """

    # Priority modes
    print_config: bool
    save_config: bool
    outdated: bool
    server_version: bool
    query: bool
    # Read/Write/Delete modes
    read: bool
    delete: bool
    write: bool
    # Read options
    block: bool
    peek: bool
    force: bool
    # Write options
    ttl: int | None
    zstd: int | None
    threads: int
    # Read / Write options
    encrypt: bool
    progress: bool | int

    @classmethod
    def keys(cls) -> tuple[str, ...]:
        return tuple(i.name for i in fields(cls))

    def priority(self) -> bool:
        c = (self.print_config, self.save_config, self.outdated, self.server_version, self.query).count(True)
        assert c <= 1, "Sanity check on priority mode count failed"
        return c > 0
