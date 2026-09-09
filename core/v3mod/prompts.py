"""Tiny prompt helpers. No third-party deps.

Every prompt takes a `default` and a `preset`. If `preset` is not None the
prompt is skipped (used by --yes / command-line flags), otherwise the user is
asked and an empty answer returns the default.
"""

from __future__ import annotations

import sys


def _interactive() -> bool:
    return sys.stdin.isatty()


def ask(label: str, default: str = "", preset: str | None = None,
        validate=None, non_interactive: bool = False) -> str:
    if preset is not None:
        value = preset
    elif non_interactive or not _interactive():
        value = default
    else:
        while True:
            suffix = f" [{default}]" if default else ""
            raw = input(f"{label}{suffix}: ").strip()
            value = raw or default
            if validate is None:
                break
            problem = validate(value)
            if not problem:
                break
            print(f"  ! {problem}")
        return value
    if validate is not None:
        problem = validate(value)
        if problem:
            raise SystemExit(f"error: {label}: {problem}")
    return value


def ask_bool(label: str, default: bool = True, preset: bool | None = None,
             non_interactive: bool = False) -> bool:
    if preset is not None:
        return preset
    if non_interactive or not _interactive():
        return default
    hint = "Y/n" if default else "y/N"
    while True:
        raw = input(f"{label} [{hint}]: ").strip().lower()
        if not raw:
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print("  ! please answer y or n")


def ask_list(label: str, default: list[str] | None = None,
             preset: list[str] | None = None, max_items: int | None = None,
             non_interactive: bool = False) -> list[str]:
    default = default or []
    if preset is not None:
        items = preset
    elif non_interactive or not _interactive():
        items = default
    else:
        shown = ", ".join(default)
        raw = input(f"{label} (comma-separated){f' [{shown}]' if shown else ''}: ").strip()
        items = [s.strip() for s in raw.split(",") if s.strip()] if raw else default
    if max_items is not None and len(items) > max_items:
        raise SystemExit(f"error: {label}: at most {max_items} items allowed")
    return items
