"""Command-line entry point for the errors add-on."""

from __future__ import annotations

import argparse
import os
import sys

from . import __version__
from .errors import cmd_errors


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="v3mod-errors",
        description="Inspect the game's error.log: filter to this mod, diff against a vanilla baseline.",
    )
    p.add_argument("--version", action="version", version=f"v3mod-errors {__version__}")
    p.add_argument("--file", help="log file (default: <user data>/logs/error.log)")
    p.add_argument("--conflicts", action="store_true",
                   help="read logs/database_conflicts.log (which file won each override) instead")
    p.add_argument("--tail", type=int, metavar="N")
    p.add_argument("--grep", metavar="REGEX")
    p.add_argument("--mine", action="store_true", help="only lines referencing this mod's files")
    p.add_argument("--baseline", metavar="NAME", help="save normalised lines as a baseline")
    p.add_argument("--diff", metavar="NAME", help="show lines not in baseline NAME")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(cmd_errors(args) or 0)
    except KeyboardInterrupt:
        print("\naborted")
        return 130
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0


if __name__ == "__main__":
    sys.exit(main())
