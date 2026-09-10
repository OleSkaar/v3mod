"""`v3mod new` (create the workspace), `v3mod add` (a mod inside it), `v3mod mods`.

Layout produced:

    <workspace>/
      v3mod-workspace.toml     shared defaults and tool paths; marks the root
      README.md  .gitignore    one git repository for every mod
      mods/<dir>/v3mod.toml    one mod
      mods/<dir>/mod/          the part the game sees (symlinked into the mod folder)
      mods/<dir>/framework/    tooling state: baselines, declared overrides, test output
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import paths
from .prompts import ask, ask_bool, ask_list
from . import linking

CMF_ID = "com.github.Victoria-3-Modding-Co-op.Community-Mod-Framework"
DEFAULT_GAME_VERSION = "1.13.*"


# --------------------------------------------------------------------------- #
# validation helpers
# --------------------------------------------------------------------------- #

def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return s or "mod"


def _v_nonempty(v: str) -> str | None:
    return None if v.strip() else "must not be empty"


def _v_prefix(v: str) -> str | None:
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,15}", v):
        return "use 2-16 chars: lowercase letters, digits, underscore; start with a letter"
    return None


def _v_mod_id(v: str) -> str | None:
    if not re.fullmatch(r"[A-Za-z0-9_.\-]+", v):
        return "only letters, digits, '.', '_' and '-'"
    if ".." in v or v.startswith(".") or v.endswith("."):
        return "malformed reverse-domain id"
    return None


def _v_version(v: str) -> str | None:
    if not re.fullmatch(r"\d+(\.\d+){0,3}", v):
        return "use a dotted numeric version like 1.0.0"
    return None


def _v_dir_name(v: str) -> str | None:
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", v):
        return "ASCII letters, digits, '-' and '_' only (the game can't load non-ASCII paths)"
    return None


def _taken(kind: str, values: dict[str, str]):
    """Validator rejecting a value already used by another mod in the workspace."""
    def check(v: str) -> str | None:
        owner = values.get(v.lower())
        return f"{kind} already used by mods/{owner}" if owner else None
    return check


def _both(*validators):
    def check(v: str) -> str | None:
        for fn in validators:
            problem = fn(v)
            if problem:
                return problem
        return None
    return check


# --------------------------------------------------------------------------- #
# answers
# --------------------------------------------------------------------------- #

@dataclass
class WorkspaceAnswers:
    name: str
    author: str
    id_prefix: str
    game_version: str
    git_init: bool


@dataclass
class Answers:
    name: str
    dir_name: str
    author: str
    mod_id: str
    version: str
    game_version: str
    description: str
    tags: list[str]
    prefix: str
    multiplayer: bool
    depend_cmf: bool
    link: bool


def collect_workspace_answers(args, root: Path) -> WorkspaceAnswers:
    """Questions asked once for the whole monorepo; `v3mod add` inherits the answers."""
    ni = bool(args.yes)
    name = ask("Workspace name", default=root.name, preset=getattr(args, "workspace_name", None),
               validate=_v_nonempty, non_interactive=ni)
    author = ask("Author / GitHub handle (shared by every mod)", default="me", preset=args.author,
                 validate=_v_nonempty, non_interactive=ni)
    id_prefix = ask("Mod id prefix (each mod's id becomes <prefix>.<slug>)",
                    default=f"com.github.{_slug(author)}", preset=getattr(args, "id_prefix", None),
                    validate=_v_mod_id, non_interactive=ni)
    game_version = ask("Supported game version ('*' wildcard, '+' = or higher)",
                       default=DEFAULT_GAME_VERSION, preset=args.game_version,
                       validate=_v_nonempty, non_interactive=ni)
    git_init = ask_bool("Initialise a git repository for the workspace?", default=True,
                        preset=None if args.git is None else args.git, non_interactive=ni)
    return WorkspaceAnswers(name, author, id_prefix, game_version, git_init)


def collect_mod_answers(args, defaults: dict, siblings: list[paths.Project]) -> Answers:
    """Questions asked per mod. `defaults` comes from the workspace's [defaults] table."""
    ni = bool(args.yes)
    dirs = {p.root.name.lower(): p.root.name for p in siblings}
    ids = {p.mod_id.lower(): p.root.name for p in siblings if p.mod_id}
    prefixes = {p.prefix.lower(): p.root.name for p in siblings if p.prefix}

    author = args.author or defaults.get("author", "me")
    id_prefix = defaults.get("id_prefix") or f"com.github.{_slug(author)}"

    name = ask("Mod name", default="My Mod", preset=args.name,
               validate=_v_nonempty, non_interactive=ni)
    slug = _slug(name)
    dir_name = ask("Directory name (under mods/)", default=_free(slug, dirs), preset=args.dir,
                   validate=_both(_v_dir_name, _taken("directory", dirs)), non_interactive=ni)
    mod_id = ask("Mod id (reverse-domain, never change it later)",
                 default=f"{id_prefix}.{slug}", preset=args.id,
                 validate=_both(_v_mod_id, _taken("mod id", ids)), non_interactive=ni)
    version = ask("Mod version", default="1.0.0", preset=args.version,
                  validate=_v_version, non_interactive=ni)
    game_version = ask("Supported game version", default=defaults.get("game_version", DEFAULT_GAME_VERSION),
                       preset=args.game_version, validate=_v_nonempty, non_interactive=ni)
    description = ask("Short description", default=f"{name} for Victoria 3",
                      preset=args.description, non_interactive=ni)
    tags = ask_list("Tags (max 5)", default=[], preset=args.tags, max_items=5,
                    non_interactive=ni)
    prefix = ask("Script prefix (used in file names, variables, loc keys)",
                 default=_free(_short_prefix(slug), prefixes), preset=args.prefix,
                 validate=_both(_v_prefix, _taken("script prefix", prefixes)), non_interactive=ni)
    multiplayer = ask_bool("Multiplayer synchronized?", default=bool(defaults.get("multiplayer", True)),
                           preset=args.multiplayer, non_interactive=ni)
    depend_cmf = ask_bool("Depend on Community Mod Framework (CMF)?",
                          default=bool(defaults.get("cmf", False)),
                          preset=args.cmf, non_interactive=ni)
    link = ask_bool("Link the mod into the game's mod folder now?",
                    default=bool(defaults.get("link", True)),
                    preset=None if args.link is None else args.link, non_interactive=ni)
    return Answers(name, dir_name, author, mod_id, version, game_version,
                   description, tags, prefix, multiplayer, depend_cmf, link)


