# v3mod (core)

Scaffold a Victoria 3 mod, lint it with [Tiger](https://github.com/amtep/tiger), link it into the
game's mod folder, launch straight into the game, and run scripted tests headless.
Python 3.11+, standard library only. **Target: Linux** (native Steam).

## Install

From the root of this repository, wherever you cloned it:

```bash
pipx install --editable ./core
pipx ensurepath
```

`--editable` points the install at this working tree, so pulling or editing takes effect without
reinstalling. Check what a given `v3mod` is running from with `pipx list`.

On Bazzite / Fedora Atomic, get pipx from Homebrew (`brew install pipx`) — not `dnf`, not system
`pip` (PEP 668 blocks it). A plain venv works too:

```bash
python3 -m venv ~/.venvs/v3mod && ~/.venvs/v3mod/bin/pip install -e ./core
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
| `v3mod new` | Make the **working directory** the workspace (monorepo) and scaffold its first mod. Takes no path — `cd` to where you want your mods first. Asks the shared questions once — author, mod-id prefix, game version, git init — then the mod's own: name, directory, id, version, description, tags, prefix, MP flag, CMF dependency, symlink. Every prompt has a flag; `-y` accepts defaults; `--empty` makes the workspace only. |
| `v3mod add [NAME]` | Scaffold another mod in the workspace, inheriting its `[defaults]`. Refuses a directory name, mod id or script prefix already used by a sibling. |
| `v3mod mods` | Every mod in the workspace, its id, and whether it is linked into the game. |
| `v3mod lint [--ci] [--baseline]` | Tiger. `--ci` gives a severity summary and exits 1 at/above `--fail-on` (default `warning`). `--baseline` snapshots today's reports so later runs show only new ones. |
| `v3mod test` | Headless scripted tests: `-nographics -handsoff -scripted_tests`, hides vanilla's own tests for the run, polls `tests.txt`, stops the process group, copies results and `TEST_FAIL_*.v3` saves to `framework/test-output/<timestamp>/`, prints a table, exits 1 on failure. |
| `v3mod launch` | Runs the binary directly inside the Steam Linux Runtime with `SteamAppId` set: no Paradox launcher, no Steam shader pre-processing. `--steam` for the old path. |
| `v3mod flags` | Probes the binary for known engine flags (`-nographics`, `-handsoff`, `-continuelastsave`, …). |
| `v3mod link` / `unlink` | Symlink `mod/` into `~/.local/share/Paradox Interactive/Victoria 3/mod/<dir>`. |
| `v3mod check-overrides` | Fails if a mod file shadows a vanilla file and isn't declared in `framework/overrides.txt`. |
| `v3mod playset show` / `enable` | Inspect/edit the launcher's `dlc_load.json`. |
| `v3mod paths` / `doctor` | Resolved directories; toolchain health. |
| `v3mod sync` | Planned: patch-upgrade helper. |

Every command that acts on a mod takes `--mod NAME` to pick one from the workspace root; `lint`,
`check-overrides`, `link` and `unlink` also take `--all`. Inside `mods/<dir>/` neither is needed.

Error-log tooling and settings profiles are separate add-ons (`v3mod-errors`, `v3mod-settings`).

## Layout

```
<this repo>/                                               the tooling (installed with pipx)
~/Mods/V3/                                                 a workspace (`cd` here, then `v3mod new`), one git repo
~/Mods/V3/v3mod-workspace.toml                             shared defaults and tool paths; marks the root
~/Mods/V3/mods/<dir>/                                      one mod: v3mod.toml, README, framework/
~/Mods/V3/mods/<dir>/mod/                                  the part the game sees
~/.local/share/Paradox Interactive/Victoria 3/mod/<dir>    -> symlink to the above
```

Keep paths ASCII-only; the game refuses to load mods whose path has non-ASCII characters.

The symlink exists because the launcher only recognises a folder with `.metadata/metadata.json` at
its top level — a repo placed directly in the game's mod folder would have to be all mod, with
`.git`, `framework/` and tooling inside what the game scans and the Workshop uploads.

### Config

`v3mod-workspace.toml` holds what every mod shares — `[defaults]` (author, mod-id prefix, game
version, multiplayer, CMF, link) that `v3mod add` pre-fills, and `[tools]` (tiger, game) that every
mod resolves against. Each `mods/<dir>/v3mod.toml` holds only what is that mod's own: name, id,
script prefix, `[run].flags`, and an optional `[tools]` block overriding the workspace's.

Which mod a command acts on: `--mod NAME` if given, else the mod containing the working directory,
else the workspace's only mod. With several mods and no selection, the command lists them and exits.

## Path resolution

Nothing path-shaped is hardcoded. Each path is resolved as **environment variable → `[tools]` in
config → autodetect**, and `v3mod paths` prints every result with the source it came from, so you
can see what was detected before deciding to override it.

| Path | Env | Config | Autodetected from |
|---|---|---|---|
| Game install | `V3MOD_GAME_DIR` | `[tools].game` | Steam library roots plus every library in `steamapps/libraryfolders.vdf` |
| User data | `V3MOD_USER_DIR` | `[tools].user_dir` | `<game>/launcher/launcher-settings.json` (`gameDataPath`), else `$XDG_DATA_HOME/Paradox Interactive/Victoria 3`, else the flatpak Steam path |
| Tiger | `V3MOD_TIGER` | `[tools].tiger` | `PATH` |

`launcher-settings.json` is the game's own answer for where it keeps saves, logs and mods, so it
wins over any guess. Its `$LINUX_DATA_HOME` and `%USER_DOCUMENTS%` placeholders are expanded from
the environment rather than assumed.

### Proton installs

Victoria 3 on Linux may be the **Windows build** running under Proton. Then `%USER_DOCUMENTS%`
resolves *inside the Proton prefix* —
`steamapps/compatdata/529340/pfx/drive_c/users/steamuser/Documents/…` — not `~/.local/share`, and
that prefix is the mod folder the game actually reads. v3mod detects the prefix and resolves to it.

v3mod runs a Windows build through Proton, the same way Steam would:

```
SteamLinuxRuntime_sniper/run -- <proton>/proton run <game>/binaries/victoria3.exe <flags>
```

with `STEAM_COMPAT_DATA_PATH` and `STEAM_COMPAT_CLIENT_INSTALL_PATH` set. The Proton build is the
one Steam already bound to this game (read from `compatdata/<appid>/version`); override it with
`--proton NAME`. This keeps `v3mod launch` and headless `v3mod test` working on a Proton install —
the Windows executable accepts the same `-nographics -handsoff -scripted_tests` flags.

The prefix must exist, so launch the game once through Steam before the first `v3mod test`. After a
run, v3mod calls `wineserver -k` on the prefix: killing the process group alone can leave wineserver
holding it open.
