"""`v3mod flags` and `v3mod test`.

flags: search the game binary for engine launch flags known from Jomini titles, so we know
       which of them this build of Victoria 3 accepts before relying on them.

test:  one-command scripted-test run:
         victoria3 -debug_mode -run_tests [-nographics] [-continuelastsave] [-random_seed=N]
       then watch for the results files the engine writes (text in the user-data dir, XML next to
       the binary), print them, and stop the game.
"""

from __future__ import annotations

import re
import shutil
import subprocess
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
    proj = paths.find_project()
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


def cmd_test(args) -> int:
    proj = paths.find_project()
    game = Path(proj.game).expanduser() if (proj and proj.game) else paths.game_dir()
    binary = paths.game_binary(game)
    if binary is None:
        raise SystemExit("error: game binary not found; set V3MOD_GAME_DIR or [tools].game")
    ls = paths.launcher_settings(game)
    user_dir = Path(ls["gameDataPath"]) if ls.get("gameDataPath") else paths.user_data_dir()
    result_file = user_dir / RESULT_FILE
    save_dir = user_dir / "save games"

    mod_tests = sorted((proj.mod_dir / "tools/scripted_tests").glob("*.txt")) if proj else []
    if proj and not mod_tests:
        print(f"warning: no scripted tests in {proj.mod_dir / 'tools/scripted_tests'}")
    else:
        print(f"mod tests: {', '.join(p.name for p in mod_tests)}")

    # Launch via the shared launcher so runtime/env handling is identical.
    class A:
        steam = False; direct = True; xvfb = args.xvfb; runtime = args.runtime
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
    if args.seed is not None:
        A.flag.append(f"-random_seed={args.seed}")
    for extra in args.flag or []:
        if extra not in A.flag:
            A.flag.append(extra)
    # v3mod.toml [run].flags (e.g. -debug_mode) must not leak into test runs.
    A._no_config_flags = True

    if args.dry_run:
        launch_mod.start_process(A)
        return 0

    if result_file.exists():
        result_file.unlink()
    before_saves = {p.name for p in save_dir.glob(f"{FAIL_SAVE_PREFIX}*")} if save_dir.exists() else set()

    renamed: list[tuple[Path, Path]] = []
    if not args.keep_vanilla_tests:
        renamed = _hide_vanilla_tests(game, keep=set())
        print(f"hid {len(renamed)} vanilla scripted-test file(s) for this run")

    started = time.time()
    proc = None
    results_text = ""
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
                break
            if time.time() - started > args.timeout * 60:
                print("timeout reached; stopping the game")
                break
            time.sleep(args.poll)
    except KeyboardInterrupt:
        print("\ninterrupted; stopping the game")
    finally:
        if proc is not None:
            launch_mod.stop_process(proc)
        _restore(renamed)
        if renamed:
            print(f"restored {len(renamed)} vanilla scripted-test file(s)")

    elapsed = (time.time() - started) / 60
    if not results_text:
        print(f"no results after {elapsed:.1f} min. Check {paths.logs_dir() / 'error.log'} "
              "(v3mod errors --tail 40): did the game reach a hands-off session? "
              "First run ever: start the binary directly once so DLCs register.")
        return 1

    parsed = _parse_results(results_text)
    out_dir = None
    if proj:
        out_dir = proj.root / "framework/test-output" / time.strftime("%Y-%m-%d_%H-%M-%S")
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / RESULT_FILE).write_text(results_text, encoding="utf-8")
        if save_dir.exists():
            for p in save_dir.glob(f"{FAIL_SAVE_PREFIX}*"):
                if p.name not in before_saves:
                    shutil.copy(p, out_dir / p.name)

    print(f"\nscripted tests finished in {elapsed:.1f} min")
    if not parsed:
        print(results_text)
        print("(no [ OK ]/[ FAIL ] lines recognised — format may have changed; raw file shown above)")
        return 1
    width = max(len(n) for _, n, _ in parsed)
    fails = 0
    for status, name, date in parsed:
        fails += status == "FAIL"
        print(f"  {status:4s}  {name:<{width}}  {date}")
    print(f"\n{len(parsed) - fails} passed, {fails} failed" + (f"; saved to {out_dir}" if out_dir else ""))
    return 1 if fails else 0
