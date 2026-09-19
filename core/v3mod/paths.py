"""Locate Victoria 3 directories, the workspace, and the per-mod project config.

Detection is best-effort; every path can be overridden by environment
variables (V3MOD_GAME_DIR, V3MOD_USER_DIR) or by config.

Two config files:
  v3mod-workspace.toml   marks the monorepo root; shared defaults and tool paths
  v3mod.toml             marks one mod, at <workspace>/mods/<dir>/v3mod.toml
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import tomllib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

CONFIG_NAME = "v3mod.toml"
WORKSPACE_NAME = "v3mod-workspace.toml"
DEFAULT_MODS_DIR = "mods"
STEAM_APP_ID = 529340


PDX_SUBDIR = "Paradox Interactive/Victoria 3"


def xdg_data_home() -> Path:
    """$XDG_DATA_HOME, or its spec default. Never assume ~/.local/share directly."""
    env = os.environ.get("XDG_DATA_HOME")
    if env:
        return Path(env)
    return Path.home() / ".local/share"


def documents_dir() -> Path:
    """The Windows/macOS Documents folder. On Windows this can be redirected (OneDrive)."""
    for var in ("OneDrive", "USERPROFILE"):
        base = os.environ.get(var)
        if base and (Path(base) / "Documents").is_dir():
            return Path(base) / "Documents"
    return Path.home() / "Documents"


@lru_cache(maxsize=1)
def _config_tools() -> dict:
    """The nearest workspace's [tools] table, so paths can be pinned in config, not just env.

    Cached: within one CLI run the working directory does not move.
    """
    try:
        cur = Path.cwd().resolve()
    except OSError:
        return {}
    for candidate in (cur, *cur.parents):
        for name in (CONFIG_NAME, WORKSPACE_NAME):
            cfg = candidate / name
            if cfg.exists():
                try:
                    tools = tomllib.loads(cfg.read_text(encoding="utf-8")).get("tools", {})
                except (OSError, tomllib.TOMLDecodeError):
                    tools = {}
                if tools:
                    return tools
    return {}


def _autodetect_user_data_dir() -> tuple[Path, str]:
    """Where the game keeps saves, logs, mods and settings, and how we worked that out."""
    # The game's own launcher-settings.json is authoritative when we can find the install.
    gdir, _ = resolve_game_dir()
    if gdir is not None:
        dp = launcher_settings(gdir).get("gameDataPath") or ""
        if dp and Path(dp).is_dir():
            return Path(dp), "launcher-settings.json"

    if platform.system() == "Linux":
        native = xdg_data_home() / PDX_SUBDIR
        flatpak = Path.home() / ".var/app/com.valvesoftware.Steam/.local/share" / PDX_SUBDIR
        if not native.exists() and flatpak.exists():
            return flatpak, "autodetected (flatpak Steam)"
        return native, "autodetected"
    return documents_dir() / PDX_SUBDIR, "autodetected"


def resolve_user_data_dir() -> tuple[Path, str]:
    env = os.environ.get("V3MOD_USER_DIR")
    if env:
        return Path(env).expanduser(), "V3MOD_USER_DIR"
    cfg = _config_tools().get("user_dir")
    if cfg:
        return Path(cfg).expanduser(), f"[tools].user_dir"
    return _autodetect_user_data_dir()


def user_data_dir() -> Path:
    """<XDG_DATA_HOME>/Paradox Interactive/Victoria 3, or the platform equivalent."""
    return resolve_user_data_dir()[0]


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


@lru_cache(maxsize=1)
def resolve_game_dir() -> tuple[Path | None, str]:
    env = os.environ.get("V3MOD_GAME_DIR")
    if env:
        return Path(env).expanduser(), "V3MOD_GAME_DIR"
    cfg = _config_tools().get("game")
    if cfg:
        return Path(cfg).expanduser(), "[tools].game"
    for root in _steam_library_candidates() + _libraries_from_vdf():
        candidate = root / "steamapps/common/Victoria 3"
        if (candidate / "game").is_dir():
            return candidate, "autodetected (Steam library)"
    return None, "not found — set [tools].game or V3MOD_GAME_DIR"


def game_dir() -> Path | None:
    return resolve_game_dir()[0]


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


def proton_prefix() -> Path | None:
    """<library>/steamapps/compatdata/<appid>/pfx — present when the game runs under Proton."""
    for root in _steam_library_candidates() + _libraries_from_vdf():
        pfx = root / f"steamapps/compatdata/{STEAM_APP_ID}/pfx"
        if (pfx / "drive_c").is_dir():
            return pfx
    return None


def proton_documents() -> Path | None:
    """The Documents folder *inside* the Proton prefix, which is what %USER_DOCUMENTS% means there."""
    pfx = proton_prefix()
    if pfx is None:
        return None
    users = pfx / "drive_c/users"
    for name in ("steamuser", os.environ.get("USER") or "", os.environ.get("USERNAME") or ""):
        if name and (users / name / "Documents").is_dir():
            return users / name / "Documents"
    return None


def steam_root() -> Path | None:
    """The Steam client install root (STEAM_COMPAT_CLIENT_INSTALL_PATH)."""
    for root in _steam_library_candidates():
        if (root / "steamapps").is_dir():
            return root
    return None


def _proton_dirs() -> list[Path]:
    out: list[Path] = []
    for root in _steam_library_candidates() + _libraries_from_vdf():
        out.append(root / "compatibilitytools.d")
        out.append(root / "steamapps/common")
    return out


def proton_runner(preferred: str | None = None) -> tuple[str, Path] | None:
    """Locate a Proton runner script. Returns (name, path to `proton`) or None.

    `preferred` names a specific build; by default we use the one Steam already bound to this
    game, recorded in compatdata/<appid>/version, so v3mod runs what Steam would run.
    """
    names: list[str] = []
    if preferred:
        names.append(preferred)
    else:
        pfx = proton_prefix()
        if pfx is not None:
            try:
                recorded = (pfx.parent / "version").read_text(encoding="utf-8").strip()
            except OSError:
                recorded = ""
            if recorded:
                names.append(recorded)
    for name in names:
        for base in _proton_dirs():
            run = base / name / "proton"
            if run.is_file():
                return name, run
    # Whatever Proton is installed, newest-looking last-resort.
    found: list[tuple[str, Path]] = []
    for base in _proton_dirs():
        if not base.is_dir():
            continue
        for d in base.iterdir():
            if (d / "proton").is_file():
                found.append((d.name, d / "proton"))
    if found:
        found.sort(key=lambda t: t[0])
        return found[-1]
    return None


def proton_env(gdir: Path | None) -> dict[str, str] | None:
    """The two variables Proton requires, or None if we cannot fill them in."""
    pfx = proton_prefix()
    root = steam_root()
    if pfx is None or root is None:
        return None
    return {
        "STEAM_COMPAT_DATA_PATH": str(pfx.parent),
        "STEAM_COMPAT_CLIENT_INSTALL_PATH": str(root),
    }


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
    """The executable this platform can run directly. A .exe on Linux is *not* directly runnable."""
    if gdir is None:
        return None
    name = "victoria3.exe" if platform.system() == "Windows" else "victoria3"
    exe = gdir / "binaries" / name
    return exe if exe.exists() else None


def windows_binary(gdir: Path | None) -> Path | None:
    """binaries/victoria3.exe, whatever platform we are on."""
    if gdir is None:
        return None
    exe = gdir / "binaries/victoria3.exe"
    return exe if exe.exists() else None


def game_build(gdir: Path | None) -> str:
    """'native', 'windows' (needs Proton/Wine on Linux), or 'none'."""
    if game_binary(gdir) is not None:
        return "native"
    if windows_binary(gdir) is not None:
        return "windows"
    return "none"


PROTON_NOTE = (
    "this is the Windows build; on Linux v3mod runs it through Proton "
    "(`proton run`, with the Proton build Steam already bound to this game)."
)


def launcher_settings(gdir: Path | None) -> dict:
    """Read <game>/launcher/launcher-settings.json (gameId, gameDataPath, exePath, dlcPath).

    gameDataPath uses placeholders: $LINUX_DATA_HOME on Linux, %USER_DOCUMENTS% on Windows.
    Both are expanded from the environment, not assumed. Returns {} if unavailable.
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
    dp = dp.replace("$LINUX_DATA_HOME", str(xdg_data_home()))
    if "%USER_DOCUMENTS%" in dp:
        # A Windows build under Proton writes into the prefix, not the Linux home.
        docs = proton_documents() if platform.system() == "Linux" else None
        dp = dp.replace("%USER_DOCUMENTS%", str(docs or documents_dir()))
    data["gameDataPath"] = str(Path(dp)) if dp else ""
    return data


