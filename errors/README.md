# v3mod-errors

Error-log tooling for Victoria 3 mods. **Optional** add-on to [`v3mod`](../core) — core works
fully without it; install only if you want log filtering from the CLI.

```bash
pipx install --editable ~/Tools/v3mod/errors
```

## Why

Vanilla's `error.log` is already full, which makes mod-caused errors hard to spot. This filters the
log down to what you changed, and diffs a run against a saved vanilla baseline.

## Usage

```bash
v3mod-errors --tail 50            # end of the log
v3mod-errors --mine               # only lines referencing this mod's files
v3mod-errors --grep 'journal'     # regex filter
v3mod-errors --conflicts          # database_conflicts.log: which file won each override

# Baseline workflow: capture vanilla once per game version, then diff your runs.
v3mod-errors --baseline vanilla_1_13_9
v3mod-errors --diff vanilla_1_13_9   # exit 1 if there are new lines
```

Baselines are normalised (timestamps stripped, long numbers replaced) and stored in
`framework/baseline/<name>.txt` inside the mod repo.

New lines in *vanilla* files still matter — they're often caused by your mod removing something
vanilla references.

## Alternative

If you edit in VS Code, the [Paradox Modding Toolkit](https://github.com/JDeffner/paradox-modding-toolkit/wiki)
streams the running game's script errors into the Problems panel as squiggles and has an Overrides &
Conflicts view. This add-on is the CLI equivalent, for scripts, CI and agents.