def _free(candidate: str, taken: dict[str, str]) -> str:
    """Suffix a default with _2, _3 … so it doesn't collide with a sibling mod."""
    if candidate.lower() not in taken:
        return candidate
    for n in range(2, 100):
        alt = f"{candidate}_{n}"
        if alt.lower() not in taken:
            return alt
    return candidate


def _short_prefix(slug: str) -> str:
    parts = [p for p in slug.split("_") if p]
    if len(parts) >= 2:
        cand = "".join(p[0] for p in parts)[:6]
    else:
        cand = slug[:6]
    cand = re.sub(r"[^a-z0-9_]", "", cand)
    if len(cand) < 2:
        cand = (cand + "mod")[:4]
    if not cand[0].isalpha():
        cand = "m" + cand
    return cand


# --------------------------------------------------------------------------- #
# workspace templates
# --------------------------------------------------------------------------- #

def _toml_bool(v: bool) -> str:
    return "true" if v else "false"


def workspace_toml(w: WorkspaceAnswers, defaults: dict) -> str:
    return f'''# v3mod workspace — the monorepo root. `v3mod add` creates a new mod under mods/.
[workspace]
name = "{w.name}"
mods_dir = "{paths.DEFAULT_MODS_DIR}"

[defaults]
# Pre-filled answers for `v3mod add`, so a second mod needs almost no setup.
author = "{w.author}"
id_prefix = "{w.id_prefix}"     # each mod's id becomes <id_prefix>.<slug>
game_version = "{w.game_version}"
multiplayer = {_toml_bool(bool(defaults.get("multiplayer", True)))}
cmf = {_toml_bool(bool(defaults.get("cmf", False)))}
link = {_toml_bool(bool(defaults.get("link", True)))}

[tools]
# Shared by every mod in the workspace; a mod may override them in its own v3mod.toml.
# Every one of these is autodetected when left empty — set one only when detection is wrong.
# Check what was detected, and from where, with `v3mod paths`.
# vic3-tiger executable. Empty = search PATH.  Env: V3MOD_TIGER
tiger = ""
# Victoria 3 install (the folder containing game/ and binaries/).  Env: V3MOD_GAME_DIR
game = ""
# User data dir: saves, logs, docs and the mod folder the game reads. Under Proton this lives
# inside the Steam compatdata prefix, not ~/.local/share.  Env: V3MOD_USER_DIR
user_dir = ""
'''


