"""`v3mod launch` and `v3mod playset` — Linux-first game launching.

launch:
  v3mod launch                      run <game>/binaries/victoria3 <flags> directly, inside the Steam Linux
                                    Runtime, with SteamAppId set (default). Skips the Paradox launcher and
                                    Steam's pre-launch shader processing. Steam client must be running.
  v3mod launch --steam              steam -applaunch 529340 <flags> instead (launcher + shader step unless
                                    the Steam launch option in the README is set)
  v3mod launch --tests              add -run_tests
  v3mod launch --wait               block until the process exits, then report where test results land

playset:
  v3mod playset show                print <user data>/dlc_load.json if present
  v3mod playset enable --entry S    append S to enabled_mods (backs the file up first)
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

from . import paths

DEFAULT_FLAGS = ["-debug_mode"]


def _flags(proj: paths.Project | None, args) -> list[str]:
    flags: list[str] = []
    if getattr(args, "_no_config_flags", False):
        pass
    elif proj is not None:
        import tomllib
        try:
            data = tomllib.loads((proj.root / paths.CONFIG_NAME).read_text(encoding="utf-8"))
            flags = list(data.get("run", {}).get("flags", DEFAULT_FLAGS))
        except (OSError, tomllib.TOMLDecodeError):
            flags = list(DEFAULT_FLAGS)
    else:
        flags = list(DEFAULT_FLAGS)
    if args.tests and "-run_tests" not in flags:
        flags.append("-run_tests")
    if args.no_save_after_failed_test and "-no_save_after_failed_test" not in flags:
        flags.append("-no_save_after_failed_test")
    for extra in args.flag or []:
        if extra not in flags:
            flags.append(extra)
    return flags


def start_process(args) -> subprocess.Popen | None:
    """Build the launch command from args, and start the game.

    Returns the Popen, or None on --dry-run. Sets args._direct / args._flags / args._game for callers.
    """
    proj = paths.resolve_project(args)
    game = Path(proj.game).expanduser() if (proj and proj.game) else paths.game_dir()
    flags = _flags(proj, args)

    binary = paths.game_binary(game)
    proton: tuple[str, Path] | None = None
    proton_vars: dict[str, str] | None = None
    if binary is None and paths.game_build(game) == "windows":
        # Windows build on Linux: run the .exe through Proton, as Steam itself would.
        proton = paths.proton_runner(getattr(args, "proton", None))
        proton_vars = paths.proton_env(game)
        binary = paths.windows_binary(game)
        if proton is None or proton_vars is None:
            missing = "no Proton build found" if proton is None else "no Proton prefix for this game"
            print(f"game is the Windows build but {missing}; falling back to steam -applaunch. "
                  "Run the game once through Steam to create the prefix.")
            binary = None

    direct = not args.steam
    if direct and binary is None:
        print("game binary not found; falling back to steam -applaunch "
              "(set V3MOD_GAME_DIR for direct launch)")
        direct = False

    if direct:
        cmd = [str(binary), *flags]
        cwd = binary.parent
        env = os.environ.copy()
        # What Steam would set for a game it launched itself; lets the Steam API attach to the
        # running client without a steam_appid.txt file.
        env.setdefault("SteamAppId", str(paths.STEAM_APP_ID))
        env.setdefault("SteamGameId", str(paths.STEAM_APP_ID))
        proton_note = ""
        if proton is not None and proton_vars is not None:
            pname, prun = proton
            env.update(proton_vars)
            cmd = [str(prun), "run", *cmd]
            proton_note = f", through Proton '{pname}'"
        runtime_note = ""
        if args.runtime != "none":
            slr = paths.steam_linux_runtime(args.runtime)
            if slr is None:
                if args.runtime != "auto":
                    raise SystemExit(f"error: SteamLinuxRuntime_{args.runtime} not found in any Steam library")
                runtime_note = ", no Steam Linux Runtime found (running on host libs)"
            else:
                name, run = slr
                cmd = [str(run), "--", *cmd]
                runtime_note = f", inside Steam Linux Runtime '{name}'"
        note = ("direct (no launcher, no Steam shader pre-processing; Steam client must be running)"
                + proton_note + runtime_note)
    else:
        steam = paths.steam_binary()
        if steam is None:
            raise SystemExit("error: steam not found on PATH; use a direct launch with V3MOD_GAME_DIR set")
        cmd = [steam, "-applaunch", str(paths.STEAM_APP_ID), *flags]
        cwd = None
        env = None
        note = "via steam -applaunch"

    print(f"launching {note}:\n  {' '.join(cmd)}")
    args._direct, args._flags, args._game, args._proj = direct, flags, game, proj
    args._proton = proton_vars if direct else None
    if args.dry_run:
        return None
    # New session so the whole tree (Steam runtime wrapper, pressure-vessel, the game) can be
    # stopped as one process group; killing only the wrapper would leave the game running.
    return subprocess.Popen(cmd, cwd=cwd, env=env, start_new_session=True)


def stop_wineserver(proton_vars: dict[str, str] | None) -> None:
    """Ask wineserver to shut the prefix down; killing the process group alone can leave it up."""
    if not proton_vars:
        return
    prefix = Path(proton_vars["STEAM_COMPAT_DATA_PATH"]) / "pfx"
    runner = paths.proton_runner()
    if runner is None or not prefix.is_dir():
        return
    wineserver = runner[1].parent / "files/bin/wineserver"
    if not wineserver.exists():
        return
    env = os.environ.copy()
    env["WINEPREFIX"] = str(prefix)
    try:
        subprocess.run([str(wineserver), "-k"], env=env, timeout=30,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        pass


def stop_process(proc: subprocess.Popen, grace: float = 30.0) -> None:
    """Terminate the launched process group, escalating to SIGKILL after `grace` seconds."""
    if proc.poll() is not None:
        return
    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:
        return
    for sig, wait in ((signal.SIGTERM, grace), (signal.SIGKILL, 5.0)):
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            return
        try:
            proc.wait(timeout=wait)
            break
        except subprocess.TimeoutExpired:
            continue
    # Reap any stragglers in the group that were not our direct child.
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def cmd_launch(args) -> int:
    started = time.time()
    proc = start_process(args)
    if proc is None:
        return 0
    direct, flags, game, proj = args._direct, args._flags, args._game, args._proj
    if not args.wait:
        print(f"pid {proc.pid} (not waiting; use --wait to block until exit)")
        return 0
    if not direct:
        print("note: `steam -applaunch` returns immediately; --wait only measures the launcher hand-off.")
    rc = proc.wait()
    elapsed = time.time() - started
    print(f"exited {rc} after {elapsed/60:.1f} min")
    if direct and rc != 0 and elapsed < 20:
        print("exited quickly with an error. If the game complained about Steam, make sure the Steam client is "
              "running; if it still refuses, create <game>/binaries/steam_appid.txt containing 529340, "
              "or use `v3mod launch --steam`. Try `--runtime soldier` if the runtime is the problem.")
    if "-run_tests" in flags:
        print("scripted test results: text file in", paths.user_data_dir(),
              "\n                       XML file in", (game / "binaries") if game else "<game>/binaries")
    print("error log:", paths.logs_dir() / "error.log")
    return rc


# --------------------------------------------------------------------------- #
# playset
# --------------------------------------------------------------------------- #

def _dlc_load_path() -> Path:
    return paths.user_data_dir() / "dlc_load.json"


def cmd_playset(args) -> int:
    path = _dlc_load_path()
    if args.playset_command == "show":
        if not path.exists():
            print(f"{path} not found. Open the launcher once and create a playset; "
                  "then re-run to see what it writes.")
            return 1
        print(path)
        print(path.read_text(encoding="utf-8"))
        return 0

    # enable
    if not path.exists():
        raise SystemExit(f"error: {path} not found; create a playset in the launcher first")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SystemExit(f"error: {path} is not valid JSON: {e}")
    mods = data.get("enabled_mods")
    if not isinstance(mods, list):
        raise SystemExit(f"error: no 'enabled_mods' list in {path}; format differs from what v3mod "
                         "expects — run `v3mod playset show` and report the structure")
    entry = args.entry
    if entry in mods:
        print(f"already enabled: {entry}")
        return 0
    backup = path.with_suffix(".json.bak")
    shutil.copy(path, backup)
    mods.append(entry)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"added {entry!r} to enabled_mods (backup at {backup.name}).")
    print("Verify the launcher shows the mod as enabled, then report whether a direct launch loads it.")
    return 0
