"""`v3mod-settings` — named profiles for the game's pdx_settings.json.

  v3mod-settings save potato [--sections Graphics]   snapshot current settings into framework/settings/potato.json
  v3mod-settings use potato                          merge that profile into the live file (top-level keys only)
  v3mod-settings list / show potato / diff potato

A profile is just a JSON object. When applied, each top-level key in the profile replaces the
same key in the live file; keys the profile doesn't mention are left alone. Save with
`--sections Graphics` to get a profile that only touches graphics. The live file is backed up to
pdx_settings.json.bak before every write. Apply a profile with `v3mod-settings use NAME` before `v3mod launch`; headless
`v3mod test` runs render nothing, so profiles are not needed there.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from v3mod import paths

SETTINGS_FILE = "pdx_settings.json"


def live_path() -> Path:
    return paths.user_data_dir() / SETTINGS_FILE


def profiles_dir(proj: paths.Project | None) -> Path:
    if proj is not None:
        return proj.root / "framework/settings"
    return paths.user_data_dir() / "v3mod_settings"


def _load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"error: {path} not found (run the game once so it writes settings)")
    except json.JSONDecodeError as e:
        raise SystemExit(f"error: {path} is not valid JSON: {e}")
    if not isinstance(data, dict):
        raise SystemExit(f"error: {path} is not a JSON object")
    return data


def _profile_path(proj, name: str) -> Path:
    return profiles_dir(proj) / f"{name}.json"


def save_profile(proj, name: str, sections: list[str] | None) -> Path:
    live = _load(live_path())
    if sections:
        missing = [s for s in sections if s not in live]
        if missing:
            raise SystemExit(f"error: section(s) not in {SETTINGS_FILE}: {', '.join(missing)}. "
                             f"Top-level keys are: {', '.join(live.keys())}")
        data = {s: live[s] for s in sections}
    else:
        data = live
    dest = _profile_path(proj, name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return dest


def apply_profile(proj, name: str) -> tuple[Path, list[str]]:
    src = _profile_path(proj, name)
    if not src.exists():
        raise SystemExit(f"error: profile {src} not found; create it with `v3mod settings save {name}`")
    profile = _load(src)
    target = live_path()
    live = _load(target)
    shutil.copy(target, target.with_suffix(".json.bak"))
    changed = [k for k in profile if live.get(k) != profile[k]]
    live.update(profile)
    target.write_text(json.dumps(live, indent=2) + "\n", encoding="utf-8")
    return target, changed


def _flat(d: dict, prefix: str = "") -> dict[str, object]:
    out: dict[str, object] = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flat(v, key + "."))
        else:
            out[key] = v
    return out


def cmd_settings(args) -> int:
    proj = paths.find_project()
    sub = args.settings_command

    if sub == "list":
        d = profiles_dir(proj)
        names = sorted(p.stem for p in d.glob("*.json")) if d.exists() else []
        print(f"profiles in {d}:" if names else f"no profiles in {d}")
        for n in names:
            print(f"  {n}")
        return 0

    if sub == "save":
        dest = save_profile(proj, args.name, args.sections)
        scope = f"sections {', '.join(args.sections)}" if args.sections else "all sections"
        print(f"saved {scope} to {dest}")
        return 0

    if sub == "use":
        target, changed = apply_profile(proj, args.name)
        print(f"applied profile '{args.name}' to {target} (backup: {target.name}.bak)")
        print("  changed top-level sections: " + (", ".join(changed) if changed else "none"))
        return 0

    if sub == "show":
        src = _profile_path(proj, args.name)
        if not src.exists():
            raise SystemExit(f"error: {src} not found")
        print(src.read_text(encoding="utf-8"))
        return 0

    if sub == "diff":
        src = _profile_path(proj, args.name)
        if not src.exists():
            raise SystemExit(f"error: {src} not found")
        prof, live = _flat(_load(src)), _flat(_load(live_path()))
        rows = [(k, live.get(k, "<absent>"), v) for k, v in prof.items() if live.get(k) != v]
        if not rows:
            print(f"live settings already match profile '{args.name}'")
            return 0
        width = max(len(k) for k, _, _ in rows)
        print(f"{'key':<{width}}  live -> profile")
        for k, a, b in rows:
            print(f"{k:<{width}}  {a!r} -> {b!r}")
        return 0

    raise SystemExit(f"unknown settings command {sub}")
