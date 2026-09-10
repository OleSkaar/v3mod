"""`v3mod build` — produce a clean copy of a mod, ready to be packaged and published.

The dev loop does not need this: `v3mod link` points the game's own file watcher straight at
`mods/<dir>/mod/`, so edits are live. Build exists for the other end — turning a working tree into
something you would hand to the Workshop:

  * dev-only files left out (scripted tests, tiger config, editor droppings, .gitkeep)
  * an optional version stamped into .metadata/metadata.json
  * an optional zip with the mod directory at its top level

Output goes to `mods/<dir>/framework/build/<dir>/`. That directory is ours to overwrite; anywhere
else named with --out is only cleaned if v3mod made it (marked by `.v3mod-build`) or --force is given.
"""

from __future__ import annotations

import json
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from . import paths

MARKER = ".v3mod-build"

# Never shipped: tooling state and editor droppings.
EXCLUDE_NAMES = {".gitkeep", ".gitignore", ".DS_Store", "Thumbs.db", "vic3-tiger.conf"}
EXCLUDE_SUFFIXES = (".swp", ".swo", "~", ".orig", ".rej", ".bak")
EXCLUDE_DIRS = {"__pycache__", ".git"}
# Dev-only content, kept out unless --with-tests.
TEST_DIR = "tools/scripted_tests"


@dataclass
class Result:
    out_dir: Path
    files: int = 0
    total_bytes: int = 0
    skipped: list[str] = field(default_factory=list)
    zip_path: Path | None = None


def _excluded(rel: Path, with_tests: bool) -> bool:
    if any(part in EXCLUDE_DIRS for part in rel.parts):
        return True
    if rel.name in EXCLUDE_NAMES or rel.name.endswith(EXCLUDE_SUFFIXES):
        return True
    if not with_tests and rel.as_posix().startswith(TEST_DIR + "/"):
        return True
    return False


def _clean(out_dir: Path, force: bool) -> None:
    """Remove a previous build, refusing to touch a directory v3mod did not create."""
    if not out_dir.exists():
        return
    ours = (out_dir.parent / MARKER).exists() or (out_dir / MARKER).exists()
    if not ours and not force:
        raise SystemExit(
            f"error: {out_dir} already exists and was not created by v3mod. "
            "Point --out somewhere else, or pass --force to overwrite it."
        )
    if not out_dir.is_dir():
        raise SystemExit(f"error: {out_dir} exists and is not a directory")
    shutil.rmtree(out_dir)


def _stamp_version(out_dir: Path, version: str) -> None:
    meta = out_dir / ".metadata/metadata.json"
    if not meta.exists():
        raise SystemExit(f"error: {meta} not found; cannot stamp a version")
    data = json.loads(meta.read_text(encoding="utf-8"))
    data["version"] = version
    meta.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _mod_version(mod_dir: Path) -> str:
    meta = mod_dir / ".metadata/metadata.json"
    try:
        return str(json.loads(meta.read_text(encoding="utf-8")).get("version", "0.0.0"))
    except (OSError, ValueError):
        return "0.0.0"


def build_mod(proj: paths.Project, out_dir: Path, with_tests: bool = False,
              version: str | None = None, force: bool = False) -> Result:
    src = proj.mod_dir
    if not src.is_dir():
        raise SystemExit(f"error: {src} not found")

    _clean(out_dir, force)
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    (out_dir.parent / MARKER).write_text(
        "Build output from `v3mod build`. Safe to delete; regenerated on the next build.\n",
        encoding="utf-8")

    result = Result(out_dir=out_dir)
    for f in sorted(src.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(src)
        if _excluded(rel, with_tests):
            result.skipped.append(rel.as_posix())
            continue
        dest = out_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dest)
        result.files += 1
        result.total_bytes += f.stat().st_size

    if not (out_dir / ".metadata/metadata.json").exists():
        raise SystemExit(
            f"error: {src}/.metadata/metadata.json is missing — the launcher will not see this mod"
        )
    if version:
        _stamp_version(out_dir, version)
    return result


def zip_build(result: Result, dir_name: str, version: str) -> Path:
    """Zip the built folder with the mod directory at the archive's top level."""
    archive = result.out_dir.parent / f"{dir_name}-{version}.zip"
    if archive.exists():
        archive.unlink()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(result.out_dir.rglob("*")):
            if f.is_file():
                z.write(f, Path(dir_name) / f.relative_to(result.out_dir))
    result.zip_path = archive
    return archive


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} GB"


def _build_one(proj: paths.Project, args) -> int:
    version = args.set_version or _mod_version(proj.mod_dir)
    out_dir = Path(args.out).resolve() / proj.root.name if args.out \
        else proj.root / "framework/build" / proj.root.name
    result = build_mod(proj, out_dir, with_tests=args.with_tests,
                       version=args.set_version, force=args.force)

    print(f"built {proj.label} {version}")
    print(f"  {result.files} file(s), {_human(result.total_bytes)} -> {out_dir}")
    if result.skipped:
        shown = ", ".join(result.skipped[:4])
        more = f" (+{len(result.skipped) - 4} more)" if len(result.skipped) > 4 else ""
        print(f"  left out {len(result.skipped)}: {shown}{more}")
    if args.zip:
        archive = zip_build(result, proj.root.name, version)
        print(f"  zip: {archive} ({_human(archive.stat().st_size)})")
    return 0


def cmd_build(args) -> int:
    if getattr(args, "all", False):
        mods = paths.require_workspace().mods()
        if not mods:
            raise SystemExit("error: the workspace has no mods yet; run `v3mod add`")
        if args.set_version:
            raise SystemExit("error: --set-version applies to one mod; drop --all or name a mod")
        worst = 0
        for proj in mods:
            print(f"\n=== {proj.root.name} ===")
            worst = _build_one(proj, args) or worst
        return worst
    return _build_one(paths.require_project(args), args)
