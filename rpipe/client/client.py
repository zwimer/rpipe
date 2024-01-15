from dataclasses import dataclass
from logging import getLogger

from .util import REQUEST_TIMEOUT, channel_url, request_simple, request
from .config import ConfigFile, Config
from .errors import UsageError
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
    # These variables do *not* cover implicit deductions
    encrypt: bool
    plaintext: bool
    # Read/Write/Clear options
    read: bool
    peek: bool
    force: bool
    clear: bool


def rpipe(conf: Config, mode: Mode) -> None:
    """
    rpipe: A remote piping tool
    Assumse no UsageError's in mode that argparse would catch
    """
    config_file = ConfigFile()
    log = getLogger(_LOG)
    log.debug("Config file: %s", config_file.fname)
    if not mode.read and mode.clear:
        raise UsageError("--clear may not be used when writing data to the pipe")
    if not mode.read and mode.peek:
        raise UsageError("--peek may not be used when writing data to the pipe")
    if mode.print_config:
        config_file.print()
        return
    # Load pipe config and save is requested
    conf = config_file.load_onto(conf, mode.plaintext)
    msg = "Loaded config with:\n  url = %s\n  channel = %s\n  has password: %s"
    log.debug(msg, conf.url, conf.channel, conf.password is not None)
    if mode.save_config:
        config_file.save(conf, mode.encrypt)
        return
    # Print server version if requested
    if mode.server_version:
        log.debug("Mode: Server version")
        if conf.url is None:
            raise UsageError("URL unknown; try again with --url")
        print(request_simple(conf.url, "version"))
        return
    # Check config
    if not (mode.encrypt or mode.plaintext or mode.read or mode.clear):
        log.info("Write mode: No password found, falling back to --plaintext")
    valid_conf = config_file.verify(conf, mode.encrypt)
    # Invoke mode
    log.debug("HTTP timeout set to %d seconds", REQUEST_TIMEOUT)
    if mode.clear:
        getLogger(_LOG).debug("Clearing channel %s", valid_conf.channel)
        r = request("DELETE", channel_url(valid_conf))
        if not r.ok:
            raise RuntimeError(f"Unexpected status code: {r.status_code}\nBody: {r.text}")
    elif mode.read:
        recv(valid_conf, mode.peek, mode.force)
    else:
        send(valid_conf)
