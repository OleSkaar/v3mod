"""`v3mod new` — scaffold a new mod repository."""

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


# --------------------------------------------------------------------------- #
# answers
# --------------------------------------------------------------------------- #

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
    git_init: bool
    link: bool


def collect_answers(args) -> Answers:
    ni = bool(args.yes)

    name = ask("Mod name", default="My Mod", preset=args.name,
               validate=_v_nonempty, non_interactive=ni)
    slug = _slug(name)
    dir_name = ask("Directory name", default=slug, preset=args.dir,
                   validate=_v_dir_name, non_interactive=ni)
    author = ask("Author / GitHub handle", default="me", preset=args.author,
                 validate=_v_nonempty, non_interactive=ni)
    mod_id = ask("Mod id (reverse-domain, never change it later)",
                 default=f"com.github.{_slug(author)}.{slug}", preset=args.id,
                 validate=_v_mod_id, non_interactive=ni)
    version = ask("Mod version", default="1.0.0", preset=args.version,
                  validate=_v_version, non_interactive=ni)
    game_version = ask("Supported game version ('*' wildcard, '+' = or higher)",
                       default=DEFAULT_GAME_VERSION, preset=args.game_version,
                       validate=_v_nonempty, non_interactive=ni)
    description = ask("Short description", default=f"{name} for Victoria 3",
                      preset=args.description, non_interactive=ni)
    tags = ask_list("Tags (max 5)", default=[], preset=args.tags, max_items=5,
                    non_interactive=ni)
    prefix = ask("Script prefix (used in file names, variables, loc keys)",
                 default=_short_prefix(slug), preset=args.prefix,
                 validate=_v_prefix, non_interactive=ni)
    multiplayer = ask_bool("Multiplayer synchronized?", default=True,
                           preset=args.multiplayer, non_interactive=ni)
    depend_cmf = ask_bool("Depend on Community Mod Framework (CMF)?", default=False,
                          preset=args.cmf, non_interactive=ni)
    git_init = ask_bool("Initialise a git repository?", default=True,
                        preset=None if args.git is None else args.git, non_interactive=ni)
    link = ask_bool("Link the mod into the game's mod folder now?", default=True,
                    preset=None if args.link is None else args.link, non_interactive=ni)
    return Answers(name, dir_name, author, mod_id, version, game_version,
                   description, tags, prefix, multiplayer, depend_cmf, git_init, link)


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
# file templates
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
    return f'''# v3mod project config (read by the v3mod CLI)
[mod]
name = "{a.name}"
id = "{a.mod_id}"
prefix = "{a.prefix}"
dir = "mod"            # mod root relative to this file (the folder that is linked into the game)

[tools]
# Path to the vic3-tiger executable. Leave empty to search PATH.
tiger = ""
# Path to the Victoria 3 install (folder containing game/ and binaries/). Leave empty to autodetect.
game = ""

[run]
# Command-line flags added when v3mod launches the game.
flags = ["-debug_mode"]
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


def gitignore() -> str:
    return '''# v3mod
framework/baseline/*.log
framework/run/
*.log
.DS_Store
Thumbs.db
__pycache__/
'''


def readme(a: Answers) -> str:
    return f'''# {a.name}

{a.description}

- Mod id: `{a.mod_id}`
- Script prefix: `{a.prefix}`
- Game version: `{a.game_version}`

## Layout

- `mod/` — the mod itself (this folder is linked into `Documents/Paradox Interactive/Victoria 3/mod/`)
- `framework/` — tooling state: Tiger baseline, error-log baselines, list of fully overridden vanilla files

## Workflow

```
v3mod link            # junction/symlink mod/ into the game's mod folder (done once)
v3mod lint            # run vic3-tiger against mod/
v3mod lint --ci       # JSON output, non-zero exit on new reports
v3mod errors --tail 50   # show the end of the game's error.log
v3mod errors --mine      # only lines that reference files in this mod
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


def _keep(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / ".gitkeep").touch()


def create_project(a: Answers, parent: Path) -> Path:
    root = parent / a.dir_name
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
    _write(root / "README.md", readme(a))
    _write(root / ".gitignore", gitignore())
    _write(root / "framework/overrides.txt", overrides_txt())
    _keep(root / "framework/baseline")
    return root


def git_init(root: Path) -> bool:
    if shutil.which("git") is None:
        print("  ! git not found on PATH; skipping git init")
        return False
    try:
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    except subprocess.CalledProcessError as e:
        print(f"  ! git init failed: {e}")
        return False
    commit = subprocess.run(["git", "commit", "-q", "-m", "Scaffold mod with v3mod"],
                            cwd=root, capture_output=True, text=True)
    if commit.returncode != 0:
        msg = (commit.stderr or commit.stdout).strip().splitlines()
        hint = msg[0] if msg else "unknown error"
        print(f"  git        : repository initialised, files staged; commit skipped ({hint})")
        if "identity" in (commit.stderr or "").lower() or "user.name" in (commit.stderr or ""):
            print('               set git config user.name / user.email, then: git commit -m "Scaffold"')
        return False
    return True


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #

def cmd_new(args) -> int:
    parent = Path(args.path).resolve() if args.path else Path.cwd()
    answers = collect_answers(args)
    root = create_project(answers, parent)
    print(f"\nCreated {root}")
    print(f"  mod folder : {root / 'mod'}")
    print(f"  metadata   : mod/.metadata/metadata.json")
    print(f"  tiger conf : mod/vic3-tiger.conf")
    print(f"  smoke test : mod/tools/scripted_tests/{answers.prefix}_smoke.txt")

    if answers.git_init:
        if git_init(root):
            print("  git        : initialised with first commit")

    if answers.link:
        try:
            target = linking.link_mod(root / "mod", answers.dir_name)
            print(f"  linked     : {target}")
        except Exception as e:  # noqa: BLE001
            print(f"  ! link failed: {e}\n    run `v3mod link` later (may need admin/dev-mode on Windows)")

    print("\nNext steps:")
    print("  cd", root.name)
    print("  v3mod lint        # needs vic3-tiger on PATH: https://github.com/amtep/tiger/releases")
    print("  Add the mod in the Paradox launcher playset (it appears under local mods).")
    return 0
