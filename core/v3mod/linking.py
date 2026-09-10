"""Link the repo's `mod/` folder into the game's local mod directory.

Windows: directory junction (no admin rights needed). Others: symlink.
"""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

from . import paths


def _is_link(p: Path) -> bool:
    if p.is_symlink():
        return True
    if platform.system() == "Windows" and p.exists():
        # Junctions are reparse points; os.lstat reports them without following.
        try:
            attrs = os.lstat(p).st_file_attributes  # type: ignore[attr-defined]
            return bool(attrs & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT
        except (AttributeError, OSError):
            return False
    return False


def _remove_link(target: Path) -> None:
    if platform.system() == "Windows":
        os.rmdir(target)  # removes a junction without touching its contents
    else:
        target.unlink()


def link_mod(mod_dir: Path, link_name: str) -> Path:
    mods = paths.mods_dir()
    mods.mkdir(parents=True, exist_ok=True)
    target = mods / link_name
    mod_dir = mod_dir.resolve()

    if target.exists() or target.is_symlink():
        if _is_link(target):
            existing = Path(os.path.realpath(target))
            if existing == mod_dir:
                return target
            if not target.exists():
                # Points at something that no longer exists: stale, and safe to replace.
                print(f"  replacing stale link {target.name} -> {existing}")
                _remove_link(target)
            else:
                raise FileExistsError(f"{target} is already a link to {existing}")
        else:
            raise FileExistsError(f"{target} exists and is a real directory")

    if platform.system() == "Windows":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(target), str(mod_dir)],
                       check=True, capture_output=True)
    else:
        os.symlink(mod_dir, target, target_is_directory=True)
    return target


def unlink_mod(link_name: str) -> Path:
    target = paths.mods_dir() / link_name
    if not (target.exists() or target.is_symlink()):
        raise FileNotFoundError(f"{target} does not exist")
    if not _is_link(target):
        raise IsADirectoryError(f"{target} is a real directory, refusing to delete")
    _remove_link(target)
    return target


def _selected(args) -> list[paths.Project]:
    if getattr(args, "all", False):
        if args.name:
            raise SystemExit("error: --name works on one mod; drop it when using --all")
        mods = paths.require_workspace().mods()
        if not mods:
            raise SystemExit("error: the workspace has no mods yet; run `v3mod add`")
        return mods
    return [paths.require_project(args)]


def cmd_link(args) -> int:
    failed = 0
    for proj in _selected(args):
        name = args.name or proj.root.name
        try:
            target = link_mod(proj.mod_dir, name)
        except (FileExistsError, OSError) as e:
            print(f"! {proj.root.name}: {e}")
            failed += 1
            continue
        print(f"linked {target} -> {proj.mod_dir}")
    return 1 if failed else 0


def cmd_unlink(args) -> int:
    if args.name and not getattr(args, "all", False):
        # A name alone is enough to clean up a link, even with no workspace or mod left.
        try:
            target = unlink_mod(args.name)
        except (FileNotFoundError, IsADirectoryError, OSError) as e:
            print(f"! {e}")
            return 1
        print(f"removed {target}")
        return 0

    failed = 0
    for proj in _selected(args):
        name = args.name or proj.root.name
        try:
            target = unlink_mod(name)
        except (FileNotFoundError, IsADirectoryError, OSError) as e:
            print(f"! {proj.root.name}: {e}")
            failed += 1
            continue
        print(f"removed {target}")
    return 1 if failed else 0
