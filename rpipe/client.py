from __future__ import annotations
from base64 import b64encode, b64decode
from pathlib import Path
import argparse
import hashlib
import sys
import os

from Cryptodome.Cipher import AES
from Cryptodome.Random import get_random_bytes
from marshmallow_dataclass import dataclass
import requests


config_file = Path.home() / ".config" / "pipe.json"
_timeout: int = 60
_PASSWORD_ENV: str = "RPIPE_PASSWORD"


@dataclass
class Config:
    """
    Information about where the remote pipe is
    """

    url: str
    channel: str
    password: str | None


def _crypt(encrypt: bool, data: bytes, password: str | None) -> bytes:
    if password is None:
        return data
    options = {"password": password.encode(), "n": 2**14, "r": 8, "p": 1, "dklen": 32}
    mode = AES.MODE_GCM
    if encrypt:
        salt = get_random_bytes(AES.block_size)
        conf = AES.new(hashlib.scrypt(salt=salt, **options), mode)  # type: ignore
        text, tag = conf.encrypt_and_digest(data)
        return b".".join(b64encode(i) for i in (text, salt, conf.nonce, tag))
    text, salt, nonce, tag = (b64decode(i) for i in data.split(b"."))
    return AES.new(hashlib.scrypt(salt=salt, **options), mode, nonce=nonce).decrypt_and_verify(text, tag)  # type: ignore


#
# Actions
#


def _recv(config: Config, peek: bool) -> None:
    """
    Receive data from the remote pipe
    """
    r = requests.get(f"{config.url}/{'peek' if peek else 'read'}/{config.channel}", timeout=None)
    if not r.ok:
        raise RuntimeError(f"{r.status_code}: {r.text}")
    sys.stdout.buffer.write(_crypt(False, r.content, config.password))
    sys.stdout.flush()


def _send(config: Config) -> None:
    """
    Send data to the remote pipe
    """
    data = _crypt(True, sys.stdin.buffer.read(), config.password)
    r = requests.post(f"{config.url}/write/{config.channel}", data=data, timeout=_timeout)
    if not r.ok:
        raise RuntimeError(f"{r.status_code}: {r.text}")


def _clear(config: Config) -> None:
    """
    Clear the remote pipe
    """
    r = requests.get(f"{config.url}/clear/{config.channel}", timeout=_timeout)
    if not r.ok:
        raise RuntimeError(f"{r.status_code}: {r.text}")


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


def pipe(
    print_config: bool,
    save_config: bool,
    url: str | None,
    channel: str | None,
    password_env: bool,
    no_password: bool,
    peek: bool,
    clear: bool,
) -> None:
    """
    rpipe
    """
    has_stdin: bool = not os.isatty(sys.stdin.fileno())
    _error_check(has_stdin, no_password, password_env, clear, peek)
    # Configure if requested
    password = None if not password_env else os.getenv(_PASSWORD_ENV)
    if save_config:
        if url is None or channel is None:
            raise RuntimeError("--url and --channel must be provided when using --save_config")
        if not password_env and not no_password:
            print("Either --password-env or --no-password must be provided when using --save_config")
        if not config_file.parent.exists():
            config_file.parent.mkdir(exist_ok=True)
        out: str = Config.Schema().dumps(Config(url=url, channel=channel, password=password))  # type: ignore
        with config_file.open("w") as f:
            f.write(out)
    # Load config, print if requested
    if print_config or url is None or channel is None:
        if not config_file.exists():
            raise RuntimeError("No config file found; please create one with --save_config.")
        try:
            with config_file.open("r") as f:
                conf: Config = Config.Schema().loads(f.read())  # type: ignore
        except Exception as e:
            raise RuntimeError(f"Invalid config; please fix or remove {config_file}") from e
        if print_config:
            print(f"Saved Config: {conf}")
            return
        url = conf.url if url is None else url
        channel = conf.channel if channel is None else channel
        password = conf.password if password is None else password
    # Exec
    conf = Config(url=url, channel=channel, password=password)  # type: ignore
    if clear:
        _clear(conf)
    elif has_stdin:
        _send(conf)
    else:
        _recv(conf, peek)


def main(prog: str, *args: str) -> None:
    """
    Parses arguments then invokes rpipe
    """
    parser = argparse.ArgumentParser(prog=Path(prog).name)
    parser.add_argument("--print_config", action="store_true", help="Print out the saved config information then exit")
    parser.add_argument(
        "-s",
        "--save_config",
        action="store_true",
        help=f"Configure {prog} to use the provided url and channel by default",
    )
    parser.add_argument("-u", "--url", help="The pipe url to use")
    parser.add_argument("-c", "--channel", help="The channel to use")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--password-env",
        action="store_true",
        help=f"Encrypt the data with the password stored in the environment variable: {_PASSWORD_ENV}",
    )
    group.add_argument("--no-password", action="store_true", help="Do not encrypt the data")
    parser.add_argument("-p", "--peek", action="store_true", help="Read in 'peek' mode")
    parser.add_argument("--clear", action="store_true", help="Delete all entries in the channel")
    pipe(**vars(parser.parse_args(args)))


def cli() -> None:
    main(*sys.argv)


if __name__ == "__main__":
    cli()
