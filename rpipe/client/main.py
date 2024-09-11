from __future__ import annotations
from typing import TYPE_CHECKING
from dataclasses import fields
from pathlib import Path
import argparse
import sys

from ..version import __version__
from ..shared import config_log
from .config import PASSWORD_ENV, PartialConfig, Option
from .client import rpipe, Mode
from .admin import Admin

if TYPE_CHECKING:
    from argparse import Namespace


def _admin(ns: Namespace):
    getattr(Admin(), ns.method)(url=ns.url, key_file=ns.key_file)


def _main(raw_ns: Namespace):
    ns = vars(raw_ns)
    opt = lambda a, b: Option(True if ns.pop(a) else (False if ns.pop(b) else None))
    mode_d = {i: k for i, k in ns.items() if i in {i.name for i in fields(Mode) if i.name != "encrypt"}}
    if mode_d["progress"] is None:
        mode_d["progress"] = False
    rpipe(
        PartialConfig(
            ssl=opt("ssl", "no_require_ssl"),
            url=Option(ns.pop("url")),
            channel=Option(ns.pop("channel")),
            password=Option(),
            key_file=Option(ns.pop("key_file")),
        ),
        Mode(read=sys.stdin.isatty(), encrypt=opt("encrypt", "plaintext"), **mode_d),
    )


def main(prog: str, *args: str) -> None:
    """
    Parses arguments then invokes rpipe
    """
    name = Path(prog).name
    parser = argparse.ArgumentParser(prog=name, add_help=False)
    parser.set_defaults(func=_main)
    g1 = parser.add_argument_group(
        "Read Mode Options", "Only available when reading"
    ).add_mutually_exclusive_group()
    g1.add_argument(
        "-p",
        "--peek",
        action="store_true",
        help="Read pipe without emptying it; will not construct a persistent pipe like a normal read.",
    )
    g1.add_argument("--clear", action="store_true", help="Delete all entries in the channel")
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Attempt to read data even if this is a upload/download client version mismatch",
    )
    parser.add_argument(
        "--ttl",
        type=int,
        default=None,
        help="Pipe TTL in seconds; use server default if not passed. Only available while writing.",
    )
    # pylint: disable=duplicate-code
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase Log verbosity, pass more than once to increase verbosity",
    )
    parser.add_argument(
        "--progress",
        type=int,
        const=True,
        nargs="?",
        help=(
            "Show a progress bar, if a value is passed, assume that's the number"
            " of bytes to be passed. Only valid while sending or receiving data."
        ),
    )
    # Config options
    config = parser.add_argument_group("Config Options", "Overrides saved config options")
    config.add_argument("-u", "--url", help="The pipe url to use")
    config.add_argument("-c", "--channel", help="The channel to use")
    config.add_argument(
        "--key-file",
        default=None,
        type=Path,
        help="SSH ed25519 private key file used to signed admin requests",
    )
    enc_g = config.add_mutually_exclusive_group()
    enc_g.add_argument(
        "--encrypt",
        action="store_true",
        help=f"Encrypt the data; uses {PASSWORD_ENV} as the password if set, otherwise uses saved password",
    )
    enc_g.add_argument("--plaintext", action="store_true", help="Do not encrypt the data")
    # Warnings
    ssl_g = config.add_mutually_exclusive_group()
    ssl_g.add_argument("--ssl", action="store_true", help="Require host use https")
    ssl_g.add_argument("--no-require-ssl", action="store_true", help="Do not require host use https")
    # Modes
    priority_mode = parser.add_argument_group(
        "Alternative modes",
        "If one of these is passed, the client will execute the desired action then exit.",
    ).add_mutually_exclusive_group()
    priority_mode.add_argument("-h", "--help", action="help", help="show this help message and exit")
    priority_mode.add_argument("--version", action="version", version=f"{name} {__version__}")
    priority_mode.add_argument(
        "--print-config", action="store_true", help="Print out the saved config information then exit"
    )
    priority_mode.add_argument(
        "-s",
        "--save-config",
        action="store_true",
        help="Update the existing rpipe config then exit; allows incomplete configs to be saved",
    )
    # Other modes
    priority_mode.add_argument(
        "--server-version", action="store_true", help="Print the server version then exit"
    )
    # Admin commands
    subparsers = parser.add_subparsers()
    admin_parser = subparsers.add_parser(
        "admin",
        help="Admins commands.",
        description=(
            "All arguments except --verbose, --url, and --key-file are ignored with admin commands."
            " Server must be configured to accept messages signed by your selected private key file"
        ),
    )
    admin_parser.set_defaults(func=_admin)
    admin = admin_parser.add_subparsers(required=True, title="Admin commands")
    server_debug = admin.add_parser("debug", help="Check if the server is running in debug mode")
    server_debug.set_defaults(method="debug")
    channels = admin.add_parser("channels", help="List all channels with stats")
    channels.set_defaults(method="channels")
    # Invoke func
    parsed = parser.parse_args(args)
    config_log(parsed.verbose)
    del parsed.verbose
    parsed.func(parsed)


def cli() -> None:
    main(*sys.argv)


if __name__ == "__main__":
    cli()
