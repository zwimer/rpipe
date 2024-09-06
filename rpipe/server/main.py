from pathlib import Path
import argparse
import logging
import sys

from ..version import __version__
from .util import MIN_VERSION
from .app import serve


def main(prog, *args) -> None:
    name = Path(prog).name
    parser = argparse.ArgumentParser(prog=name)
    parser.add_argument("--version", action="version", version=f"{name} {__version__}")
    parser.add_argument(
        "--min-client-version",
        action="version",
        version=f"rpipe>={MIN_VERSION}",
        help="Print the minimum supported client version then exit",
    )
    parser.add_argument(
        "--key-files",
        type=Path,
        nargs="*",
        default=[],
        help="SSH ed25519 public keys to accept for admin access",
    )
    parser.add_argument("--state-file", type=Path, help="The save state file, if desired")
    parser.add_argument("port", type=int, help="The port waitress will listen on")
    parser.add_argument("--host", default="0.0.0.0", help="The host waitress will bind to for listening")
    parser.add_argument("--debug", action="store_true", help="Run the server in debug mode")
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    serve(**vars(parser.parse_args(args)))


def cli() -> None:
    main(*sys.argv)


if __name__ == "__main__":
    cli()