def workspace_gitignore() -> str:
    return '''# v3mod
mods/*/framework/baseline/*.log
mods/*/framework/run/
mods/*/framework/test-output/
*.log
.DS_Store
Thumbs.db
__pycache__/
'''


def workspace_readme(w: WorkspaceAnswers) -> str:
    return f'''# {w.name}

Victoria 3 mods by {w.author}, in one repository managed by the
[`v3mod`](https://github.com/{w.author}) CLI.

## Layout

```
v3mod-workspace.toml   shared defaults (author, id prefix, game version) and tool paths
mods/<dir>/            one mod
mods/<dir>/mod/        the part the game sees — symlinked into the game's mod folder
mods/<dir>/framework/  tooling state: Tiger baseline, error-log baselines, declared overrides
```

## Working here

```bash
v3mod mods                 # every mod in this workspace, and whether it is linked
v3mod add                  # scaffold another mod (inherits the defaults above)
```

Every mod command takes `--mod <dir>` when run from the workspace root, or acts on the current
mod when run from inside `mods/<dir>/`:

```bash
v3mod lint --mod <dir>     # Tiger
v3mod lint --ci --all      # every mod; non-zero exit on new findings
v3mod test --mod <dir>     # headless scripted tests
v3mod link --mod <dir>     # symlink into the game's mod folder
v3mod paths                # resolved directories on this machine
```

## Conventions

- Every change lives in its own file. Use `INJECT:` / `REPLACE:` keywords in keyword-supported
  folders rather than copying a whole vanilla file.
- Events and GUI types are first-wins: name override files so they sort before vanilla.
- Any vanilla file a mod fully overwrites must be listed in that mod's `framework/overrides.txt`.
- Every `.txt` and `.yml` under `mod/` is UTF-8 **with BOM**.
- Each mod keeps its own script prefix so two mods never collide in loc keys or global variables.
'''


# --------------------------------------------------------------------------- #
# mod templates
# --------------------------------------------------------------------------- #

def metadata_json(a: Answers) -> str:
    data = {
        "name": a.name,
        "id": a.mod_id,
        "version": a.version,
        "game_id": "victoria3",
        "supported_game_version": a.game_version,
        "short_description": a.description,
        "tags": a.tags,
        "relationships": [],
        "game_custom_data": {"multiplayer_synchronized": a.multiplayer},
    }
    if a.depend_cmf:
        data["relationships"].append({
            "rel_type": "dependency",
            "id": CMF_ID,
            "display_name": "Community Mod Framework",
            "resource_type": "mod",
            "version": "1.*",
        })
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def v3mod_toml(a: Answers) -> str:
    return f'''# v3mod project config for one mod. Shared settings live in ../../{paths.WORKSPACE_NAME}.
[mod]
name = "{a.name}"
id = "{a.mod_id}"
prefix = "{a.prefix}"
dir = "mod"            # mod root relative to this file (the folder that is linked into the game)

[run]
# Command-line flags added when v3mod launches the game for this mod.
flags = ["-debug_mode"]

# [tools]
# Uncomment to override the workspace's paths for this mod only.
# tiger = ""
# game = ""
# user_dir = ""
'''


