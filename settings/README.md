# v3mod-settings

Named profiles of the game's `pdx_settings.json`. Add-on to [`v3mod`](../core).

```bash
pipx install --editable ~/Tools/v3mod/settings
```

## Do you need this?

Probably not. `v3mod test` runs the game with `-nographics`, so test runs render nothing and there
is no reason to switch to low settings for them. This is only useful for **manual** debug sessions
on a busy machine.

## Usage

```bash
# Set your real settings in-game, quit, then:
v3mod-settings save play --sections Graphics
# Set everything to minimum in-game, quit, then:
v3mod-settings save potato --sections Graphics

v3mod-settings use potato     # apply before a manual session
v3mod-settings diff play      # what would change
v3mod-settings list
```

`--sections Graphics` limits a profile to that top-level section, leaving audio and keybinds alone.
A bad `--sections` value prints the real section names.

Notes: the game rewrites `pdx_settings.json` on exit, so re-run `save play` whenever you change
settings in-game. The live file is backed up to `pdx_settings.json.bak` on every write. Profiles are
stored in `framework/settings/` in the mod repo, or the user-data dir outside one.
