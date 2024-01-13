from dataclasses import dataclass, asdict, fields
from base64 import b64encode, b64decode
from typing import TYPE_CHECKING
from urllib.parse import quote
from pathlib import Path
import argparse
import logging
import hashlib
import json
import zlib
import sys
import os

from Cryptodome.Random import get_random_bytes
from Cryptodome.Cipher import AES
from requests import Request, Session

from ._shared import WriteCode, ReadCode, Headers
from ._version import __version__

if TYPE_CHECKING:
    from requests import Response


CONFIG_FILE = Path(os.environ.get("RPIPE_CONFIG_FILE", Path.home() / ".config" / "rpipe.json"))
_PASSWORD_ENV: str = "RPIPE_PASSWORD"
_ZLIB_LEVEL: int = 6
_TIMEOUT: int = 60


logging.basicConfig(level=logging.WARNING, format="%(message)s")


#
# Classes
#


class UsageError(ValueError):
    pass


class VersionError(UsageError):
    pass


class NoData(ValueError):
    pass


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


# pylint: disable=too-many-instance-attributes
@dataclass(kw_only=True, frozen=True)
class Mode:
    """
    Arguments used to decide how rpipe should operate
    """

    # Priority
    print_config: bool  # Priority
    save_config: bool  # Priority
    # Whether the user *explicitly* requested encryption or plaintext
    # These variables do *not* cover implicit deductions
    encrypt: bool
    plaintext: bool
    # Read/Write/Clear options
    read: bool
    peek: bool
    force: bool
    clear: bool


#
# Helpers
#


def _crypt(encrypt: bool, data: bytes, password: str | None) -> bytes:
    if password is None:
        return data
    opts = {"password": password.encode(), "n": 2**14, "r": 8, "p": 1, "dklen": 32}
    mode = AES.MODE_GCM
    if encrypt:
        salt = get_random_bytes(AES.block_size)
        conf = AES.new(hashlib.scrypt(salt=salt, **opts), mode)  # type: ignore
        text, tag = conf.encrypt_and_digest(zlib.compress(data, level=_ZLIB_LEVEL))
        return b".".join(b64encode(i) for i in (text, salt, conf.nonce, tag))
    text, salt, nonce, tag = (b64decode(i) for i in data.split(b"."))
    aes = AES.new(hashlib.scrypt(salt=salt, **opts), mode, nonce=nonce)  # type: ignore
    return zlib.decompress(aes.decrypt_and_verify(text, tag))


def _request(*args, **kwargs) -> "Response":
    r = Request(*args, **kwargs).prepare()
    logging.debug("Preparing request:\n  %s %s", r.method, r.url)
    for i, k in r.headers.items():
        logging.debug("    %s: %s", i, k)
    if r.body:
        logging.debug("  len(request.body) = %d", len(r.body))
    logging.debug("  timeout=%d", _TIMEOUT)
    ret = Session().send(r, timeout=_TIMEOUT)
    return ret


#
# Actions
#


def _recv(config: ValidConfig, peek: bool, force: bool) -> None:
    """
    Receive data from the remote pipe
    """
    logging.debug("Reading from channel %s with peek=%s and force=%s", config.channel, peek, force)
    r = _request(
        "GET",
        f"{config.url}/{'peek' if peek else 'read'}/{quote(config.channel)}",
        headers={Headers.client_version: __version__, Headers.version_override: str(force)},
    )
    match r.status_code:
        case ReadCode.ok:
            encrypted = r.headers.get(Headers.encrypted, "False") == "True"
            sys.stdout.buffer.write(_crypt(False, r.content, config.password if encrypted else None))
            sys.stdout.flush()
        case ReadCode.wrong_version:
            raise VersionError(f"Version mismatch; uploader version = {r.text}; force a read with --force")
        case ReadCode.illegal_version:
            raise VersionError(f"Server requires version >= {r.text}")
        case ReadCode.no_data:
            raise NoData(f"The channel {config.channel} is empty.")
        case _:
            raise RuntimeError(f"Unknown status code: {r.status_code}\nBody: {r.text}")


def _send(config: ValidConfig) -> None:
    """
    Send data to the remote pipe
    """
    logging.debug("Writing to channel %s", config.channel)
    data = _crypt(True, sys.stdin.buffer.read(), config.password)
    r = _request(
        "POST",
        f"{config.url}/write/{quote(config.channel)}",
        headers={
            Headers.client_version: __version__,
            Headers.encrypted: str(isinstance(config.password, str)),
        },
        data=data,
    )
    match r.status_code:
        case WriteCode.ok:
            pass
        case WriteCode.illegal_version:
            raise VersionError(f"Server requires version >= {r.text}")
        case WriteCode.missing_version:
            raise VersionError("Client failed to set headers correctly; please report this")
        case _:
            raise RuntimeError(f"Unexpected status code: {r.status_code}\nBody: {r.text}")


def _clear(config: ValidConfig) -> None:
    """
    Clear the remote pipe
    """
    logging.debug("Clearing channel %s", config.channel)
    r = _request("GET", f"{config.url}/clear/{quote(config.channel)}")
    if not r.ok:
        raise RuntimeError(f"Unexpected status code: {r.status_code}\nBody: {r.text}")


