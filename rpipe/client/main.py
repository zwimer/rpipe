from dataclasses import fields
from pathlib import Path
import argparse
import logging
import sys

from ..version import __version__
from .client import rpipe, Mode
from .config import PASSWORD_ENV, PartialConfig, Option


def main(prog: str, *args: str) -> None:
    """
    Parses arguments then invokes rpipe
    """
    name = Path(prog).name
    parser = argparse.ArgumentParser(prog=name, add_help=False)
    g1 = parser.add_argument_group(
        "Read Mode Options", "Only available when reading"
    ).add_mutually_exclusive_group()
    g1.add_argument("-p", "--peek", action="store_true", help="Read in 'peek' mode")
    g1.add_argument("--clear", action="store_true", help="Delete all entries in the channel")
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Attempt to read data even if this is a upload/download client version mismatch",
    )
    parser.add_argument("--verbose", action="store_true", help="Be verbose")
    # Config options
    config = parser.add_argument_group("Config Options", "Overrides saved config options")
    config.add_argument("-u", "--url", help="The pipe url to use")
    config.add_argument("-c", "--channel", help="The channel to use")
    enc_g = config.add_argument_group("Encryption Mode").add_mutually_exclusive_group()
    enc_g.add_argument(
        "--encrypt",
        action="store_true",
        help=f"Encrypt the data; uses {PASSWORD_ENV} as the password if set, otherwise uses saved password",
    )
    enc_g.add_argument("--plaintext", action="store_true", help="Do not encrypt the data")
    # Warnings
    ssl_g = config.add_argument_group("SSL Warning").add_mutually_exclusive_group()
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
    ns = vars(parser.parse_args(args))
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    if ns.pop("verbose"):
        logging.getLogger().setLevel(logging.DEBUG)
    opt = lambda a, b: Option(True if ns.pop(a) else (False if ns.pop(b) else None))
    mode_d = {i: k for i, k in ns.items() if i in {i.name for i in fields(Mode) if i.name != "encrypt"}}
    rpipe(
        PartialConfig(
            ssl=opt("ssl", "no_require_ssl"),
            url=Option(ns.pop("url")),
            channel=Option(ns.pop("channel")),
            password=Option(),
        ),
        Mode(read=sys.stdin.isatty(), encrypt=opt("encrypt", "plaintext"), **mode_d),
    )


def cli() -> None:
    main(*sys.argv)


if __name__ == "__main__":
    cli()