def tiger_conf(a: Answers) -> str:
    return '''# vic3-tiger configuration (Paradox script format). See https://github.com/amtep/tiger
languages = {
	check = "english"
}

filter = {
	show_vanilla = no
	show_loaded_mods = no
	trigger = {
		# Add rules here to silence known false positives, e.g.:
		# NOT = { key = "unknown-field" }
	}
}

# If the mod depends on other mods (e.g. CMF), load them first so references resolve:
#load_mod = {
#	label = "CMF"
#	workshop_id = 3385002128
#}

scope_override = {
}
'''


def mod_readme(a: Answers) -> str:
    return f'''# {a.name}

{a.description}

- Mod id: `{a.mod_id}`
- Script prefix: `{a.prefix}`
- Game version: `{a.game_version}`

## Layout

- `mod/` — the mod itself (linked into the game's mod folder; `v3mod paths` shows where that is)
- `framework/` — tooling state: Tiger baseline, error-log baselines, list of fully overridden files

## Workflow

Run these from this directory, or add `--mod {a.dir_name}` from the workspace root.

```
v3mod link            # symlink mod/ into the game's mod folder (done once)
v3mod lint            # run vic3-tiger against mod/
v3mod lint --ci       # summary, non-zero exit on new reports
v3mod test            # headless scripted tests
v3mod-errors --mine   # error.log lines that reference this mod
```

## Conventions

- Every change lives in its own file. Use `INJECT:` / `REPLACE:` keywords in keyword-supported folders.
- Events and GUI types are first-wins: name override files so they sort before vanilla (`000_{a.prefix}_*.txt`).
- Any vanilla file you fully overwrite must be listed in `framework/overrides.txt`.
'''


def overrides_txt() -> str:
    return '''# One path per line, relative to the mod root, for every vanilla file this mod
# fully overwrites (same path + filename as vanilla). `v3mod check-overrides`
# fails if a shadowed vanilla file is not listed here.
'''


def global_history(a: Answers) -> str:
    return f'''# Marks that {a.name} is loaded. Used by the smoke scripted test and by
# {a.prefix}_is_active_trigger for cross-mod detection.
GLOBAL = {{
	set_global_variable = on_mod_loaded_{a.prefix}
}}
'''


def compat_trigger(a: Answers) -> str:
    return f'''# Cross-mod detection trigger (Community Mod Framework convention).
# Other mods can check `{a.prefix}_is_active_trigger = yes`.
{a.prefix}_is_active_trigger = {{
	has_global_variable = on_mod_loaded_{a.prefix}
}}
'''


def smoke_test(a: Answers) -> str:
    return f'''# Smoke test: the mod's global history file ran.
# Run with: victoria3 -debug_mode -run_tests   (results: text in Documents, XML in binaries/)
last_date = "1836.3.1"

tests = {{
	{a.prefix}_mod_loaded = {{
		acceptable_fail_rate = 0.0
		success = {{
			has_global_variable = on_mod_loaded_{a.prefix}
		}}
		fail = {{
			game_date > "1836.2.1"
		}}
	}}
}}
'''


def localization(a: Answers) -> str:
    # UTF-8 BOM is added when writing.
    return f'''l_english:
 {a.prefix}_mod_name:0 "{a.name}"
'''


# --------------------------------------------------------------------------- #
# writing
# --------------------------------------------------------------------------- #

