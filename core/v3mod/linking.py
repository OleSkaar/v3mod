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
            raise FileExistsError(f"{target} is already a link to {existing}")
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
    if platform.system() == "Windows":
        os.rmdir(target)  # removes junction without touching contents
    else:
        target.unlink()
    return target


def cmd_link(args) -> int:
    proj = paths.require_project()
    name = args.name or proj.root.name
    target = link_mod(proj.mod_dir, name)
    print(f"linked {target} -> {proj.mod_dir}")
    return 0


def cmd_unlink(args) -> int:
    proj = paths.require_project()
    name = args.name or proj.root.name
    target = unlink_mod(name)
    print(f"removed {target}")
    return 0
