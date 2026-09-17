"""Command-line entry point (core).

Optional add-ons register their own commands as separate console scripts:
  v3mod-errors    error.log filtering and vanilla-baseline diffing
  v3mod-settings  named pdx_settings.json profiles
"""

from __future__ import annotations

import argparse
import os
import sys

from . import __version__
from . import build, checks, launch, linking, lint, report, scaffold, testing


def _not_implemented(name: str, doc_section: str):
    def _cmd(args) -> int:
        print(f"`v3mod {name}` is not implemented yet. See the working document, section {doc_section}.")
        return 2
    return _cmd


def _mod_options(p: argparse.ArgumentParser) -> None:
    """Scaffolding flags shared by `new` and `add`.

    On `new`, --author and --game-version answer the workspace-level questions and become the
    defaults every later `v3mod add` inherits; on `add` they override those defaults for one mod.
    """
    p.add_argument("-y", "--yes", action="store_true", help="accept defaults / skip prompts")
    p.add_argument("--name")
    p.add_argument("--dir", help="directory name under mods/ (ASCII only)")
    p.add_argument("--author")
    p.add_argument("--id", help="mod id, reverse-domain style")
    p.add_argument("--version", dest="version")
    p.add_argument("--game-version", dest="game_version")
    p.add_argument("--description")
    p.add_argument("--tags", type=lambda s: [t.strip() for t in s.split(",") if t.strip()])
    p.add_argument("--prefix", help="script prefix, e.g. mymod")
    mp = p.add_mutually_exclusive_group()
    mp.add_argument("--multiplayer", dest="multiplayer", action="store_true", default=None)
    mp.add_argument("--no-multiplayer", dest="multiplayer", action="store_false")
    cmf = p.add_mutually_exclusive_group()
    cmf.add_argument("--cmf", dest="cmf", action="store_true", default=None,
                     help="declare a dependency on Community Mod Framework")
    cmf.add_argument("--no-cmf", dest="cmf", action="store_false")
    lk = p.add_mutually_exclusive_group()
    lk.add_argument("--link", dest="link", action="store_true", default=None)
    lk.add_argument("--no-link", dest="link", action="store_false")