def _write(path: Path, text: str, bom: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8")
    if bom:
        data = b"\xef\xbb\xbf" + data
    path.write_bytes(data)


def _write_new(path: Path, text: str) -> bool:
    """Write only if absent — `v3mod new .` must not clobber an existing README or .gitignore."""
    if path.exists():
        return False
    _write(path, text)
    return True


def create_workspace(root: Path, w: WorkspaceAnswers, defaults: dict) -> paths.Workspace:
    root.mkdir(parents=True, exist_ok=True)
    _write(root / paths.WORKSPACE_NAME, workspace_toml(w, defaults))
    for path, text in ((root / "README.md", workspace_readme(w)),
                       (root / ".gitignore", workspace_gitignore())):
        if not _write_new(path, text):
            print(f"  kept existing {path.name}")
    (root / paths.DEFAULT_MODS_DIR).mkdir(exist_ok=True)
    return paths.load_workspace(root / paths.WORKSPACE_NAME)


def create_mod(a: Answers, ws: paths.Workspace) -> Path:
    root = ws.mods_dir / a.dir_name
    if root.exists() and any(root.iterdir()):
        raise SystemExit(f"error: {root} already exists and is not empty")
    mod = root / "mod"
    p = a.prefix

    _write(mod / ".metadata/metadata.json", metadata_json(a))
    _write(mod / "vic3-tiger.conf", tiger_conf(a))
    # Vanilla script files carry a UTF-8 BOM and Tiger warns when it is missing,
    # so every file under mod/ except JSON is written with one.
    _write(mod / f"common/history/global/{p}_mod_loaded.txt", global_history(a), bom=True)
    _write(mod / f"common/scripted_triggers/zz_{p}_compatibility_triggers.txt", compat_trigger(a), bom=True)
    _write(mod / f"tools/scripted_tests/{p}_smoke.txt", smoke_test(a), bom=True)
    _write(mod / f"localization/english/{p}_l_english.yml", localization(a), bom=True)
    # No placeholder files inside mod/: the game and Tiger scan these folders.

    _write(root / paths.CONFIG_NAME, v3mod_toml(a))
    _write(root / "README.md", mod_readme(a))
    _write(root / "framework/overrides.txt", overrides_txt())
    (root / "framework/baseline").mkdir(parents=True, exist_ok=True)
    (root / "framework/baseline/.gitkeep").touch()
    return root


def git_init(root: Path) -> bool:
    if (root / ".git").exists():
        return False
    if shutil.which("git") is None:
        print("  ! git not found on PATH; skipping git init")
        return False
    try:
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    except subprocess.CalledProcessError as e:
        print(f"  ! git init failed: {e}")
        return False
    commit = subprocess.run(["git", "commit", "-q", "-m", "Scaffold workspace with v3mod"],
                            cwd=root, capture_output=True, text=True)
    if commit.returncode != 0:
        msg = (commit.stderr or commit.stdout).strip().splitlines()
        hint = msg[0] if msg else "unknown error"
        print(f"  git        : repository initialised, files staged; commit skipped ({hint})")
        if "identity" in (commit.stderr or "").lower() or "user.name" in (commit.stderr or ""):
            print('               set git config user.name / user.email, then: git commit -m "Scaffold"')
        return False
    return True


def _link(a: Answers, root: Path) -> None:
    if not a.link:
        return
    try:
        target = linking.link_mod(root / "mod", a.dir_name)
        print(f"  linked     : {target}")
    except Exception as e:  # noqa: BLE001
        print(f"  ! link failed: {e}\n    run `v3mod link --mod {a.dir_name}` later")


def _report_mod(a: Answers, root: Path, ws: paths.Workspace) -> None:
    rel = root.relative_to(ws.root)
    print(f"\nCreated mod {a.name} in {root}")
    print(f"  mod folder : {rel / 'mod'}")
    print(f"  metadata   : {rel / 'mod/.metadata/metadata.json'}")
    print(f"  tiger conf : {rel / 'mod/vic3-tiger.conf'}")
    print(f"  smoke test : {rel / f'mod/tools/scripted_tests/{a.prefix}_smoke.txt'}")
    _link(a, root)


# --------------------------------------------------------------------------- #
# entry points
# --------------------------------------------------------------------------- #

def _confirm_directory(root: Path, args) -> bool:
    """`v3mod new` has no path argument, so check before scattering files into the wrong directory."""
    existing = [p for p in root.iterdir() if p.name != ".git"]
    if not existing or args.yes:
        return True
    print(f"{root} is not empty ({len(existing)} entries). `v3mod new` would add "
          f"{paths.WORKSPACE_NAME}, {paths.DEFAULT_MODS_DIR}/, README.md and .gitignore here.")
    if ask_bool("Create the workspace in this directory?", default=False):
        return True
    print("aborted; cd to the directory you want the workspace in and run `v3mod new` there")
    return False


def cmd_new(args) -> int:
    """Turn the working directory into a workspace. Where that is, is the user's choice."""
    root = Path.cwd()
    if (root / paths.WORKSPACE_NAME).exists():
        raise SystemExit(
            f"error: {root} is already a v3mod workspace. Use `v3mod add` to create another mod in it."
        )
    outer = paths.find_workspace(root)
    if outer is not None:
        raise SystemExit(
            f"error: {root} is inside the workspace at {outer.root}; workspaces don't nest. "
            f"Run `v3mod add` there instead."
        )
    if (root / paths.CONFIG_NAME).exists():
        raise SystemExit(f"error: {root} holds a single-mod {paths.CONFIG_NAME}; move it under mods/ first")
    if not _confirm_directory(root, args):
        return 1

    wa = collect_workspace_answers(args, root)
    inherited = {"author": wa.author, "id_prefix": wa.id_prefix, "game_version": wa.game_version}

    # The first mod's answers become the workspace defaults, so `v3mod add` repeats them.
    answers = None if args.empty else collect_mod_answers(args, inherited, siblings=[])
    if answers is not None:
        inherited.update(multiplayer=answers.multiplayer, cmf=answers.depend_cmf, link=answers.link)

    ws = create_workspace(root, wa, inherited)
    print(f"\nCreated workspace {root}")
    print(f"  config     : {paths.WORKSPACE_NAME}")
    print(f"  mods dir   : {paths.DEFAULT_MODS_DIR}/")

    if answers is not None:
        _report_mod(answers, create_mod(answers, ws), ws)

    if wa.git_init and git_init(root):
        print("  git        : initialised with first commit")

    print("\nNext steps:")
    if answers is None:
        print("  v3mod add         # scaffold the first mod")
    else:
        print(f"  cd {paths.DEFAULT_MODS_DIR}/{answers.dir_name}")
        print("  v3mod lint        # needs vic3-tiger on PATH: https://github.com/amtep/tiger/releases")
        print("  v3mod add         # later: another mod, inheriting this workspace's defaults")
    return 0


def cmd_add(args) -> int:
    start = Path(args.workspace).resolve() if args.workspace else None
    ws = paths.require_workspace(start)
    if getattr(args, "mod_name", None):
        args.name = args.mod_name
    siblings = ws.mods()
    answers = collect_mod_answers(args, ws.defaults, siblings)
    root = create_mod(answers, ws)
    _report_mod(answers, root, ws)
    print("\nNext steps:")
    print(f"  cd {root}")
    print("  v3mod lint")
    return 0


def cmd_mods(args) -> int:
    ws = paths.require_workspace()
    mods = ws.mods()
    print(f"workspace {ws.name} at {ws.root}")
    if not mods:
        print(f"  (no mods yet — run `v3mod add`; expected under {ws.mods_dir})")
        return 0
    mods_root = paths.mods_dir()
    width = max(len(m.root.name) for m in mods)
    for m in mods:
        link = mods_root / m.root.name
        state = "linked" if link.is_symlink() or link.exists() else "not linked"
        print(f"  {m.root.name:<{width}}  {m.label}  [{m.mod_id or 'no id'}]  {state}")
    return 0
