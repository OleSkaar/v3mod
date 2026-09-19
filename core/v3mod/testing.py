"""`v3mod flags` and `v3mod test`.

flags: search the game binary for engine launch flags known from Jomini titles, so we know
       which of them this build of Victoria 3 accepts before relying on them.

test:  one-command scripted-test run:
         victoria3 -nographics -handsoff -scripted_tests [-continuelastsave] [-random_seed=N]
       then watch for the results file the engine writes in the user-data dir, print it, and stop
       the game. With --seeds it runs one game per seed in sequence (never two at once), each into
       its own output folder; --load picks which workspace mods the game loads for the run,
       --only/--skip pick the suites, --tail keeps matching debug.log lines live (the engine
       truncates that file in place mid-run), and `v3mod report` tabulates the results.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import paths, launch as launch_mod

KNOWN_FLAGS = [
    "-debug_mode", "-run_tests", "-scripted_tests", "-no_save_after_failed_test",
    "-save_before_failed_test", "-nographics", "-handsoff", "-continuelastsave",
    "-random_seed", "-benchmark", "-develop", "-map_editor", "-nolauncher",
    "-checksum", "-dumpdata", "-crash_data_log_directory",
]


def probe_flags(binary: Path) -> dict[str, bool]:
    data = binary.read_bytes()
    found: dict[str, bool] = {}
    for flag in KNOWN_FLAGS:
        name = flag.lstrip("-").encode()
        # Engine flag tables store the bare name; require a word boundary on both sides.
        found[flag] = re.search(rb"(?<![A-Za-z0-9_])" + re.escape(name) + rb"(?![A-Za-z0-9_])", data) is not None
    return found


def cmd_flags(args) -> int:
    proj = paths.resolve_project(args)
    game = Path(proj.game).expanduser() if (proj and proj.game) else paths.game_dir()
    binary = paths.game_binary(game)
    if binary is None:
        raise SystemExit("error: game binary not found; set V3MOD_GAME_DIR or [tools].game")
    print(f"probing {binary} ({binary.stat().st_size // 1_000_000} MB) for known engine flags")
    found = probe_flags(binary)
    for flag, ok in found.items():
        print(f"  {'found  ' if ok else 'absent '} {flag}")
    print("\n'found' means the name occurs in the binary, which is strong but not conclusive evidence "
          "that the flag is honoured; 'absent' is close to conclusive that it is not.")
    return 0


# --------------------------------------------------------------------------- #
# test
# --------------------------------------------------------------------------- #
#
# Mechanics (from kaiser-chris/pdx-test-runner, which has a real Vic3 run on record):
#   launch:   victoria3 -nographics -handsoff -scripted_tests
#   results:  <user data>/tests.txt, lines "[ OK ] name ( date )" / "[ FAIL ] name ( date )",
#             written only once every test has resolved; the game keeps running afterwards.
#   failures: <user data>/save games/TEST_FAIL_*.v3
#   vanilla:  <game>/game/tools/scripted_tests/*.txt run too unless hidden.

RESULT_FILE = "tests.txt"
RESULT_LINE = re.compile(r"^\[\s*(OK|FAIL)\s*\]\s+(\S+)\s+\(\s*(.*?)\s*\)")
IGNORED_SUFFIX = ".v3mod-ignored"
FAIL_SAVE_PREFIX = "TEST_FAIL_"


def _hide_vanilla_tests(game: Path, keep: set[str]) -> list[tuple[Path, Path]]:
    """Rename vanilla scripted-test files so the engine skips them. Returns (orig, renamed) pairs."""
    d = game / "game/tools/scripted_tests"
    renamed: list[tuple[Path, Path]] = []
    if not d.is_dir():
        return renamed
    for f in sorted(d.glob("*.txt")):
        if f.name in keep:
            continue
        target = f.with_name(f.name + IGNORED_SUFFIX)
        f.rename(target)
        renamed.append((f, target))
    return renamed


def _restore(renamed: list[tuple[Path, Path]]) -> None:
    for orig, target in renamed:
        if target.exists() and not orig.exists():
            target.rename(orig)


def _parse_results(text: str) -> list[tuple[str, str, str]]:
    out = []
    for line in text.splitlines():
        m = RESULT_LINE.match(line.strip())
        if m:
            out.append((m.group(1), m.group(2), m.group(3)))
    return out


def parse_seeds(spec: str) -> list[int]:
    """'13,14,16' or '13-16' or a mix -> [13, 14, 15, 16]."""
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def _display_connected() -> bool | None:
    """True/False from the DRM connectors, None when unknown (no /sys, not Linux).

    The game needs a connected display even for -nographics runs (Proton: 'Xalia: No displays
    available' at startup when the monitor is off or unplugged)."""
    root = Path("/sys/class/drm")
    if not root.is_dir():
        return None
    states = []
    for f in root.glob("card*-*/status"):
        try:
            states.append(f.read_text().strip())
        except OSError:
            pass
    if not states:
        return None
    return "connected" in states


def _reexec_inhibited(args) -> None:
    """Re-run this command under kde-inhibit / systemd-inhibit so a multi-hour batch does not
    stop when the desktop idles. No-op if neither exists or we are already inside one."""
    if os.environ.get("V3MOD_INHIBITED") or getattr(args, "no_inhibit", False) or getattr(args, "dry_run", False):
        return
    if shutil.which("kde-inhibit"):
        wrapper = ["kde-inhibit", "--screenSaver", "--power", "--"]
    elif shutil.which("systemd-inhibit"):
        wrapper = ["systemd-inhibit", "--what=idle:sleep", "--why=v3mod test batch", "--"]
    else:
        return
    env = os.environ.copy()
    env["V3MOD_INHIBITED"] = "1"
    print(f"batch run: re-launching under {wrapper[0]} (idle/sleep inhibited for the duration)")
    os.execvpe(wrapper[0], [*wrapper, sys.executable, "-m", "v3mod", *sys.argv[1:]], env)


class _LogTail:
    """Follow <logs>/debug.log like `tail -F`, keeping lines that match a regex.

    The engine truncates debug.log in place partway through a run, so a plain read at the end
    loses the early months; this reopens when the file shrinks or is replaced."""

    def __init__(self, path: Path, pattern: str, out: Path):
        self.path, self.rx, self.out = path, re.compile(pattern), out
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.count = 0

    def start(self) -> "_LogTail":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        # Start at the current end: what is in the file now belongs to the previous run. The
        # engine truncates it at startup, which the size check below detects and restarts at 0.
        try:
            st0 = self.path.stat()
            pos, ino = st0.st_size, st0.st_ino
        except OSError:
            pos, ino = 0, None
        with open(self.out, "w", encoding="utf-8") as sink:
            while not self._stop.is_set():
                try:
                    st = self.path.stat()
                except OSError:
                    time.sleep(1)
                    continue
                if ino != st.st_ino or st.st_size < pos:
                    ino, pos = st.st_ino, 0
                if st.st_size > pos:
                    with open(self.path, "rb") as f:
                        f.seek(pos)
                        chunk = f.read()
                    pos += len(chunk)
                    for line in chunk.decode("utf-8", errors="replace").splitlines():
                        if self.rx.search(line):
                            sink.write(line + "\n")
                            self.count += 1
                    sink.flush()
                time.sleep(1)


def _suite_files(mods: list[paths.Project]) -> list[Path]:
    out: list[Path] = []
    for m in mods:
        out.extend(sorted((m.mod_dir / "tools/scripted_tests").glob("*.txt")))
    return out


def _hide_suites(files: list[Path], only: set[str], skip: set[str]) -> list[tuple[Path, Path]]:
    """Rename suite files not selected by --only/--skip to .v3mod-ignored for the run."""
    renamed: list[tuple[Path, Path]] = []
    for f in files:
        stem = f.stem
        hide = (only and stem not in only) or (stem in skip)
        if hide:
            target = f.with_name(f.name + IGNORED_SUFFIX)
            f.rename(target)
            renamed.append((f, target))
    return renamed


def _mods_to_load(proj: paths.Project, spec: str | None) -> list[paths.Project]:
    """The workspace mods the game should load: --load's list, always including the selected mod."""
    if not spec:
        return [proj]
    ws = proj.workspace or paths.find_workspace(proj.root)
    out: list[paths.Project] = []
    for name in [n.strip() for n in spec.split(",") if n.strip()]:
        m = ws.mod(name) if ws else None
        if m is None:
            raise SystemExit(f"error: --load: no mod '{name}' in the workspace")
        if all(m.root != o.root for o in out):
            out.append(m)
    if all(proj.root != o.root for o in out):
        out.insert(0, proj)
    return out


def _run_once(args, proj, game, user_dir, mods, seed, out_dir: Path) -> tuple[int, list[tuple[str, str, str]]]:
    """One launch: returns (exit code, parsed results). Writes tests.txt / failed.txt / saves / logs
    into out_dir. Exit 3 means the game died before writing results (retryable)."""
    result_file = user_dir / RESULT_FILE
    save_dir = user_dir / "save games"
    logs_dir = user_dir / "logs"

    class A:
        steam = False; direct = True; runtime = args.runtime
        mod = args.mod; proton = args.proton
        tests = False; no_save_after_failed_test = False
        flag = ["-nographics", "-handsoff", "-scripted_tests"]
        wait = False; dry_run = args.dry_run
    if args.no_nographics:
        A.flag.remove("-nographics")
    if args.debug:
        A.flag.insert(0, "-debug_mode")
    if args.no_save_after_failed_test:
        A.flag.append("-no_save_after_failed_test")
    if args.continue_last_save:
        A.flag.append("-continuelastsave")
    if seed is not None:
        A.flag.append(f"-random_seed={seed}")
    for extra in args.flag or []:
        if extra not in A.flag:
            A.flag.append(extra)
    # v3mod.toml [run].flags (e.g. -debug_mode) must not leak into test runs.
    A._no_config_flags = True

    if args.dry_run:
        launch_mod.start_process(A)
        return 0, []

    if result_file.exists():
        result_file.unlink()
    # The engine does not overwrite a TEST_FAIL_<marker>_<date> save that already exists, so a
    # stale one from an earlier run would hide this run's failure save. They were copied into
    # framework/test-output when they were new.
    if save_dir.exists() and not args.keep_fail_saves:
        stale = list(save_dir.glob(f"{FAIL_SAVE_PREFIX}*"))
        for p in stale:
            p.unlink()
        if stale:
            print(f"removed {len(stale)} stale {FAIL_SAVE_PREFIX}* save(s)")
    before_saves = {p.name for p in save_dir.glob(f"{FAIL_SAVE_PREFIX}*")} if save_dir.exists() else set()
    for p in logs_dir.glob("debug.[0-9].log"):
        try:
            p.unlink()
        except OSError:
            pass

    renamed: list[tuple[Path, Path]] = []
    if not args.keep_vanilla_tests:
        renamed = _hide_vanilla_tests(game, keep=set())
        print(f"hid {len(renamed)} vanilla scripted-test file(s) for this run")
    only = set(n.strip() for n in (args.only or "").split(",") if n.strip())
    skip = set(n.strip() for n in (args.skip or "").split(",") if n.strip())
    if only or skip:
        hidden = _hide_suites(_suite_files(mods), only, skip)
        renamed.extend(hidden)
        print(f"suites: running {', '.join(f.stem for f in _suite_files(mods)) or '(none)'}"
              f" (hid {len(hidden)})")

    out_dir.mkdir(parents=True, exist_ok=True)
    tail = None
    if args.tail:
        tail = _LogTail(logs_dir / "debug.log", args.tail, out_dir / "watch.log").start()

    started = time.time()
    proc = None
    results_text = ""
    died = False
    try:
        proc = launch_mod.start_process(A)
        print(f"waiting for {result_file} (poll {args.poll}s, timeout {args.timeout} min)")
        while True:
            if result_file.exists():
                results_text = result_file.read_text(encoding="utf-8", errors="replace")
                if "[" in results_text:
                    time.sleep(2)
                    results_text = result_file.read_text(encoding="utf-8", errors="replace")
                    break
            rc = proc.poll()
            if rc is not None:
                print(f"game exited ({rc}) before results were written")
                died = time.time() - started < 15 * 60
                break
            if time.time() - started > args.timeout * 60:
                print("timeout reached; stopping the game")
                break
            time.sleep(args.poll)
    except KeyboardInterrupt:
        print("\ninterrupted; stopping the game")
        raise
    finally:
        if proc is not None:
            launch_mod.stop_process(proc)
            launch_mod.stop_wineserver(getattr(A, "_proton", None))
        _restore(renamed)
        if renamed:
            print(f"restored {len(renamed)} scripted-test file(s)")
        if tail is not None:
            time.sleep(2)
            tail.stop()
            print(f"kept {tail.count} debug.log line(s) matching /{args.tail}/ in {out_dir / 'watch.log'}")

    elapsed = (time.time() - started) / 60
    new_saves = sorted(p for p in save_dir.glob(f"{FAIL_SAVE_PREFIX}*") if p.name not in before_saves) \
        if save_dir.exists() else []
    if not args.no_copy_saves:
        for p in new_saves:
            shutil.copy(p, out_dir / p.name)
    if args.debug_log:
        parts = sorted(logs_dir.glob("debug.[0-9].log"), reverse=True) + [logs_dir / "debug.log"]
        with open(out_dir / "debug.log", "wb") as sink:
            for p in parts:
                if p.exists():
                    sink.write(p.read_bytes())

    if not results_text:
        if new_saves:
            # A run cut off by the timeout writes no tests.txt, but each failed marker did write
            # its save; keep their names so `v3mod report` can still count the failures.
            failed = [re.sub(r"\.v3$", "", p.name[len(FAIL_SAVE_PREFIX):]) for p in new_saves]
            (out_dir / "failed.txt").write_text("\n".join(failed) + "\n", encoding="utf-8")
            print(f"no {RESULT_FILE} after {elapsed:.1f} min; {len(failed)} failure save(s) name the "
                  f"markers that failed (failed.txt):")
            for f in failed:
                print(f"  FAIL  {f}")
        else:
            print(f"no results after {elapsed:.1f} min. Check {paths.logs_dir() / 'error.log'} "
                  "(v3mod-errors --tail 40): did the game reach a hands-off session? "
                  "First run ever: start the binary directly once so DLCs register.")
        return (3 if died else 1), []

    parsed = _parse_results(results_text)
    (out_dir / RESULT_FILE).write_text(results_text, encoding="utf-8")
    print(f"\nscripted tests finished in {elapsed:.1f} min")
    if not parsed:
        print(results_text)
        print("(no [ OK ]/[ FAIL ] lines recognised — format may have changed; raw file shown above)")
        return 1, []
    width = max(len(n) for _, n, _ in parsed)
    fails = 0
    for status, name, date in parsed:
        fails += status == "FAIL"
        print(f"  {status:4s}  {name:<{width}}  {date}")
    print(f"\n{len(parsed) - fails} passed, {fails} failed; saved to {out_dir}")
    return (1 if fails else 0), parsed


def cmd_test(args) -> int:
    proj = paths.require_project(args)
    game = Path(proj.game).expanduser() if (proj and proj.game) else paths.game_dir()
    build = paths.game_build(game)
    if build == "none":
        raise SystemExit("error: game executable not found; set V3MOD_GAME_DIR or [tools].game")
    if build == "windows":
        if paths.proton_runner(args.proton) is None or paths.proton_env(game) is None:
            raise SystemExit(
                "error: this is the Windows build and no usable Proton install was found. "
                "Launch the game once through Steam so the prefix exists, or name a build with "
                "--proton."
            )
        print(f"note: {paths.PROTON_NOTE}")
    ls = paths.launcher_settings(game)
    user_dir = Path(ls["gameDataPath"]) if ls.get("gameDataPath") else paths.user_data_dir()

    seeds: list[int | None]
    if args.seeds:
        seeds = list(parse_seeds(args.seeds))
        if args.seed is not None:
            seeds.insert(0, args.seed)
    else:
        seeds = [args.seed]
    if len(seeds) > 1:
        _reexec_inhibited(args)

    mods = _mods_to_load(proj, args.load)
    suites = _suite_files(mods)
    if not suites:
        print(f"warning: no scripted tests in {', '.join(str(m.mod_dir / 'tools/scripted_tests') for m in mods)}")
    else:
        print(f"mod tests: {', '.join(p.name for p in suites)}")

    if _display_connected() is False:
        print("warning: no display connected (/sys/class/drm); the game needs one even for "
              "-nographics runs and will exit at startup without it")

    stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    base_out = Path(args.out).expanduser() if args.out else proj.root / "framework/test-output" / stamp
    playset_backup = None
    if args.load and not args.dry_run:
        playset_backup = launch_mod.set_content_load(user_dir, mods)
        print(f"playset for this run: {', '.join(m.root.name for m in mods)}")

    worst = 0
    try:
        for i, seed in enumerate(seeds):
            out_dir = base_out / f"seed-{seed}" if len(seeds) > 1 or (args.out and seed is not None) else base_out
            if len(seeds) > 1 and i:
                print(f"\npausing {args.pause}s before the next seed")
                time.sleep(args.pause)
            for attempt in range(args.retries + 1):
                label = f"seed {seed}" if seed is not None else "run"
                print(f"\n=== {label}" + (f", attempt {attempt + 1}" if attempt else "") + f"  {time.strftime('%H:%M')}")
                rc, _ = _run_once(args, proj, game, user_dir, mods, seed, out_dir)
                if rc == 3 and attempt < args.retries:
                    print("startup failure; retrying in 45s")
                    time.sleep(45)
                    continue
                break
            worst = max(worst, rc if rc != 3 else 1)
    except KeyboardInterrupt:
        print("\nbatch aborted")
        worst = 130
    finally:
        if playset_backup is not None:
            launch_mod.restore_content_load(user_dir, playset_backup)
            print("playset restored")
    if len(seeds) > 1:
        print(f"\nbatch done: {len(seeds)} seed(s) under {base_out}\n  v3mod report {base_out}")
    return worst