def _mod_selector(p: argparse.ArgumentParser) -> None:
    """`--mod NAME` for commands that act on one mod in the workspace."""
    p.add_argument("-m", "--mod", metavar="NAME",
                   help="mod to act on (directory name under mods/). Default: the mod containing "
                        "the working directory, or the workspace's only mod.")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="v3mod",
        description="Victoria 3 mod CLI — scaffold, lint (Tiger), link, launch, headless scripted tests. "
                    "Optional add-ons: v3mod-errors, v3mod-settings.",
    )
    p.add_argument("--version", action="version", version=f"v3mod {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    # new / add / mods ------------------------------------------------------
    n = sub.add_parser("new", help="turn the current directory into a workspace, with its first mod")
    n.add_argument("--empty", action="store_true", help="create the workspace only, no first mod")
    n.add_argument("--workspace-name", dest="workspace_name", help="display name (default: directory name)")
    n.add_argument("--id-prefix", dest="id_prefix", help="shared mod-id prefix, e.g. com.github.me")
    g = n.add_mutually_exclusive_group()
    g.add_argument("--git", dest="git", action="store_true", default=None)
    g.add_argument("--no-git", dest="git", action="store_false")
    _mod_options(n)
    n.set_defaults(func=scaffold.cmd_new)

    a = sub.add_parser("add", help="add another mod to an existing workspace")
    a.add_argument("mod_name", nargs="?", metavar="NAME", help="mod name (same as --name)")
    a.add_argument("--workspace", metavar="PATH", help="workspace to add to (default: found from cwd)")
    _mod_options(a)
    a.set_defaults(func=scaffold.cmd_add)

    sub.add_parser("mods", help="list the mods in this workspace").set_defaults(func=scaffold.cmd_mods)

    # lint ------------------------------------------------------------------
    l = sub.add_parser("lint", help="run vic3-tiger on the mod")
    l.add_argument("--ci", action="store_true", help="summary + non-zero exit on findings")
    l.add_argument("--json", action="store_true", help="print raw Tiger JSON")
    l.add_argument("--baseline", action="store_true", help="write framework/tiger-baseline.json")
    l.add_argument("--no-suppress", action="store_true", help="ignore existing baseline")
    l.add_argument("--fail-on", choices=lint.SEVERITY_ORDER, default="warning",
                   help="minimum severity that fails --ci (default: warning)")
    l.add_argument("--limit", type=int, default=30, help="max findings to print in --ci")
    l.add_argument("--consolidate", action="store_true")
    l.add_argument("--unused", action="store_true")
    l.add_argument("--no-color", action="store_true")
    l.add_argument("--game", help="path to game install (overrides config)")
    l.add_argument("--all", action="store_true", help="lint every mod in the workspace")
    _mod_selector(l)
    l.set_defaults(func=lint.cmd_lint)

    # build -----------------------------------------------------------------
    b = sub.add_parser("build", help="copy a mod to a clean folder ready for packaging/publishing")
    b.add_argument("--zip", action="store_true", help="also write <dir>-<version>.zip beside it")
    b.add_argument("--set-version", metavar="X.Y.Z",
                   help="stamp this version into the built metadata.json (leaves the source alone)")
    b.add_argument("--with-tests", action="store_true",
                   help=f"keep {build.TEST_DIR}/ in the output (left out by default)")
    b.add_argument("--out", metavar="DIR",
                   help="parent directory for the build (default: the mod's framework/build/)")
    b.add_argument("--force", action="store_true",
                   help="overwrite an --out directory v3mod did not create")
    b.add_argument("--all", action="store_true", help="build every mod in the workspace")
    _mod_selector(b)
    b.set_defaults(func=build.cmd_build)

    # link / unlink ---------------------------------------------------------
    lnk = sub.add_parser("link", help="symlink mod/ into the game's mod folder")
    lnk.add_argument("--name", help="link name (default: the mod's directory name)")
    lnk.add_argument("--all", action="store_true", help="link every mod in the workspace")
    _mod_selector(lnk)
    lnk.set_defaults(func=linking.cmd_link)
    ulk = sub.add_parser("unlink", help="remove the symlink")
    ulk.add_argument("--name")
    ulk.add_argument("--all", action="store_true", help="unlink every mod in the workspace")
    _mod_selector(ulk)
    ulk.set_defaults(func=linking.cmd_unlink)

    # checks ----------------------------------------------------------------
    co = sub.add_parser("check-overrides", help="fail on undeclared full-file overrides of vanilla")
    co.add_argument("--game")
    co.add_argument("--all", action="store_true", help="check every mod in the workspace")
    _mod_selector(co)
    co.set_defaults(func=checks.cmd_check_overrides)
    sub.add_parser("paths", help="show detected directories").set_defaults(func=checks.cmd_paths)
    doc = sub.add_parser("doctor", help="check toolchain and workspace health")
    _mod_selector(doc)
    doc.set_defaults(func=checks.cmd_doctor)

    # launch / playset ------------------------------------------------------
    la = sub.add_parser("launch", help="launch the game directly (no launcher); --steam to go via Steam")
    la.add_argument("--steam", action="store_true", help="launch via `steam -applaunch` instead of the binary")
    la.add_argument("--direct", action="store_true", help=argparse.SUPPRESS)  # kept for compatibility; now default
    la.add_argument("--runtime", choices=["auto", "sniper", "soldier", "none"], default="auto",
                    help="run inside a Steam Linux Runtime container (default auto: sniper, then soldier; none = host libs)")
    la.add_argument("--tests", action="store_true", help="add -run_tests")
    la.add_argument("--no-save-after-failed-test", action="store_true")
    la.add_argument("--flag", action="append", metavar="FLAG", help="extra launch flag (repeatable)")
    la.add_argument("--wait", action="store_true", help="block until the process exits")
    la.add_argument("--proton", metavar="NAME",
                    help="Proton build to run a Windows install with (default: the one Steam "
                         "already bound to this game)")
    la.add_argument("--dry-run", action="store_true", help="print the command only")
    _mod_selector(la)
    la.set_defaults(func=launch.cmd_launch)

    ps = sub.add_parser("playset", help="show or set which mods the game loads (content_load.json)")
    pssub = ps.add_subparsers(dest="playset_command", required=True)
    pssub.add_parser("show", help="print content_load.json (what the game reads) and dlc_load.json")
    pset = pssub.add_parser("set", help="write content_load.json enabling exactly these workspace mods")
    pset.add_argument("mods", metavar="MOD[,MOD]", help="workspace mod directory names, comma-separated")
    pe = pssub.add_parser("enable", help="legacy: append an entry to dlc_load.json's enabled_mods")
    pe.add_argument("--entry", required=True, help='exact string to add, e.g. "mod/grand_canals"')
    ps.set_defaults(func=launch.cmd_playset)

    # test / flags ----------------------------------------------------------
    t = sub.add_parser("test", help="run scripted tests headless (-nographics -handsoff -scripted_tests) and report")
    t.add_argument("--no-nographics", action="store_true", help="render normally (keeps -handsoff)")
    t.add_argument("--debug", action="store_true", help="also pass -debug_mode")
    t.add_argument("--keep-vanilla-tests", action="store_true",
                   help="don't hide the base game's own scripted tests (they run to their last_date)")
    t.add_argument("--no-save-after-failed-test", action="store_true", help="skip the TEST_FAIL_* save on failure")
    t.add_argument("--continue-last-save", action="store_true", help="add -continuelastsave")
    t.add_argument("--seed", type=int, help="add -random_seed=N")
    t.add_argument("--seeds", metavar="LIST", help="run once per seed, in sequence: '13,14' or '13-16'; "
                   "results under <out>/seed-N/")
    t.add_argument("--load", metavar="MOD[,MOD]",
                   help="workspace mods the game loads for the run (content_load.json is written and "
                        "restored afterwards); the selected mod is always included")
    t.add_argument("--only", metavar="SUITE[,SUITE]", help="run only these scripted-test files (stems)")
    t.add_argument("--skip", metavar="SUITE[,SUITE]", help="hide these scripted-test files for the run")
    t.add_argument("--tail", metavar="REGEX",
                   help="keep debug.log lines matching REGEX live in <out>/watch.log (the engine "
                        "truncates debug.log in place mid-run)")
    t.add_argument("--debug-log", action="store_true", help="copy the whole debug.log into the output dir")
    t.add_argument("--out", metavar="DIR", help="output directory (default framework/test-output/<timestamp>)")
    t.add_argument("--retries", type=int, default=0, help="relaunch when the game dies at startup (default 0)")
    t.add_argument("--pause", type=int, default=30, help="seconds between seeds (default 30)")
    t.add_argument("--keep-fail-saves", action="store_true",
                   help="do not delete stale TEST_FAIL_* saves before the run (the engine will not "
                        "overwrite a same-named save)")
    t.add_argument("--no-copy-saves", action="store_true", help="do not copy new TEST_FAIL_* saves to the output dir")
    t.add_argument("--no-inhibit", action="store_true", help="do not wrap a multi-seed batch in kde-/systemd-inhibit")
    t.add_argument("--runtime", choices=["auto", "sniper", "soldier", "none"], default="auto")
    t.add_argument("--flag", action="append", metavar="FLAG", help="extra launch flag (repeatable)")
    t.add_argument("--poll", type=int, default=15, help="seconds between checks of tests.txt (default 15)")
    t.add_argument("--timeout", type=int, default=180, help="minutes to wait for results (default 180)")
    t.add_argument("--proton", metavar="NAME", help="Proton build to use for a Windows install")
    t.add_argument("--dry-run", action="store_true")
    _mod_selector(t)
    t.set_defaults(func=testing.cmd_test)

    fl = sub.add_parser("flags", help="probe the game binary for known engine launch flags")
    fl.set_defaults(func=testing.cmd_flags)

    r = sub.add_parser("report", help="pass-rate table across scripted-test runs")
    r.add_argument("dirs", nargs="*", metavar="DIR",
                   help="run directories, or folders of runs (default: this mod's framework/test-output)")
    _mod_selector(r)
    r.set_defaults(func=report.cmd_report)

    # planned ---------------------------------------------------------------
    sub.add_parser("sync", help="[planned] patch-upgrade helper") \
        .set_defaults(func=_not_implemented("sync", "5.5"))
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        print("\naborted")
        return 130
    except BrokenPipeError:
        # Output was piped into something that closed early (e.g. `| head`).
        # Silence Python's shutdown warning by pointing stdout at devnull.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0


if __name__ == "__main__":
    sys.exit(main())
