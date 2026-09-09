# v3mod (core)

Scaffold a Victoria 3 mod, lint it with [Tiger](https://github.com/amtep/tiger), link it into the
game's mod folder, launch straight into the game, and run scripted tests headless.
Python 3.11+, standard library only. **Target: Linux** (native Steam).

## Install

```bash
pipx install --editable ~/Tools/v3mod/core
pipx ensurepath
```

On Bazzite / Fedora Atomic, get pipx from Homebrew (`brew install pipx`) — not `dnf`, not system
`pip` (PEP 668 blocks it). A plain venv works too:

```bash
python3 -m venv ~/.venvs/v3mod && ~/.venvs/v3mod/bin/pip install -e ~/Tools/v3mod/core
ln -s ~/.venvs/v3mod/bin/v3mod ~/.local/bin/v3mod
```

Then put `vic3-tiger` on PATH:

```bash
curl -L https://github.com/amtep/tiger/releases/download/v1.19.0/vic3-tiger-linux-v1.19.0.tar.gz | tar xz -C /tmp
cp /tmp/vic3-tiger-linux-v1.19.0/vic3-tiger ~/.local/bin/ && chmod +x ~/.local/bin/vic3-tiger
```

## Commands

| Command | What it does |
|---|---|
| `v3mod new [parent]` | Interactive scaffold: name, id, version, game version, description, tags, prefix, MP flag, CMF dependency, git init, symlink. Every prompt has a flag; `-y` accepts defaults. |
| `v3mod lint [--ci] [--baseline]` | Tiger. `--ci` gives a severity summary and exits 1 at/above `--fail-on` (default `warning`). `--baseline` snapshots today's reports so later runs show only new ones. |
| `v3mod test` | Headless scripted tests: `-nographics -handsoff -scripted_tests`, hides vanilla's own tests for the run, polls `tests.txt`, stops the process group, copies results and `TEST_FAIL_*.v3` saves to `framework/test-output/<timestamp>/`, prints a table, exits 1 on failure. |
| `v3mod launch` | Runs the binary directly inside the Steam Linux Runtime with `SteamAppId` set: no Paradox launcher, no Steam shader pre-processing. `--steam` for the old path. |
| `v3mod flags` | Probes the binary for known engine flags (`-nographics`, `-handsoff`, `-continuelastsave`, …). |
| `v3mod link` / `unlink` | Symlink `mod/` into `~/.local/share/Paradox Interactive/Victoria 3/mod/<name>`. |
| `v3mod check-overrides` | Fails if a mod file shadows a vanilla file and isn't declared in `framework/overrides.txt`. |
| `v3mod playset show` / `enable` | Inspect/edit the launcher's `dlc_load.json`. |
| `v3mod paths` / `doctor` | Resolved directories; toolchain health. |
| `v3mod sync` | Planned: patch-upgrade helper. |

Error-log tooling and settings profiles are separate add-ons (`v3mod-errors`, `v3mod-settings`).

## Layout

```
~/Tools/v3mod/                                              this tool
~/Mods/V3/<name>/                                           one repo per mod (`v3mod new ~/Mods/V3`)
~/Mods/V3/<name>/mod/                                       the part the game sees
~/.local/share/Paradox Interactive/Victoria 3/mod/<name>    -> symlink to the above
```

Keep paths ASCII-only; the game refuses to load mods whose path has non-ASCII characters.

The symlink exists because the launcher only recognises a folder with `.metadata/metadata.json` at
its top level — a repo placed directly in the game's mod folder would have to be all mod, with
`.git`, `framework/` and tooling inside what the game scans and the Workshop uploads.

## Environment overrides

- `V3MOD_GAME_DIR` — game install (the folder containing `game/` and `binaries/`)
- `V3MOD_USER_DIR` — user data dir (default `~/.local/share/Paradox Interactive/Victoria 3`)

Game detection also reads every library in `steamapps/libraryfolders.vdf`.
