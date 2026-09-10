"""`v3mod check-overrides`, `v3mod paths`, `v3mod doctor`."""

from __future__ import annotations

import platform
import shutil
import sys
from pathlib import Path

from . import paths
from .paths import mod_file_manifest

# Folders where a same-named file is *expected* to shadow vanilla (per-key
# mechanics live inside them), so shadowing is not by itself an override.
_KEYED_BY_FOLDER = ("localization/",)


def _read_overrides(path: Path) -> set[str]:
    if not path.exists():
        return set()
    out = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            out.add(s.replace("\\", "/"))
    return out


def cmd_check_overrides(args) -> int:
    if getattr(args, "all", False):
        mods = paths.require_workspace().mods()
        if not mods:
            raise SystemExit("error: the workspace has no mods yet; run `v3mod add`")
        worst = 0
        for proj in mods:
            print(f"\n=== {proj.root.name} ===")
            rc = _check_overrides_one(proj, args)
            worst = rc or worst
        return worst
    return _check_overrides_one(paths.require_project(args), args)


def _check_overrides_one(proj: paths.Project, args) -> int:
    game = Path(args.game or proj.game) if (args.game or proj.game) else paths.game_dir()
    if game is None:
        raise SystemExit("error: game directory not found; pass --game or set [tools].game")
    vanilla = game / "game"
    declared = _read_overrides(proj.overrides_file)

    shadowed, undeclared, stale = [], [], []
    for rel in sorted(mod_file_manifest(proj.mod_dir)):
        if rel == "vic3-tiger.conf" or rel.endswith(".gitkeep"):
            continue
        if (vanilla / rel).exists():
            shadowed.append(rel)
            if rel not in declared and not rel.startswith(_KEYED_BY_FOLDER):
                undeclared.append(rel)
    for rel in sorted(declared):
        if not (proj.mod_dir / rel).exists():
            stale.append(rel)

    print(f"{len(shadowed)} file(s) shadow a vanilla file; {len(declared)} declared in overrides.txt")
    for rel in undeclared:
        print(f"  UNDECLARED  {rel}")
    for rel in stale:
        print(f"  STALE       {rel} (listed but not in mod)")
    if undeclared:
        print("\nAdd each to framework/overrides.txt, or convert to INJECT:/REPLACE: in an own-named file.")
        return 1
    return 0


def _game_for(proj, ws=None) -> Path | None:
    if proj and proj.game:
        return Path(proj.game).expanduser()
    if ws and ws.game:
        return Path(ws.game).expanduser()
    return paths.game_dir()


def cmd_paths(args) -> int:
    ws = paths.find_workspace()
    proj = paths.resolve_project(args)
    game = _game_for(proj, ws)
    rows = [
        ("OS", platform.system()),
        ("user data", paths.user_data_dir()),
        ("mods", paths.mods_dir()),
        ("logs", paths.logs_dir()),
        ("docs", paths.docs_dir()),
        ("distro", paths.os_release_id() or "(unknown)"),
        ("steam", paths.steam_binary() or "(not found)"),
        ("steam runtime", (lambda r: f"{r[0]}: {r[1]}" if r else "(not found)")(paths.steam_linux_runtime("auto"))),
        ("game", game or "(not found — set V3MOD_GAME_DIR)"),
        ("binary", paths.game_binary(game) or "(not found)"),
        ("tiger", paths.find_tiger(proj.tiger if proj else (ws.tiger if ws else None)) or "(not found)"),
        ("workspace", ws.root if ws else "(none — run v3mod new)"),
        ("mods in workspace", (", ".join(d.name for d in ws.mod_dirs()) or "(none)") if ws else "(n/a)"),
        ("selected mod", proj.root if proj else "(none — use --mod, or cd into one)"),
    ]
    width = max(len(k) for k, _ in rows)
    for k, v in rows:
        print(f"{k:<{width}}  {v}")
    return 0


def cmd_doctor(args) -> int:
    ok = True

    def check(label: str, good: bool, hint: str = "") -> None:
        nonlocal ok
        mark = "ok " if good else "MISSING"
        print(f"[{mark}] {label}" + (f"  -> {hint}" if (not good and hint) else ""))
        ok = ok and good

    ws = paths.find_workspace()
    proj = paths.resolve_project(args)
    game = _game_for(proj, ws)
    check(f"python {sys.version.split()[0]} (>=3.11)", sys.version_info >= (3, 11))
    check("git on PATH", shutil.which("git") is not None, "install git")
    distro = paths.os_release_id()
    if distro in paths.IMMUTABLE_DISTROS:
        print(f"[info] immutable distro '{distro}': install CLI tools with brew/pipx/venv, system packages with rpm-ostree")
    check("steam on PATH", paths.steam_binary() is not None, "needed for `v3mod launch` (native Steam, not snap/flatpak)")
    slr = paths.steam_linux_runtime("auto")
    check("Steam Linux Runtime (for a direct launch)", slr is not None,
          "install SteamLinuxRuntime 3.0 (sniper) from Steam's Tools list, or use `v3mod launch --steam`")
    check("vic3-tiger", paths.find_tiger(proj.tiger if proj else (ws.tiger if ws else None)) is not None,
          "https://github.com/amtep/tiger/releases")
    check("Victoria 3 install", game is not None, "set V3MOD_GAME_DIR or [tools].game")
    check("victoria3 binary", paths.game_binary(game) is not None)
    check("user data dir", paths.user_data_dir().exists(), "run the game once")
    check("docs dir (script_docs output)", paths.docs_dir().exists(),
          "in-game console: script_docs, DumpDataTypes")
    check(f"workspace ({paths.WORKSPACE_NAME})", ws is not None, "run v3mod new <dir>")

    if ws is None:
        return 0 if ok else 1
    mods = ws.mods()
    check("at least one mod", bool(mods), "run v3mod add")
    for m in mods:
        marker = " *" if proj is not None and m.root == proj.root else "  "
        print(f"\n{marker}{m.root.name} — {m.label}")
        check("  mod/.metadata/metadata.json", (m.mod_dir / ".metadata/metadata.json").exists())
        link = paths.mods_dir() / m.root.name
        check(f"  linked into mods dir as '{m.root.name}'", link.exists(),
              f"v3mod link --mod {m.root.name}")
    return 0 if ok else 1
