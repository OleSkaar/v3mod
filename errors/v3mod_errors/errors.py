"""`v3mod-errors` — work with the game's error.log.

  v3mod-errors                     print the whole current error.log
  v3mod-errors --tail 50           last 50 lines
  v3mod-errors --mine              only lines that reference a file in this mod
  v3mod-errors --grep PATTERN      regex filter
  v3mod-errors --baseline NAME     save normalised lines as framework/baseline/NAME.txt
  v3mod-errors --diff NAME         show lines not present in that baseline

Normalisation strips timestamps and replaces long numbers (ids, dates) so a
vanilla baseline captured at the same checkpoint stays stable across runs.
"""

from __future__ import annotations

import re
from pathlib import Path

from v3mod import paths

_TS = re.compile(r"^\[\d{2}:\d{2}:\d{2}(?:\.\d+)?\]")
_INNER_TS = re.compile(r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?\]")
_LONGNUM = re.compile(r"\b\d{4,}\b")


def normalise(line: str) -> str:
    line = _TS.sub("", line.rstrip("\r\n"))
    line = _INNER_TS.sub("[ts]", line)
    line = _LONGNUM.sub("#", line)
    return line.strip()


def error_log_path() -> Path:
    return paths.logs_dir() / "error.log"


def read_log(path: Path) -> list[str]:
    if not path.exists():
        raise SystemExit(f"error: {path} not found (run the game with -debug_mode first)")
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def _mentions_mod(line: str, manifest: set[str], mod_dir_name: str) -> bool:
    if mod_dir_name and f"mod/{mod_dir_name}/" in line.replace("\\", "/"):
        return True
    norm = line.replace("\\", "/")
    for rel in manifest:
        if rel in norm:
            return True
    return False


def cmd_errors(args) -> int:
    proj = paths.find_project()
    if args.conflicts:
        log_path = paths.logs_dir() / "database_conflicts.log"
    else:
        log_path = Path(args.file) if args.file else error_log_path()
    lines = read_log(log_path)

    if args.grep:
        rx = re.compile(args.grep)
        lines = [l for l in lines if rx.search(l)]

    if args.mine:
        if proj is None:
            raise SystemExit("error: --mine needs a v3mod project (v3mod.toml)")
        manifest = paths.mod_file_manifest(proj.mod_dir)
        lines = [l for l in lines if _mentions_mod(l, manifest, proj.root.name)]

    if args.baseline:
        if proj is None:
            raise SystemExit("error: --baseline needs a v3mod project (v3mod.toml)")
        proj.baseline_dir.mkdir(parents=True, exist_ok=True)
        dest = proj.baseline_dir / f"{args.baseline}.txt"
        uniq = sorted({normalise(l) for l in lines if l.strip()})
        dest.write_text("\n".join(uniq) + "\n", encoding="utf-8")
        print(f"wrote {len(uniq)} normalised lines to {dest}")
        return 0

    if args.diff:
        if proj is None:
            raise SystemExit("error: --diff needs a v3mod project (v3mod.toml)")
        src = proj.baseline_dir / f"{args.diff}.txt"
        if not src.exists():
            raise SystemExit(f"error: baseline {src} not found (create with --baseline {args.diff})")
        base = set(src.read_text(encoding="utf-8").splitlines())
        new = [l for l in lines if l.strip() and normalise(l) not in base]
        print(f"{len(new)} line(s) not in baseline '{args.diff}' ({len(lines)} total)")
        lines = new

    if args.tail:
        lines = lines[-args.tail:]

    for l in lines:
        print(l)
    return 1 if (args.diff and lines) else 0
