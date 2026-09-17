# v3mod

Linux-first tooling for Victoria 3 mods. Three installable pieces plus a skill, so the core stays
small and nothing you don't use is in the way.

| Piece | Install | What it is |
|---|---|---|
| **`core/`** | `pipx install --editable ./core` | The CLI: scaffold, lint via Tiger, link, launch, headless scripted tests, playset, doctor. |
| **`errors/`** | `pipx install --editable ./errors` | `v3mod-errors`: filter `error.log` to your mod, diff against a vanilla baseline, read `database_conflicts.log`. **Optional.** |
| **`settings/`** | `pipx install --editable ./settings` | `v3mod-settings`: named `pdx_settings.json` profiles (potato vs play). **Optional** — headless test runs render nothing, so this is only for manual sessions. |
| **`skill/`** | `cp -r skill/v3mod-modding ~/.claude/skills/` | Agent Skill teaching Claude the workflow; calls the CLI. |

**Only `core` is required.** `errors`, `settings` and the skill are each independent and each
optional; core has no knowledge of them and works fully without any of them installed.

## Building and installing

Prerequisites: git, Python 3.11+ and [pipx](https://pipx.pypa.io/). There are no third-party
Python dependencies — `core` is standard library only, and the add-ons depend only on `v3mod`.

```bash
git clone https://github.com/OleSkaar/v3mod.git
cd v3mod
pipx install --editable ./core               # required
pipx install --editable ./errors             # optional
pipx install --editable ./settings           # optional
pipx ensurepath                              # once, if ~/.local/bin is not on PATH yet
cp -r skill/v3mod-modding ~/.claude/skills/  # optional: the Claude Code skill
```

`--editable` points the installed commands at this working tree, so a `git pull` or a local edit
takes effect without reinstalling. On Bazzite / Fedora Atomic, get pipx from Homebrew
(`brew install pipx`) — system `pip` is blocked by PEP 668. A plain venv works too; see
[`core/README.md`](core/README.md), which also covers putting `vic3-tiger` on `PATH` for
`v3mod lint`.

To build distributable packages instead of installing editable:

```bash
pipx run build ./core                        # -> core/dist/v3mod-<version>.whl and .tar.gz
pipx run build ./errors
pipx run build ./settings
```

Checks, before committing:

```bash
python3 -m compileall -q core errors settings   # the only automated check so far; no test suite yet
v3mod doctor                                    # git, steam, tiger, game install, Steam Linux Runtime
```

## Quick start

Mods live together in one **workspace** — a monorepo with shared defaults, created once:

```bash
pipx install --editable ./core    # from the root of this repo
v3mod doctor                      # checks git, steam, tiger, game install, Steam Linux Runtime

mkdir -p ~/Mods/V3 && cd ~/Mods/V3   # wherever you want your mods to live
v3mod new                         # makes this directory the workspace, with its first mod
v3mod add "National Strategies"   # every later mod: no setup questions worth answering twice
v3mod mods                        # what's here, and what's linked into the game
cd mods/pet_peeves
v3mod lint                        # Tiger
v3mod launch                      # straight into the game, no launcher, no shader step
v3mod test                        # headless scripted-test run
```

```
~/Mods/V3/                        the workspace — this directory is your choice, not v3mod's
  v3mod-workspace.toml            shared defaults (author, id prefix, game version) and tool paths
  mods/pet_peeves/                one mod: v3mod.toml, mod/, framework/
  mods/national_strategies/
```

Every mod command acts on the mod you're standing in; from the workspace root, name it with
`--mod <dir>` (or `--all`, where it makes sense).

`v3mod link` is the development loop — the game watches the linked folder, so edits are live.
`v3mod build` is for release: a clean copy without scripted tests or tooling files, optionally
version-stamped and zipped.

Each piece has its own README with the details.

## Design notes

- **Core has no agent-specific code.** The agent layer is a skill installed to `~/.claude/skills/`,
  which discovers paths by calling `v3mod paths` rather than pinning them in a per-repo file.
- **The community owns most of the stack.** Tiger validates, the engine runs scripted tests
  natively (`-nographics -handsoff -scripted_tests`), Modding Digests track patches, CMF provides
  runtime helpers. `v3mod` is the Linux glue and the scaffold — see the working document.
