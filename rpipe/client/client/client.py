from dataclasses import dataclass
from logging import getLogger
from json import dumps

from human_readable import listing

from ...shared import TRACE, QueryEC
from ..config import ConfigFile, Option, PartialConfig
from .util import REQUEST_TIMEOUT, request
from .errors import UsageError, VersionError
from .delete import delete
from .recv import recv
from .send import send

_LOG: str = "client"


# pylint: disable=too-many-instance-attributes
@dataclass(kw_only=True, frozen=True)
class Mode:
    """
    Arguments used to decide how rpipe should operate
    """

    # Priority modes (in order)
    print_config: bool
    save_config: bool
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
    # Read / Write options
    encrypt: Option[bool]
    progress: bool | int


def _check_mode_flags(mode: Mode) -> None:
    def tru(x) -> bool:
        rv = getattr(mode, x)
        return (False if rv.is_none() else rv.value) if isinstance(rv, Option) else bool(rv)

    # Flag specific checks
    if mode.ttl is not None and mode.ttl <= 0:
        raise UsageError("--ttl must be positive")
    if mode.progress is not False and mode.progress <= 0:
        raise UsageError("--progress argument must be positive if passed")
    # Sanity check
    n_priority = (mode.print_config, mode.save_config, mode.server_version).count(True)
    if n_priority > 1:
        raise UsageError("Only one priority mode may be used at a time")
    if (mode.read, mode.write, mode.delete).count(True) != 1:
        raise UsageError("Can only read, write, or delete at a time")
    # Mode flags
    read_bad = {"ttl"}
    write_bad = {"block", "peek", "force"}
    delete_bad = read_bad | write_bad | {"progress", "encrypt"}
    bad = lambda x: [f"--{i}" for i in x if tru(i)]
    fmt = lambda x: f"argument{'' if len(x) == 1 else 's'} {listing(x, ',', 'and') }: may not be used "
    if n_priority > 0 and (args := bad(delete_bad)):
        raise UsageError(fmt(args) + "with priority modes")
    # Mode specific flags
    if mode.read and (args := bad(read_bad)):
        raise UsageError(fmt(args) + "when reading data from the pipe")
    if mode.write and (args := bad(write_bad)):
        raise UsageError(fmt(args) + "when writing data to the pipe")
    if mode.delete and (args := bad(delete_bad)):
        raise UsageError(fmt(args) + "when deleting data from the pipe")


def _query(conf: PartialConfig) -> None:
    log = getLogger(_LOG)
    log.info("Mode: Query")
    if conf.url is None:
        raise UsageError("URL unknown; try again with --url")
    if conf.channel is None:
        raise UsageError("Channel unknown; try again with --channel")
    log.info("Querying channel %s ...", conf.channel)
    r = request("GET", f"{conf.url.value}/q/{conf.channel.value}")
    log.debug("Got response %s", r)
    log.log(TRACE, "Data: %s", r.content)
    match r.status_code:
        case QueryEC.illegal_version:
            raise VersionError(f"Server requires version >= {r.text}")
        case QueryEC.no_data:
            print("No data on this channel")
            return
    if not r.ok:
        raise RuntimeError(f"Query failed. Error {r.status_code}: {r.text}")
    print(f"{conf.channel.value}: {dumps(r.json(), indent=4)}")


def _priority_actions(conf: PartialConfig, mode: Mode, config_file) -> PartialConfig | None:
    log = getLogger(_LOG)
    # Print config if requested
    if mode.print_config:
        config_file.print()
        return None
    # Load pipe config and save is requested
    conf = config_file.load_onto(conf, mode.encrypt.is_false())
    log.info("Loaded %s", conf)
    if mode.save_config:
        config_file.save(conf, mode.encrypt.is_true())
        return None
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
        return None
    if mode.query:
        _query(conf)
        return None

    return conf


def rpipe(conf: PartialConfig, mode: Mode) -> None:
    """
    rpipe: A remote piping tool
    Assumes no UsageError's in mode that argparse would catch
    """
    config_file = ConfigFile()
    log = getLogger(_LOG)
    log.info("Config file: %s", config_file.path)
    _check_mode_flags(mode)
    loaded: PartialConfig | None = _priority_actions(conf, mode, config_file)
    if loaded is None:
        return
    # Finish creating config
    if mode.write and not mode.encrypt.is_none():
        log.info("Write mode: No password found, falling back to plaintext mode")
    full_conf = config_file.verify(loaded, mode.encrypt.is_true())
    # Invoke mode
    log.info("HTTP timeout set to %d seconds", REQUEST_TIMEOUT)
    if mode.read:
        recv(full_conf, mode.block, mode.peek, mode.force, mode.progress)
    elif mode.write:
        send(full_conf, mode.ttl, mode.progress)
    else:
        delete(full_conf)