def resolve_tiger(configured: str | None = None) -> tuple[str | None, str]:
    env = os.environ.get("V3MOD_TIGER")
    if env:
        p = Path(env).expanduser()
        if p.exists():
            return str(p), "V3MOD_TIGER"
    configured = configured or _config_tools().get("tiger")
    if configured:
        p = Path(configured).expanduser()
        if p.exists():
            return str(p), "[tools].tiger"
    for name in ("vic3-tiger", "vic3-tiger.exe"):
        found = shutil.which(name)
        if found:
            return found, "autodetected (PATH)"
    return None, "not found — set [tools].tiger or V3MOD_TIGER"


def find_tiger(configured: str | None = None) -> str | None:
    return resolve_tiger(configured)[0]


@dataclass
class Workspace:
    """The monorepo root: shared config plus a mods/ directory of mod projects."""

    root: Path
    name: str = ""
    mods_dirname: str = DEFAULT_MODS_DIR
    defaults: dict = field(default_factory=dict)
    tiger: str | None = None
    game: str | None = None

    @property
    def mods_dir(self) -> Path:
        return self.root / self.mods_dirname

    @property
    def config_file(self) -> Path:
        return self.root / WORKSPACE_NAME

    def mod_dirs(self) -> list[Path]:
        """Directories under mods/ that hold a v3mod.toml, sorted by name."""
        if not self.mods_dir.is_dir():
            return []
        return sorted((d for d in self.mods_dir.iterdir()
                       if d.is_dir() and (d / CONFIG_NAME).exists()),
                      key=lambda d: d.name.lower())

    def mods(self) -> list["Project"]:
        return [load_project(d / CONFIG_NAME, workspace=self) for d in self.mod_dirs()]

    def mod(self, selector: str) -> "Project | None":
        """Find one mod by directory name (exact, then case-insensitive) or by [mod].name."""
        direct = self.mods_dir / selector
        if (direct / CONFIG_NAME).exists():
            return load_project(direct / CONFIG_NAME, workspace=self)
        low = selector.lower()
        loaded = self.mods()
        for proj in loaded:
            if proj.root.name.lower() == low:
                return proj
        for proj in loaded:
            if proj.name.lower() == low:
                return proj
        return None


