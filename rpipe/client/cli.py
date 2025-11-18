from multiprocessing import cpu_count
from pathlib import Path
import argparse

import argcomplete

from .. import __version__  # Extract version without importing shared


PASSWORD_ENV: str = "RPIPE_PASSWORD"
_DEFAULT_CF = Path.home() / ".config" / "rpipe.json"


def _cli(parser: argparse.ArgumentParser, parsed: argparse.Namespace) -> None:
    """
    We import main from CLI after parsing arguments because
    it is slow, and not necessary for --help or --version
    """
    # pylint: disable=import-outside-toplevel,cyclic-import
    from .main import main

    main(parser, parsed)


def _si(size: str) -> int:
    if size.isdecimal():
        return int(size)
    try:
        if (frv := float(size[:-1]) * (1000 ** (1 + "KMGT".index(size[-1].upper())))) == (rv := int(frv)):
            return rv
        raise ValueError("Non-integer number of bytes requested")
    except ValueError as e:
        raise ValueError(f"Invalid size: {size}") from e


# pylint: disable=too-many-locals,too-many-statements
def cli() -> None:
    """
    Parses arguments then invokes rpipe
    """
    threads: int = max(1, (cpu := cpu_count()) - 1)
    parser = argparse.ArgumentParser(add_help=False)
    parser.set_defaults(method=None)
    recv_g = parser.add_argument_group("Recv Mode")
    recv_g.add_argument(
        "-b", "--block", action="store_true", help="Wait until a channel is available to read"
    )
    recv_g.add_argument(
        "-p",
        "--peek",
        action="store_true",
        help="Read pipe without emptying it; will not construct a persistent pipe like a normal read",
    )
    recv_g.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Attempt to read data even if this is a upload/download client version mismatch",
    )
    recv_g.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Overwrite existing output path if it is not a non-empty directory (requires --file or --dir)",
    )
    send_g = parser.add_argument_group("Send Mode")
    send_g.add_argument(
        "-t",
        "--ttl",
        type=int,
        default=None,
        help="Pipe TTL in seconds; use server default if not passed",
    )
    send_g.add_argument(  # Do not use default= for better error checking w.r.t. plaintext mode
        "-Z",
        "--zstd",
        metavar="[1-22]",
        choices=range(1, 23),
        type=int,
        help="Compression level to use; invalid in plaintext mode",
    )
    send_g.add_argument(
        "-j",
        "--threads",
        metavar=f"[1-{cpu}]" if cpu > 1 else "1",
        choices=range(1, cpu + 1),
        default=threads,
        type=int,
        help=f"The number of threads to use for compression. Default: {threads}",
    )
    recv_send_g = parser.add_argument_group("Recv Mode / Send Mode")
    io_g = recv_send_g.add_mutually_exclusive_group()
    io_g.add_argument(
        "-F",
        "--file",
        default=None,
        const=True,
        nargs="?",
        type=Path,
        help="A file use for input/output instead of stdin/stdout. For sending, implies --progress <file size> unless otherwise specified. Requires -r or -s",
    )
    io_g.add_argument(
        "-D",
        "--dir",
        default=None,
        const=True,
        nargs="?",
        type=Path,
        help="A dir to tar/output as input/output instead of stdin/stdout. For sending, implies --progress <tarball size> unless otherwise specified. Requires -r or -s",
    )
    prog_g = recv_send_g.add_mutually_exclusive_group()
    prog_g.add_argument("-N", "--no-progress", action="store_true", help="Do not show a progress bar")
    prog_g.add_argument(
        "-P",
        "--progress",
        metavar="SIZE",
        type=_si,
        default=None,
        const=True,
        nargs="?",
        help="Show a progress bar, if a value is passed, assume that's the number of bytes to be passed. Only valid while sending or receiving data. Values can be suffixed with K, M, G, or T, to multiply by powers of 1000",
    )
    recv_send_g.add_argument(
        "-Y", "--total", action="store_true", help="Print the total number of bytes sent/received"
    )
    recv_send_g.add_argument(
        "-K", "--checksum", action="store_true", help="Checksum the data being sent/received"
    )
    # Config options
    config = parser.add_argument_group("Configuration")
    config.add_argument("-u", "--url", help="The pipe url to use")
    config.add_argument("-c", "--channel", help="The channel to use")
    config.add_argument("-T", "--timeout", type=float, help="The timeout for the HTTP requests")
    config.add_argument(
        "-k",
        "--key-file",
        type=Path,
        help="SSH ed25519 private key file used to signed admin requests",
    )
    config.add_argument("-C", "--config-file", type=Path, default=_DEFAULT_CF, help="The custom config file")
    config.add_argument(
        "-e",
        "--encrypt",
        action=argparse.BooleanOptionalAction,
        help=f"Encrypt the data; uses {PASSWORD_ENV} as the password if set, otherwise uses saved password",
    )
    config.add_argument("-S", "--ssl", action=argparse.BooleanOptionalAction, help="Require host use https")
    log_g = parser.add_argument_group("Logging")
    # pylint: disable=duplicate-code
    log_g.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase Log verbosity, pass more than once to increase verbosity",
    )
    log_g.add_argument("-n", "--no-color-log", action="store_true", help="Disable color in the log output")
    # Modes
    mode_g = parser.add_argument_group(
        "Mode Selection",
        description="Force usage of a specific mode (automatically chosen by default)",
    ).add_mutually_exclusive_group()
    mode_g.add_argument("-r", "--recv", action="store_true", help="Read data from server")
    mode_g.add_argument("-s", "--send", action="store_true", help="Send data to server")
    mode_g.add_argument("-d", "--delete", action="store_true", help="Delete all entries in the channel")
    mode_g.add_argument(
        "-q",
        "--query",
        action="store_true",
        help="Get information on the given channel",
    )
    mode_g.add_argument("-h", "--help", action="help", help="Show this help message and exit")
    mode_g.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"{parser.prog} {__version__}",
        help="Show program's version number and exit",
    )
    mode_g.add_argument(
        "-X", "--print-config", action="store_true", help="Print out the config (including CLI args)"
    )
    mode_g.add_argument(
        "-U",
        "--update-config",
        action="store_true",
        help="Update the existing rpipe config then exit; allows incomplete configs to be saved",
    )
    mode_g.add_argument(
        "-O", "--outdated", action="store_true", help="Check if this client is too old for the server"
    )
    mode_g.add_argument("-Q", "--server-version", action="store_true", help="Print the server version")
    mode_g.add_argument(
        "-B", "--blocked", action="store_true", help="Determine if the client is blocked from the server"
    )
    # Top priority mode
    mode_g.add_argument("-A", "--admin", action="store_true", help="Allow use of admin commands")
    # Admin commands
    admin = parser.add_subparsers(
        title="Admin Commands",
        description=(
            "Server admin commands; must be used with --admin and should have a key file set before use."
            " All arguments except logging and config arguments are ignored with admin commands."
            " Server must be configured to accept messages signed by your selected private key file"
        ),
        dest="method",
    )
    admin.add_parser("debug", help="Check if the server is running in debug mode")
    admin.add_parser("channels", help="List all channels with stats")
    admin.add_parser("stats", help="Print various server stats")
    log_p = admin.add_parser("log", help="Download server logs various server stats")
    log_p.add_argument(
        "-o", "--output-file", type=Path, default=None, help="Log output file, instead of stdout"
    )
    log_lvl_p = admin.add_parser("log-level", help="Get/set the server log level")
    log_lvl_p.add_argument("level", default=None, nargs="?", help="The log level for the server to use")
    admin.add_parser("lock", help="Lock the channel")
    admin.add_parser("unlock", help="Unlock the channel")
    for name in ("ip", "route"):
        p2 = admin.add_parser(name, help=f"Block / unblock {name}s, or get a list of blocked {name}s")
        m_g = p2.add_argument_group(
            f"Block / Unblock a given {name}",
            f"If none of these are passed, the command will return the list of banned {name}s",
        )
        m_g.add_argument("--block", nargs="+", help=f"Block a given {name}")
        m_g.add_argument("--unblock", nargs="+", help=f"Unblock a given {name}")
    argcomplete.autocomplete(parser)  # Tab completion
    _cli(parser, parser.parse_args())
