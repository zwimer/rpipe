from dataclasses import fields
from pathlib import Path
import argparse
import logging
import sys

from ..version import __version__
from .client import rpipe, Mode
from .config import PASSWORD_ENV, Config


def main(prog: str, *args: str) -> None:
    """
    Parses arguments then invokes rpipe
    """
    name = Path(prog).name
    parser = argparse.ArgumentParser(prog=name)
    parser.add_argument("--version", action="version", version=f"{name} {__version__}")
    g1 = parser.add_mutually_exclusive_group()
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
    parser.add_argument("-u", "--url", help="The pipe url to use")
    parser.add_argument("-c", "--channel", help="The channel to use")
    enc_mode = parser.add_mutually_exclusive_group()
    enc_mode.add_argument(
        "--encrypt",
        action="store_true",
        help=f"Encrypt the data; uses {PASSWORD_ENV} as the password if set, otherwise uses saved password",
    )
    enc_mode.add_argument("--plaintext", action="store_true", help="Do not encrypt the data")
    priority_mode = parser.add_mutually_exclusive_group()
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
    keys = lambda x: (i.name for i in fields(x))
    conf_d = {i: k for i, k in ns.items() if i in keys(Config)}
    mode_d = {i: k for i, k in ns.items() if i in keys(Mode)}
    assert set(ns) == set(conf_d) | set(mode_d)
    conf_d["password"] = None
    rpipe(Config(**conf_d), Mode(read=sys.stdin.isatty(), **mode_d))


def cli() -> None:
    main(*sys.argv)


if __name__ == "__main__":
    cli()
