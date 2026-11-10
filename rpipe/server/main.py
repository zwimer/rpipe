from dataclasses import fields
from pathlib import Path
import argparse

from ..shared import __version__
from .app import ServerConfig, LogConfig, serve
from .util import MIN_VERSION


def cli() -> None:
    parser = argparse.ArgumentParser()
    modes = parser.add_argument_group("Modes")
    modes.add_argument("-V", "--version", action="version", version=f"{parser.prog} {__version__}")
    modes.add_argument(
        "--min-client-version",
        action="version",
        version=f"rpipe>={MIN_VERSION}",
        help="Print the minimum supported client version then exit",
    )
    parser.add_argument(
        "listen",
        default=None,
        help="What waiterss will bind to; for debug mode (flask): <host>:<port> (IPv4 xor IPv6)",
    )
    parser.add_argument("-b", "--blocklist", type=Path, help="The blocklist configuration file")
    parser.add_argument("-s", "--state-file", type=Path, help="The save state file, if desired")
    parser.add_argument(
        "-T",
        "--trusted-proxies",
        nargs="+",
        default=[],
        help="IP addresses / networks to trust as trusted proxies",
    )
    parser.add_argument(
        "-k",
        "--key-files",
        type=Path,
        nargs="+",
        default=[],
        help="SSH ed25519 public keys to accept for admin access",
    )
    parser.add_argument("-F", "--favicon", type=Path, help="The favicon file, if desired")
    log_g = parser.add_argument_group("Logging")
    log_g.add_argument(
        "-l", "--log-file", type=Path, default=None, help="The log file to append to, if desired"
    )
    # pylint: disable=duplicate-code
    log_g.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase Log verbosity, pass more than once to increase verbosity",
    )
    # pylint: enable=duplicate-code
    log_g.add_argument("-C", "--colored", action="store_true", help="Enable color in the log output")
    parser.add_argument("--debug", action="store_true", help="Run the server in debug mode")
    ns = parser.parse_args()
    # Create listen
    listen: tuple[str, int] | str = ns.listen
    if ns.debug:
        try:
            if isinstance(listen, str):
                host, port_s = listen[1:].split("]:") if listen.startswith("[") else listen.rsplit(":", 1)
                if host:
                    listen = (host, int(port_s))
        except ValueError:
            pass
        if isinstance(listen, str):
            raise ValueError("In debug mode, listen must be <host>:<port>")
    # Pass remaining arguments
    field_names = lambda x: (i.name for i in fields(x))
    gen = lambda C, **kw: C(**{i: getattr(ns, i) for i in field_names(C) if i not in kw}, **kw)
    serve(gen(ServerConfig, listen=listen), gen(LogConfig), ns.favicon)
