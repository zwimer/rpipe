from dataclasses import dataclass
from logging import getLogger
from json import dumps

from zstandard import ZstdCompressor
from human_readable import listing


from ...shared import TRACE, QueryEC, Version, version
from ..config import ConfigFile, Option, PartialConfig
from .util import REQUEST_TIMEOUT, request
from .errors import UsageError, VersionError
from .delete import delete
from .recv import recv
from .send import send


_LOG: str = "client"
_DEFAULT_LVL: int = 3


# pylint: disable=too-many-instance-attributes
@dataclass(kw_only=True, frozen=True)
class Mode:
    """
    Arguments used to decide how rpipe should operate
    """

    # Priority modes (in order)
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
    encrypt: Option[bool]
    progress: bool | int


def _n_priority(mode: Mode) -> int:
    return (mode.print_config, mode.save_config, mode.outdated, mode.server_version, mode.query).count(True)


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
    if (n_pri := _n_priority(mode)) > 1:
        raise UsageError("Only one priority mode may be used at a time")
    if (mode.read, mode.write, mode.delete).count(True) != 1:
        raise UsageError("Can only read, write, or delete at a time")
    # Mode flags
    read_bad = {"ttl"}
    write_bad = {"block", "peek", "force"}
    delete_bad = read_bad | write_bad | {"progress", "encrypt"}
    bad = lambda x: [f"--{i}" for i in x if tru(i)]
    fmt = lambda x: f"argument{'' if len(x) == 1 else 's'} {listing(x, ',', 'and') }: may not be used "
    if n_pri > 0 and (args := bad(delete_bad)):
        raise UsageError(fmt(args) + "with priority modes")
    # Mode specific flags
    if mode.read and (args := bad(read_bad)):
        raise UsageError(fmt(args) + "when reading data from the pipe")
    if mode.write and (args := bad(write_bad)):
        raise UsageError(fmt(args) + "when writing data to the pipe")
    if mode.delete and (args := bad(delete_bad)):
        raise UsageError(fmt(args) + "when deleting data from the pipe")


def _check_outdated(conf: PartialConfig) -> None:
    log = getLogger(_LOG)
    log.info("Mode: Outdated")
    r = request("GET", f"{conf.url.value}/supported")
    if not r.ok:
        raise RuntimeError(f"Failed to get server minimum version: {r}")
    info = r.json()
    log.info("Server supports clients: %s", info)
    ok = Version(info["min"]) <= version and all(version != Version(i) for i in info["banned"])
    print(f"{'' if ok else 'NOT '}SUPPORTED")


def _query(conf: PartialConfig) -> None:
    log = getLogger(_LOG)
    log.info("Mode: Query")
    if conf.channel is None:
        raise UsageError("Channel unknown; try again with --channel")
    log.info("Querying channel %s ...", conf.channel)
    r = request("GET", f"{conf.url.value}/q/{conf.channel.value}")
    log.debug("Got response %s", r)
    log.log(TRACE, "Data: %s", r.content)
    match r.status_code:
        case QueryEC.illegal_version:
            raise VersionError(r.text)
        case QueryEC.no_data:
            print(f"No data on channel: {conf.channel.value}")
            return
    if not r.ok:
        raise RuntimeError(f"Query failed. Error {r.status_code}: {r.text}")
    print(f"{conf.channel.value}: {dumps(r.json(), indent=4)}")


def _priority_actions(conf: PartialConfig, mode: Mode, config_file) -> bool:
    if not (np := _n_priority(mode)):
        return False
    assert np == 1, "Sanity check on priority mode count failed"
    log = getLogger(_LOG)
    if mode.save_config:
        log.info("Mode: Save Config")
        config_file.save(conf, mode.encrypt.is_true())
        return True
    # Everything after this requires the URL
    if conf.url is None:
        raise UsageError("Missing: --url")
    # Check if supported
    if mode.outdated:
        _check_outdated(conf)
    # Print server version if requested
    if mode.server_version:
        log.info("Mode: Server Version")
        r = request("GET", f"{conf.url.value}/version")
        if not r.ok:
            raise RuntimeError(f"Failed to get version: {r}")
        print(f"rpipe_server {r.text}")
    if mode.query:
        _query(conf)
    return True


def rpipe(conf: PartialConfig, mode: Mode) -> None:
    """
    rpipe: A remote piping tool
    Assumes no UsageError's in mode that argparse would catch
    """
    _check_mode_flags(mode)
    log = getLogger(_LOG)
    config_file = ConfigFile()
    log.info("Config file: %s", config_file.path)
    # Print config if requested, else load it
    if mode.print_config:
        log.info("Mode: Print Config")
        config_file.print()
        return
    conf = config_file.load_onto(conf, mode.encrypt.is_false())
    # Remaining priority actions + finish creating config
    if _priority_actions(conf, mode, config_file):
        return
    if mode.write and not mode.encrypt.is_none():
        log.info("Write mode: No password found, falling back to plaintext mode")
    full_conf = config_file.verify(conf, mode.encrypt.is_true())
    if (mode.read or mode.write) and not conf.password:
        log.warning("Encryption disabled: plaintext mode")
        if mode.zstd is not None:
            raise UsageError("Cannot compress data in plaintext mode")
    # Invoke mode
    log.info("HTTP timeout set to %d seconds", REQUEST_TIMEOUT)
    if mode.read:
        recv(full_conf, mode.block, mode.peek, mode.force, mode.progress)
    elif mode.write:
        lvl = _DEFAULT_LVL if mode.zstd is None else mode.zstd
        log.debug("Using compression level %d and %d threads", lvl, mode.threads)
        compress = ZstdCompressor(write_checksum=True, level=lvl, threads=mode.threads).compress
        send(full_conf, mode.ttl, mode.progress, compress)
    else:
        delete(full_conf)
