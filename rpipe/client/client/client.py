from dataclasses import dataclass
from logging import getLogger

from ..config import ConfigFile, Option, PartialConfig
from .util import REQUEST_TIMEOUT, request
from .errors import UsageError
from .clear import clear
from .recv import recv
from .send import send

_LOG: str = "client"


# pylint: disable=too-many-instance-attributes
@dataclass(kw_only=True, frozen=True)
class Mode:
    """
    Arguments used to decide how rpipe should operate
    """

    # Priority (in order)
    print_config: bool
    save_config: bool
    server_version: bool
    # Whether the user *explicitly* requested encryption or plaintext
    encrypt: Option[bool]
    # Read/Write/Clear modes
    read: bool
    peek: bool
    clear: bool
    # Other options
    progress: bool | int
    ttl: int | None
    force: bool


# pylint: disable=too-many-branches
def rpipe(conf: PartialConfig, mode: Mode) -> None:
    """
    rpipe: A remote piping tool
    Assumes no UsageError's in mode that argparse would catch
    """
    config_file = ConfigFile()
    log = getLogger(_LOG)
    log.info("Config file: %s", config_file.path)
    write = not (mode.read or mode.clear)
    if not mode.read and mode.clear:
        raise UsageError("--clear may not be used when writing data to the pipe")
    if not mode.read and mode.peek:
        raise UsageError("--peek may not be used when writing data to the pipe")
    if mode.progress is not False:
        if mode.progress <= 0:
            raise UsageError("--progress may not be passed a non-positive number of bytes")
        if mode.clear:
            raise UsageError("--progress may not be used when clearing the pipe")
    if mode.print_config:
        config_file.print()
        return
    # Load pipe config and save is requested
    conf = config_file.load_onto(conf, mode.encrypt.is_false())
    log.info("Loaded %s", conf)
    if mode.save_config:
        config_file.save(conf, mode.encrypt.is_true())
        return
    # Print server version if requested
    if mode.server_version:
        log.info("Mode: Server version")
        if conf.url is None:
            raise UsageError("URL unknown; try again with --url")
        log.info("Requesting server version...")
        r = request("GET", f"{conf.url.value}/version")
        if not r.ok:
            raise RuntimeError(f"Failed to get version: {r}")
        print(f"rpipe_server {r.text}")
        return
    # Check ttl usage
    if mode.ttl and not write:
        raise UsageError("--ttl may only be used when writing")
    # Check config
    if write and not mode.encrypt.is_none():
        log.info("Write mode: No password found, falling back to plaintext mode")
    full_conf = config_file.verify(conf, mode.encrypt.is_true())
    # Invoke mode
    log.info("HTTP timeout set to %d seconds", REQUEST_TIMEOUT)
    if mode.clear:
        clear(full_conf)
    elif mode.read:
        recv(full_conf, mode.peek, mode.force, mode.progress)
    else:
        send(full_conf, mode.ttl, mode.progress)
