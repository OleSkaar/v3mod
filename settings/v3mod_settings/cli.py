"""Command-line entry point for the settings add-on."""

from __future__ import annotations

import argparse
import os
import sys

from . import __version__
from .settings import cmd_settings


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="v3mod-settings",
        description="Named profiles of the game's pdx_settings.json (e.g. potato vs play). "
                    "Not needed for headless `v3mod test` runs.",
    )
    p.add_argument("--version", action="version", version=f"v3mod-settings {__version__}")
    sub = p.add_subparsers(dest="settings_command", required=True)
    sub.add_parser("list", help="list saved profiles")
    ss = sub.add_parser("save", help="snapshot current settings as a profile")
    ss.add_argument("name")
    ss.add_argument("--sections", nargs="+", metavar="KEY",
                    help="only these top-level sections (e.g. Graphics)")
    su = sub.add_parser("use", help="apply a profile to the live settings file")
    su.add_argument("name")
    sh = sub.add_parser("show", help="print a profile")
    sh.add_argument("name")
    sd = sub.add_parser("diff", help="show what a profile would change")
    sd.add_argument("name")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(cmd_settings(args) or 0)
    except KeyboardInterrupt:
        print("\naborted")
        return 130
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0


if __name__ == "__main__":
    sys.exit(main())
