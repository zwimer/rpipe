from dataclasses import fields
from pathlib import Path
import argparse
import sys

from ..shared import __version__
from .app import ServerConfig, LogConfig, serve
from .util import MIN_VERSION


def main(prog, *args) -> None:
    name = Path(prog).name
    parser = argparse.ArgumentParser(prog=name)
    modes = parser.add_argument_group("Modes")
    modes.add_argument("--version", action="version", version=f"{name} {__version__}")
    modes.add_argument(
        "--min-client-version",
        action="version",
        version=f"rpipe>={MIN_VERSION}",
        help="Print the minimum supported client version then exit",
    )
    parser.add_argument("port", type=int, help="The port waitress will listen on")
    parser.add_argument("--host", default="0.0.0.0", help="The host waitress will bind to for listening")
    parser.add_argument("--state-file", type=Path, help="The save state file, if desired")
    parser.add_argument(
        "--key-files",
        type=Path,
        nargs="*",
        default=[],
        help="SSH ed25519 public keys to accept for admin access",
    )
    log_group = parser.add_argument_group("Logging")
    log_group.add_argument(
        "--log-file", type=Path, default=None, help="The log file to append to, if desired"
    )
    # pylint: disable=duplicate-code
    log_group.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase Log verbosity, pass more than once to increase verbosity",
    )
    parser.add_argument("--debug", action="store_true", help="Run the server in debug mode")
    ns = parser.parse_args(args)
    gen = lambda C: C(**{i: getattr(ns, i) for i in (k.name for k in fields(C))})
    serve(gen(ServerConfig), gen(LogConfig))


def cli() -> None:
    main(*sys.argv)


if __name__ == "__main__":
    cli()
