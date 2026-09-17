"""`v3mod report` — pass-rate table for scripted-test runs.

  v3mod report DIR...            each DIR is one run (holds tests.txt, or failed.txt / TEST_FAIL_*
                                 saves when the run was cut off) or a folder of runs (seed-N/...)
  v3mod report                   every run under this mod's framework/test-output/

One row per marker, one column per run, and the pass rate; a run that ended before a marker
resolved counts as unknown (shown as '.'), not as a failure.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import paths
from .testing import RESULT_FILE, FAIL_SAVE_PREFIX, _parse_results

Outcome = dict[str, str]  # marker -> "OK" | "FAIL"


def read_run(d: Path) -> Outcome | None:
    """Outcomes recorded in one run directory, or None if it holds no results at all."""
    tests = d / RESULT_FILE
    if tests.exists():
        return {name: status for status, name, _ in _parse_results(tests.read_text(encoding="utf-8", errors="replace"))}
    failed = d / "failed.txt"
    names: set[str] = set()
    if failed.exists():
        names.update(l.strip() for l in failed.read_text(encoding="utf-8").splitlines() if l.strip())
    for p in d.glob(f"{FAIL_SAVE_PREFIX}*.v3"):
        names.add(p.name[len(FAIL_SAVE_PREFIX):-3])
    if not names:
        return None
    # The engine names the save TEST_FAIL_<marker>_<date>; the marker itself has no date in it.
    return {re.sub(r"_\d+ [A-Z][a-z]+, \d{4}$", "", n): "FAIL" for n in names}


def collect_runs(roots: list[Path]) -> list[tuple[str, Outcome]]:
    runs: list[tuple[str, Outcome]] = []
    for root in roots:
        if not root.is_dir():
            print(f"warning: {root} is not a directory")
            continue
        own = read_run(root)
        if own is not None:
            runs.append((root.name, own))
            continue
        for d in sorted(root.iterdir()):
            if d.is_dir():
                o = read_run(d)
                if o is not None:
                    runs.append((d.name, o))
    return runs


def _sort_key(name: str):
    # Keep markers in suite order when they carry a numeric id (nst_1_2b_..., 1.2, ...).
    nums = [int(x) for x in re.findall(r"\d+", name)]
    return (nums, name)


def cmd_report(args) -> int:
    roots = [Path(d).expanduser() for d in args.dirs]
    if not roots:
        proj = paths.require_project(args)
        roots = [proj.root / "framework/test-output"]
    runs = collect_runs(roots)
    if not runs:
        print("no results found")
        return 1
    markers = sorted({m for _, o in runs for m in o}, key=_sort_key)
    width = max(len(m) for m in markers)
    cols = [n.replace("seed-", "s") for n, _ in runs]
    cw = max(4, max(len(c) for c in cols))
    print(f"{'marker':<{width}}  " + "  ".join(f"{c:>{cw}}" for c in cols) + "   pass")
    for m in markers:
        cells, ok, known = [], 0, 0
        for _, o in runs:
            r = o.get(m)
            if r is None:
                cells.append(".")
            else:
                known += 1
                ok += r == "OK"
                cells.append("ok" if r == "OK" else "FAIL")
        rate = f"{ok}/{known}" if known else "-"
        print(f"{m:<{width}}  " + "  ".join(f"{c:>{cw}}" for c in cells) + f"   {rate}")
    print(f"\n{len(runs)} run(s); '.' = not resolved in that run (cut off before the marker's window closed)")
    return 0