#
# Main
#


def _mode_check(m: Mode) -> None:
    if m.clear and m.peek:
        raise RuntimeError("--peek may not be used with --clear")
    if not m.read:
        if m.clear:
            raise RuntimeError("--clear may not be used when writing data to the pipe")
        if m.peek:
            raise RuntimeError("--peek may not be used when writing data to the pipe")


def _print_config() -> None:
    logging.debug("Mode: print-config")
    print(f"Config file: {CONFIG_FILE}")
    if not CONFIG_FILE.exists():
        print("No saved config")
    raw = CONFIG_FILE.read_text(encoding="utf-8")
    try:
        print(Config(**json.loads(raw)))
    except TypeError:
        print(f"Failed to load config: {raw}")


def _load_config(conf: Config, plaintext: bool) -> Config:
    logging.debug("Generating config...")
    password = None if plaintext else os.getenv(_PASSWORD_ENV)
    raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8")) if CONFIG_FILE.exists() else {}
    return Config(
        url=raw.get("url", None) if conf.url is None else conf.url,
        channel=raw.get("channel", None) if conf.channel is None else conf.channel,
        password=raw.get("password", None) if password is None and not plaintext else password,
    )


def _save_config(conf: Config, encrypt: bool) -> None:
    logging.debug("Mode: save-config")
    if encrypt and os.environ.get(_PASSWORD_ENV, None) is None:
        raise UsageError(f"--save-config --encrypt requires {_PASSWORD_ENV} be set")
    parent = CONFIG_FILE.parent
    if not parent.exists():
        logging.debug("Creating directory %s", parent)
        parent.mkdir(exist_ok=True)
    logging.debug("Saving config %s", conf)
    CONFIG_FILE.write_text(json.dumps(asdict(conf)), encoding="utf-8")
    logging.info("Config saved")


def _verify_config(conf: Config, encrypt: bool) -> None:
    logging.debug("Validating config...")
    if conf.url is None:
        raise UsageError("Missing: --url")
    if conf.channel is None:
        raise UsageError("Missing: --channel")
    if encrypt and conf.password is None:
        raise UsageError("Missing: --encrypt requires a password")


def rpipe(conf: Config, mode: Mode) -> None:
    """
    rpipe
    """
    logging.debug("Config file: %s", CONFIG_FILE)
    _mode_check(mode)
    if mode.print_config:
        _print_config()
        return
    # Load pipe config and save is requested
    conf = _load_config(conf, mode.plaintext)
    msg = "Loaded config with:\n  url = %s\n  channel = %s\n  has password: %s"
    logging.debug(msg, conf.url, conf.channel, conf.password is not None)
    if mode.save_config:
        _save_config(conf, mode.encrypt)
        return
    if not (mode.encrypt or mode.plaintext or mode.read or mode.clear):
        logging.info("Write mode: No password found, falling back to --plaintext")
    _verify_config(conf, mode.encrypt)
    # Invoke mode
    valid_conf = ValidConfig(**asdict(conf))
    if mode.clear:
        _clear(valid_conf)
    elif mode.read:
        _recv(valid_conf, mode.peek, mode.force)
    else:
        _send(valid_conf)


def main(prog: str, *args: str) -> None:
    """
    Parses arguments then invokes rpipe
    """
    name = Path(prog).name
    parser = argparse.ArgumentParser(prog=name)
    parser.add_argument("--version", action="version", version=f"{name} {__version__}")
    parser.add_argument("-p", "--peek", action="store_true", help="Read in 'peek' mode")
    parser.add_argument("--clear", action="store_true", help="Delete all entries in the channel")
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Attempt to read data even if this is a upload/download client version mismatch",
    )
    parser.add_argument("--verbose", action="store_true", help="Be verbose")
    # Config options
    parser.add_argument("-u", "--url", help="The pipe url to use")
    parser.add_argument("-c", "--channel", help="The channel to use")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--encrypt",
        action="store_true",
        help=f"Encrypt the data; uses {_PASSWORD_ENV} as the password if set, otherwise uses saved password",
    )
    group.add_argument("--plaintext", action="store_true", help="Do not encrypt the data")
    parser.add_argument(
        "--print-config", action="store_true", help="Print out the saved config information then exit"
    )
    parser.add_argument(
        "-s",
        "--save-config",
        action="store_true",
        help="Update the existing rpipe config then exit; allows incomplete configs to be saved",
    )
    ns = vars(parser.parse_args(args))
    if ns.pop("verbose"):
        logging.getLogger().setLevel(logging.DEBUG)
    keys = lambda x: (i.name for i in fields(x))
    conf_d = {i: k for i, k in ns.items() if i in keys(Config)}
    mode_d = {i: k for i, k in ns.items() if i in keys(Mode)}
    assert set(ns) == set(conf_d) | set(mode_d)
    conf_d["password"] = None
    return rpipe(Config(**conf_d), Mode(read=sys.stdin.isatty(), **mode_d))


def cli() -> None:
    main(*sys.argv)


if __name__ == "__main__":
    cli()
