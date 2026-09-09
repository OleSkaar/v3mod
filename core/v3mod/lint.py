"""`v3mod lint` — run vic3-tiger against the mod folder.

Modes:
  v3mod lint                 human-readable Tiger output (passthrough)
  v3mod lint --ci            JSON, summary by severity, non-zero exit on findings
  v3mod lint --baseline      write framework/tiger-baseline.json (Tiger --json)
  v3mod lint --no-suppress   ignore an existing baseline
"""

from __future__ import annotations

import json
import subprocess
from collections import Counter

from . import paths

SEVERITY_ORDER = ["fatal", "error", "warning", "untidy", "tips"]  # Tiger's levels


def _tiger_cmd(proj: paths.Project, args, json_out: bool) -> list[str]:
    tiger = paths.find_tiger(proj.tiger)
    if tiger is None:
        raise SystemExit(
            "error: vic3-tiger not found. Download a release from "
            "https://github.com/amtep/tiger/releases and put it on PATH, or set "
            "[tools].tiger in v3mod.toml."
        )
    cmd = [tiger]
    if json_out:
        cmd.append("--json")
    if args.no_color:
        cmd.append("--no-color")
    if args.consolidate:
        cmd.append("--consolidate")
    if args.unused:
        cmd.append("--unused")
    game = args.game or proj.game or None
    if game:
        cmd += ["--game", game]
    if not args.no_suppress and not args.baseline and proj.tiger_baseline.exists():
        cmd += ["--suppress", str(proj.tiger_baseline)]
    cmd.append(str(proj.mod_dir))
    return cmd


def _severity(report: dict) -> str:
    return str(report.get("severity", "unknown")).lower()


def cmd_lint(args) -> int:
    proj = paths.require_project()
    want_json = bool(args.ci or args.baseline or args.json)
    cmd = _tiger_cmd(proj, args, json_out=want_json)

    if not want_json:
        return subprocess.run(cmd).returncode

    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode not in (0, 1) and not result.stdout.strip():
        print(result.stderr)
        raise SystemExit(f"error: tiger exited with {result.returncode}")

    try:
        reports = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        print(result.stdout)
        raise SystemExit("error: could not parse Tiger JSON output")

    if args.baseline:
        proj.tiger_baseline.parent.mkdir(parents=True, exist_ok=True)
        proj.tiger_baseline.write_text(result.stdout, encoding="utf-8")
        print(f"wrote baseline with {len(reports)} reports to {proj.tiger_baseline}")
        return 0

    if args.json:
        print(result.stdout)
        return 0

    counts = Counter(_severity(r) for r in reports)
    print(f"tiger: {len(reports)} report(s)"
          + (f" (excluding baseline {proj.tiger_baseline.name})" if "--suppress" in cmd else ""))
    for sev in SEVERITY_ORDER:
        if counts.get(sev):
            print(f"  {sev:8s} {counts[sev]}")
    other = {k: v for k, v in counts.items() if k not in SEVERITY_ORDER}
    for sev, n in other.items():
        print(f"  {sev:8s} {n}")

    threshold = SEVERITY_ORDER.index(args.fail_on)
    failing = [r for r in reports
               if _severity(r) in SEVERITY_ORDER and SEVERITY_ORDER.index(_severity(r)) <= threshold]
    if failing:
        for r in failing[: args.limit]:
            loc = ""
            locs = r.get("locations") or []
            if locs:
                first = locs[0]
                loc = first.get("path", "?")
                if first.get("linenr") is not None:
                    loc += f":{first['linenr']}"
                loc += " "
            print(f"  - [{_severity(r)}] {loc}{r.get('message', '')}")
        if len(failing) > args.limit:
            print(f"  ... and {len(failing) - args.limit} more")
        return 1
    return 0
