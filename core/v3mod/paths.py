"""Locate Victoria 3 directories and the project config.

Detection is best-effort; every path can be overridden by environment
variables (V3MOD_GAME_DIR, V3MOD_USER_DIR) or by the project's v3mod.toml.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_NAME = "v3mod.toml"
STEAM_APP_ID = 529340


def user_data_dir() -> Path:
    """Documents/Paradox Interactive/Victoria 3 (or Linux equivalent)."""
    env = os.environ.get("V3MOD_USER_DIR")
    if env:
        return Path(env)
    system = platform.system()
    if system == "Linux":
        native = Path.home() / ".local/share/Paradox Interactive/Victoria 3"
        flatpak = Path.home() / ".var/app/com.valvesoftware.Steam/.local/share/Paradox Interactive/Victoria 3"
        if not native.exists() and flatpak.exists():
            return flatpak
        return native
    # Windows and macOS both use Documents
    return Path.home() / "Documents/Paradox Interactive/Victoria 3"


def mods_dir() -> Path:
    return user_data_dir() / "mod"


def logs_dir() -> Path:
    return user_data_dir() / "logs"


def docs_dir() -> Path:
    return user_data_dir() / "docs"


def _steam_library_candidates() -> list[Path]:
    system = platform.system()
    home = Path.home()
    if system == "Windows":
        roots = [
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam",
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Steam",
        ]
        # Extra drives commonly used for Steam libraries
        for letter in "DEFGH":
            roots.append(Path(f"{letter}:/SteamLibrary"))
            roots.append(Path(f"{letter}:/Steam"))
        return roots
    if system == "Darwin":
        return [home / "Library/Application Support/Steam"]
    return [
        home / ".steam/steam",
        home / ".local/share/Steam",
        home / ".var/app/com.valvesoftware.Steam/.local/share/Steam",  # flatpak
    ]


_VDF_PATH = re.compile(r'"path"\s+"([^"]+)"')


def _libraries_from_vdf() -> list[Path]:
    """Extra Steam libraries listed in steamapps/libraryfolders.vdf."""
    out: list[Path] = []
    for root in _steam_library_candidates():
        vdf = root / "steamapps/libraryfolders.vdf"
        if vdf.exists():
            try:
                for m in _VDF_PATH.finditer(vdf.read_text(encoding="utf-8", errors="replace")):
                    out.append(Path(m.group(1).replace("\\\\", "/")))
            except OSError:
                pass
    return out


def game_dir() -> Path | None:
    env = os.environ.get("V3MOD_GAME_DIR")
    if env:
        return Path(env)
    for root in _steam_library_candidates() + _libraries_from_vdf():
        candidate = root / "steamapps/common/Victoria 3"
        if (candidate / "game").is_dir():
            return candidate
    return None


def steam_linux_runtime(name: str = "auto") -> tuple[str, Path] | None:
    """Locate a Steam Linux Runtime container launcher (steamapps/common/SteamLinuxRuntime_*/run).

    name: 'sniper', 'soldier', or 'auto' (sniper first). Returns (name, run_path) or None.
    """
    order = ["sniper", "soldier"] if name == "auto" else [name]
    for root in _steam_library_candidates() + _libraries_from_vdf():
        for n in order:
            run = root / f"steamapps/common/SteamLinuxRuntime_{n}/run"
            if run.exists():
                return n, run
    return None


def os_release_id() -> str:
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if line.startswith("ID="):
                return line[3:].strip().strip('"')
    except OSError:
        pass
    return ""


IMMUTABLE_DISTROS = {"bazzite", "silverblue", "kinoite", "fedora-silverblue", "aurora", "bluefin", "steamos"}


def steam_binary() -> str | None:
    for name in ("steam", "steam-native"):
        found = shutil.which(name)
        if found:
            return found
    return None


def game_binary(gdir: Path | None) -> Path | None:
    if gdir is None:
        return None
    system = platform.system()
    if system == "Windows":
        exe = gdir / "binaries/victoria3.exe"
    elif system == "Darwin":
        exe = gdir / "binaries/victoria3"
    else:
        exe = gdir / "binaries/victoria3"
    return exe if exe.exists() else None


def launcher_settings(gdir: Path | None) -> dict:
    """Read <game>/launcher/launcher-settings.json (gameId, gameDataPath, exePath, dlcPath).

    gameDataPath uses placeholders: $LINUX_DATA_HOME (~/.local/share) on Linux,
    %USER_DOCUMENTS% on Windows. Returns {} if unavailable.
    """
    if gdir is None:
        return {}
    ls = gdir / "launcher/launcher-settings.json"
    try:
        import json
        data = json.loads(ls.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    dp = data.get("gameDataPath", "")
    dp = dp.replace("$LINUX_DATA_HOME", str(Path.home() / ".local/share"))
    dp = dp.replace("%USER_DOCUMENTS%", str(Path.home() / "Documents"))
    data["gameDataPath"] = str(Path(dp)) if dp else ""
    return data


def find_tiger(configured: str | None = None) -> str | None:
    if configured:
        p = Path(configured).expanduser()
        if p.exists():
            return str(p)
    for name in ("vic3-tiger", "vic3-tiger.exe"):
        found = shutil.which(name)
        if found:
            return found
    return None


@dataclass
class Project:
    root: Path
    mod_dir: Path
    name: str = ""
    prefix: str = ""
    mod_id: str = ""
    tiger: str | None = None
    game: str | None = None
    baseline_dir: Path = field(init=False)
    tiger_baseline: Path = field(init=False)
    overrides_file: Path = field(init=False)

    def __post_init__(self) -> None:
        fw = self.root / "framework"
        self.baseline_dir = fw / "baseline"
        self.tiger_baseline = fw / "tiger-baseline.json"
        self.overrides_file = fw / "overrides.txt"


def find_project(start: Path | None = None) -> Project | None:
    """Walk up from `start` until a v3mod.toml is found."""
    cur = (start or Path.cwd()).resolve()
    for candidate in (cur, *cur.parents):
        cfg = candidate / CONFIG_NAME
        if cfg.exists():
            return load_project(cfg)
    return None


def load_project(cfg_path: Path) -> Project:
    data = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
    mod = data.get("mod", {})
    tools = data.get("tools", {})
    root = cfg_path.parent
    mod_dir = root / mod.get("dir", "mod")
    return Project(
        root=root,
        mod_dir=mod_dir,
        name=mod.get("name", ""),
        prefix=mod.get("prefix", ""),
        mod_id=mod.get("id", ""),
        tiger=tools.get("tiger") or None,
        game=tools.get("game") or None,
    )


def mod_file_manifest(mod_dir: Path) -> set[str]:
    """Relative paths (forward slashes) of all files in the mod."""
    out: set[str] = set()
    for f in mod_dir.rglob("*"):
        if f.is_file() and ".metadata" not in f.parts:
            out.add(f.relative_to(mod_dir).as_posix())
    return out


def require_project() -> Project:
    proj = find_project()
    if proj is None:
        raise SystemExit(
            f"error: no {CONFIG_NAME} found in this directory or its parents. "
            "Run `v3mod new` to create a project, or cd into one."
        )
    return proj
