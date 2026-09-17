"""Query a plaintext Victoria 3 save through jomini (Rust parser, WASM build, run under node).

    from v3mod_saves import Save
    s = Save(path)
    s.get('/meta_data/game_date')          # one path -> value
    s.get('/states/database', '/pacts/database')   # several -> {path: value}, one parse
    s.tag(95) -> 'TUR'; s.id_of('TUR') -> '95'
    s.plays(initiator='TUR', target='EGY'); s.sides(play)

Saves must be plaintext (the scripted-test TEST_FAIL_* saves are; a normal save is binary unless
the game is run with -debug_mode). Files are 200-400 MB, so every path wanted from one save should
go into a single get() call; results are cached per instance.

The parser lives in a node package (jomini) that is installed on first use into
$XDG_CACHE_HOME/v3mod/pdxq (or ~/.cache/v3mod/pdxq); `v3mod-save setup` does it explicitly.
"""

from __future__ import annotations

import functools
import json
import os
import shutil
import subprocess
from pathlib import Path

JS_DIR = Path(__file__).parent / "js"


def cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "v3mod" / "pdxq"


def ensure_parser(quiet: bool = False) -> Path:
    """Copy the query script into the cache dir and `npm install` jomini there once.
    Returns the path of pdxq.mjs."""
    if shutil.which("node") is None:
        raise SystemExit("error: v3mod-save needs node (and npm) on PATH to run the jomini parser")
    d = cache_dir()
    d.mkdir(parents=True, exist_ok=True)
    for name in ("pdxq.mjs", "package.json"):
        src, dst = JS_DIR / name, d / name
        if not dst.exists() or src.read_bytes() != dst.read_bytes():
            shutil.copy(src, dst)
    if not (d / "node_modules" / "jomini").is_dir():
        if shutil.which("npm") is None:
            raise SystemExit(f"error: jomini is not installed in {d} and npm is not on PATH")
        if not quiet:
            print(f"installing jomini into {d} (once)")
        subprocess.run(["npm", "install", "--no-audit", "--no-fund", "--silent"], cwd=d, check=True)
    return d / "pdxq.mjs"


class Save:
    def __init__(self, path: str | os.PathLike):
        self.path = str(path)
        self._cache: dict[str, object] = {}

    def get(self, *paths: str):
        """Fetch one or more '/a/b' paths in a single parse; returns the value (one path) or a dict."""
        missing = [p for p in paths if p not in self._cache]
        if missing:
            script = ensure_parser(quiet=True)
            out = subprocess.run(["node", "--max-old-space-size=8192", str(script), self.path, *missing],
                                 capture_output=True, text=True, check=True).stdout
            self._cache.update(json.loads(out))
        return self._cache[paths[0]] if len(paths) == 1 else {p: self._cache[p] for p in paths}

    @functools.cached_property
    def ids(self) -> dict[str, str]:
        """country id -> tag"""
        db = self.get("/country_manager/database")
        return {k: v["definition"] for k, v in db.items() if isinstance(v, dict) and "definition" in v}

    def tag(self, cid) -> str:
        return self.ids.get(str(cid), str(cid))

    def id_of(self, tag: str) -> str | None:
        return next((k for k, v in self.ids.items() if v == tag), None)

    def plays(self, initiator: str | None = None, target: str | None = None):
        """diplomatic plays (live and dead), optionally filtered by initiator/target tag"""
        db = self.get("/diplomatic_plays/database")
        out = []
        for pid, p in db.items():
            if not isinstance(p, dict):
                continue
            if initiator and self.tag(p.get("initiator")) != initiator:
                continue
            if target and self.tag(p.get("target")) != target:
                continue
            out.append((pid, p))
        return out

    def sides(self, play: dict) -> list[tuple[str, str]]:
        """[(tag, side), ...] for a play's committed participants"""
        return [(self.tag(r["country"]), r["side"]) for r in play.get("country_records", [])]

    def state_regions(self) -> dict[str, str]:
        """state id -> STATE_* region name"""
        return {k: v.get("region", k) for k, v in self.get("/states/database").items() if isinstance(v, dict)}
