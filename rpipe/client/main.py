"""
This file converts the output of the CLI to the input of the client
It also handles CLI error checking
This is a distinct file from the CLI because importing the client is slow
Splitting the CLI into two files does cause a cyclic import
"""

from logging import StreamHandler, getLevelName, getLogger
from inspect import Parameter, signature
from typing import TYPE_CHECKING
from dataclasses import replace
from os import getenv
import argparse
import sys

from zstdlib.log import CuteFormatter
from human_readable import listing

from ..shared import log
from .client import UsageError, Config, Mode, rpipe
from .cli import PASSWORD_ENV
from .admin import Admin

if TYPE_CHECKING:
    from argparse import Namespace


_LOG = "main"


def _check_mode_flags(mode: Mode) -> None:
    if (mode.recv, mode.send, mode.delete).count(True) != 1:
        raise UsageError("Can only recv, send, or delete at a time")
    # Flag specific checks
    if mode.ttl is not None and mode.ttl <= 0:
        raise UsageError("--ttl must be positive")
    if type(mode.progress) is int and mode.progress <= 0:  # pylint: disable=unidiomatic-typecheck
        raise UsageError("--progress argument must be positive if passed")
    if mode.yes and mode.file is None and mode.dir is None:
        raise UsageError("--yes requires --file or --dir")
    # Mode flags
    recv_bad = {"ttl"}
    send_bad = {"block", "peek", "force", "yes"}
    delete_bad = recv_bad | send_bad | {"progress", "encrypt", "file", "dir"}
    bad = lambda x: [f"--{i}" for i in x if bool(getattr(mode, i))]
    fmt = lambda x: f"argument{'' if len(x) == 1 else 's'} {listing(x, ',', 'and') }: may not be used "
    if mode.priority() and (args := bad(delete_bad)):
        raise UsageError(fmt(args) + "with priority modes")
    # Mode specific flags
    if mode.recv and (args := bad(recv_bad)):
        raise UsageError(fmt(args) + "when receiving data from the pipe")
    if mode.send and (args := bad(send_bad)):
        raise UsageError(fmt(args) + "when sending data to the pipe")
    if mode.delete and (args := bad(delete_bad)):
        raise UsageError(fmt(args) + "when deleting data from the pipe")


def _main(ns: Namespace, conf: Config):
    mode_d = {i: k for i, k in vars(ns).items() if i in Mode.keys()}
    if ns.no_progress:
        mode_d["progress"] = False  # Disable implicit progress
    # Load mode
    if (ns.file or ns.dir) and not ns.recv and not ns.send:
        raise UsageError("--file and --dir require either an explicit -r or -w")
    if (ns.recv, ns.send, ns.delete).count(True) == 0:
        mode_d["recv"] = ns.file is None and sys.stdin.isatty() and not ns.delete
        mode_d["send"] = not (mode_d["recv"] or ns.delete)
    mode = Mode(**mode_d)
    # Adjustments, error checks, then execute
    _check_mode_flags(mode)
    if ns.encrypt is None:
        mode = replace(mode, encrypt=bool(conf.password))
    if mode.encrypt and not conf.password:
        raise UsageError(f"--encrypt flag requires a password; set via {PASSWORD_ENV}")
    rpipe(conf, mode, ns.config_file)


def _admin(ns: Namespace, conf: Config) -> None:
    kw = signature(func := Admin(conf)[ns.method.replace("-", "_")]).parameters
    assert all(i.kind == Parameter.POSITIONAL_OR_KEYWORD for i in kw.values())
    func(**{i: getattr(ns, i) for i in kw})


def _config_log(parsed: Namespace) -> None:
    # Log config
    log.define_trace()
    root = getLogger()
    root.setLevel(lvl := log.level(parsed.verbose))
    assert len(root.handlers) == 0, "Root logger should not have any handlers"
    root.addHandler(sh := StreamHandler())
    sh.setFormatter(CuteFormatter(**log.CF_KWARGS, colored=not parsed.no_color_log))  # type: ignore[arg-type]
    getLogger(_LOG).info(
        "Logging level set to %s with colors %sABLED",
        getLevelName(lvl),
        "DIS" if parsed.no_color_log else "EN",
    )


# pylint: disable=too-many-locals,too-many-statements
def main(parser: argparse.ArgumentParser, parsed: Namespace) -> None:
    _config_log(parsed)
    # Load Config
    conf_d = {i: k for i, k in vars(parsed).items() if i in Config.keys()}
    if (pw := getenv(PASSWORD_ENV)) is not None:
        getLogger(_LOG).debug("Taking password from: %s", PASSWORD_ENV)
        conf_d["password"] = pw
    conf = Config.load(conf_d, parsed.config_file)  # We do not validate conf yet
    # Invoke the correct function
    if (parsed.method is not None) != parsed.admin:
        raise UsageError("Admin command must be passed with --admin")
    try:
        (_admin if parsed.admin else _main)(parsed, conf)
    except UsageError as e:
        parser.error(str(e))