def find_workspace(start: Path | None = None) -> Workspace | None:
    """Walk up from `start` until a v3mod-workspace.toml is found."""
    cur = (start or Path.cwd()).resolve()
    for candidate in (cur, *cur.parents):
        cfg = candidate / WORKSPACE_NAME
        if cfg.exists():
            return load_workspace(cfg)
    return None


def load_workspace(cfg_path: Path) -> Workspace:
    data = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
    ws = data.get("workspace", {})
    tools = data.get("tools", {})
    root = cfg_path.parent
    return Workspace(
        root=root,
        name=ws.get("name", root.name),
        mods_dirname=ws.get("mods_dir", DEFAULT_MODS_DIR),
        defaults=data.get("defaults", {}),
        tiger=tools.get("tiger") or None,
        game=tools.get("game") or None,
    )


def require_workspace(start: Path | None = None) -> Workspace:
    ws = find_workspace(start)
    if ws is None:
        raise SystemExit(
            f"error: no {WORKSPACE_NAME} in this directory or its parents. "
            "cd to the directory you keep mods in and run `v3mod new` once, then `v3mod add` "
            "for each mod."
        )
    return ws


@dataclass
class Project:
    """One mod inside a workspace: <workspace>/mods/<dir>/."""

    root: Path
    mod_dir: Path
    name: str = ""
    prefix: str = ""
    mod_id: str = ""
    tiger: str | None = None
    game: str | None = None
    workspace: Workspace | None = None
    baseline_dir: Path = field(init=False)  # v3mod-errors' error-log baselines; created on demand
    tiger_baseline: Path = field(init=False)
    overrides_file: Path = field(init=False)

    def __post_init__(self) -> None:
        fw = self.root / "framework"
        self.baseline_dir = fw / "baseline"
        self.tiger_baseline = fw / "tiger-baseline.json"
        self.overrides_file = fw / "overrides.txt"

    @property
    def label(self) -> str:
        return self.name or self.root.name


