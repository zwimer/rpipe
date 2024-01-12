from base64 import b64encode, b64decode
from typing import TYPE_CHECKING
from urllib.parse import quote
from pathlib import Path
import argparse
import logging
import hashlib
import zlib
import sys
import os

from Cryptodome.Random import get_random_bytes
from Cryptodome.Cipher import AES
from marshmallow_dataclass import dataclass
from requests import Request, Session

from ._shared import WriteCode, ReadCode, Headers
from ._version import __version__

if TYPE_CHECKING:
    from requests import Response


config_file = Path.home() / ".config" / "pipe.json"
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


@dataclass
class Config:
    """
    Information about where the remote pipe is
    """

    url: str
    channel: str
    password: str | None


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


def _recv(config: Config, peek: bool, force: bool) -> None:
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
            sys.stdout.buffer.write(_crypt(False, r.content, config.password))
            sys.stdout.flush()
        case ReadCode.wrong_version:
            raise VersionError(f"Version mismatch; uploader version = {r.text}; force a read with --force")
        case ReadCode.illegal_version:
            raise VersionError(f"Server requires version >= {r.text}")
        case ReadCode.no_data:
            raise NoData(f"The channel {config.channel} is empty.")
        case _:
            raise RuntimeError(f"Unknown status code: {r.status_code}\nBody: {r.text}")


def _send(config: Config) -> None:
    """
    Send data to the remote pipe
    """
    logging.debug("Writing to channel %s", config.channel)
    data = _crypt(True, sys.stdin.buffer.read(), config.password)
    r = _request(
        "POST",
        f"{config.url}/write/{quote(config.channel)}",
        headers={Headers.client_version: __version__},
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


def _clear(config: Config) -> None:
    """
    Clear the remote pipe
    """
    logging.debug("Clearing channel %s", config.channel)
    r = _request("GET", f"{config.url}/clear/{config.channel}")
    if not r.ok:
        raise RuntimeError(f"Unexpected status code: {r.status_code}\nBody: {r.text}")


#
# Main
#


def _error_check(has_stdin: bool, no_password: bool, password_env: bool, clear: bool, peek: bool) -> None:
    if no_password and password_env:
        raise RuntimeError("--no_password and --password-env are mutually exclusive")
    if clear and peek:
        raise RuntimeError("--peek may not be used with --clear")
    if has_stdin:
        if clear:
            raise RuntimeError("--clear may not be used when writing data to the pipe")
        if peek:
            raise RuntimeError("--peek may not be used when writing data to the pipe")


def _config_check(config: Config) -> None:
    if config.channel is not None and config.channel.lower() == "version":
        raise RuntimeError(f"{config.channel} is a reserved channel name")


# pylint: disable=too-many-arguments
def rpipe(
    print_config: bool,
    save_config: bool,
    url: str | None,
    channel: str | None,
    password_env: bool,
    no_password: bool,
    verbose: bool,
    peek: bool,
    force: bool,
    clear: bool,
) -> None:
    """
    rpipe
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    has_stdin: bool = not sys.stdin.isatty()
    _error_check(has_stdin, no_password, password_env, clear, peek)
    # Configure if requested
    password = None if not password_env else os.getenv(_PASSWORD_ENV)
    if save_config:
        logging.debug("Generating config...")
        if url is None or channel is None:
            raise UsageError("--url and --channel must be provided when using --save-config")
        if not password_env and not no_password:
            raise UsageError("Either --password-env or --no-password must be provided when using --save-config")
        if not config_file.parent.exists():
            config_file.parent.mkdir(exist_ok=True)
        out: str = Config.Schema().dumps(Config(url, channel, password))  # type: ignore
        logging.debug("Saving config to: %s", config_file)
        config_file.write_text(out)
        logging.info("Config saved")
        return
    # Load config, print if requested
    if print_config or url is None or channel is None:
        logging.debug("Loading saved config...")
        if not config_file.exists():
            raise UsageError("No config file found; please create one with --save-config.")
        try:
            conf: Config = Config.Schema().loads(config_file.read_text())  # type: ignore
        except Exception as e:
            raise ValueError(f"Invalid config; please fix or remove {config_file}") from e
        if print_config:
            print(f"Saved Config: {conf}")
            return
        url = conf.url if url is None else url
        channel = conf.channel if channel is None else channel
        password = None if no_password else (conf.password if password is None else password)
    # Exec
    logging.debug("Validating config...")
    conf = Config(url, channel, password)  # type: ignore
    _config_check(conf)
    if clear:
        _clear(conf)
    elif has_stdin:
        _send(conf)
    else:
        _recv(conf, peek, force)


def main(prog: str, *args: str) -> None:
    """
    Parses arguments then invokes rpipe
    """
    name = Path(prog).name
    parser = argparse.ArgumentParser(prog=name)
    parser.add_argument("--version", action="version", version=f"{name} {__version__}")
    parser.add_argument("-p", "--peek", action="store_true", help="Read in 'peek' mode")
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Attempt to read data even if this is a upload/download client version mismatch",
    )
    parser.add_argument("--clear", action="store_true", help="Delete all entries in the channel")
    parser.add_argument("--verbose", action="store_true", help="Be verbose")
    # Config options
    parser.add_argument("-u", "--url", help="The pipe url to use")
    parser.add_argument("-c", "--channel", help="The channel to use")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--password-env",
        action="store_true",
        help=f"Encrypt the data with the password stored in the environment variable: {_PASSWORD_ENV}",
    )
    group.add_argument("--no-password", action="store_true", help="Do not encrypt the data")
    parser.add_argument("--print_config", action="store_true", help="Print out the saved config information then exit")
    parser.add_argument(
        "-s",
        "--save-config",
        action="store_true",
        help=f"Configure {prog} to use the provided url and channel by default then exit",
    )
    rpipe(**vars(parser.parse_args(args)))


def cli() -> None:
    main(*sys.argv)


if __name__ == "__main__":
    cli()