def find_project(start: Path | None = None) -> Project | None:
    """Walk up from `start` until a v3mod.toml is found."""
    cur = (start or Path.cwd()).resolve()
    for candidate in (cur, *cur.parents):
        cfg = candidate / CONFIG_NAME
        if cfg.exists():
            return load_project(cfg)
    return None


def load_project(cfg_path: Path, workspace: Workspace | None = None) -> Project:
    data = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
    mod = data.get("mod", {})
    tools = data.get("tools", {})
    root = cfg_path.parent
    ws = workspace if workspace is not None else find_workspace(root)
    mod_dir = root / mod.get("dir", "mod")
    return Project(
        root=root,
        mod_dir=mod_dir,
        name=mod.get("name", ""),
        prefix=mod.get("prefix", ""),
        mod_id=mod.get("id", ""),
        # A mod may override the workspace's tool paths; usually it doesn't.
        tiger=tools.get("tiger") or (ws.tiger if ws else None),
        game=tools.get("game") or (ws.game if ws else None),
    )


def mod_file_manifest(mod_dir: Path) -> set[str]:
    """Relative paths (forward slashes) of all files in the mod."""
    out: set[str] = set()
    for f in mod_dir.rglob("*"):
        if f.is_file() and ".metadata" not in f.parts:
            out.add(f.relative_to(mod_dir).as_posix())
    return out


def _ambiguous(ws: Workspace, mods: list[Project]) -> SystemExit:
    listing = "\n".join(f"  {m.root.name:<24} {m.label}" for m in mods)
    return SystemExit(
        f"error: {len(mods)} mods in the workspace at {ws.root}; say which one with "
        f"`--mod NAME`, or cd into its directory:\n{listing}"
    )


def resolve_project(args=None, required: bool = False) -> Project | None:
    """Find the mod a command should act on.

    Order: an explicit --mod, then a v3mod.toml at or above the working directory,
    then the workspace's only mod. With several mods and no selection, `required`
    decides between an error and None.
    """
    selector = getattr(args, "mod", None)
    if selector:
        ws = require_workspace()
        proj = ws.mod(selector)
        if proj is None:
            known = ", ".join(d.name for d in ws.mod_dirs()) or "(none)"
            raise SystemExit(f"error: no mod {selector!r} in {ws.mods_dir} (have: {known})")
        return proj

    proj = find_project()
    if proj is not None:
        return proj

    ws = find_workspace()
    if ws is not None:
        mods = ws.mods()
        if len(mods) == 1:
            return mods[0]
        if not mods:
            if required:
                raise SystemExit(
                    f"error: the workspace at {ws.root} has no mods yet. Run `v3mod add` to create one."
                )
            return None
        if required:
            raise _ambiguous(ws, mods)
        return None

    if required:
        raise SystemExit(
            f"error: no {CONFIG_NAME} or {WORKSPACE_NAME} in this directory or its parents. "
            "cd to the directory you keep mods in and run `v3mod new`, or cd into an existing "
            "workspace."
        )
    return None


def require_project(args=None) -> Project:
    proj = resolve_project(args, required=True)
    assert proj is not None  # required=True either returns a project or raises
    return proj
