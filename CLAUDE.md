# v3mod — repo guide

Linux-first tooling for Victoria 3 mods. This repo is **the tooling**, not a mod. Mods it scaffolds
live elsewhere, in a single **workspace** monorepo (`~/Mods/V3/`, one mod per `mods/<dir>/`).

## Background

The design conversation that produced this code is summarised in an artifact:

<https://claude.ai/public/artifacts/b7b36038-944e-4ca5-aa1c-27b1a45d6568>

Read it for *why* things are shaped the way they are. It is a snapshot of the development process so
far, not a specification — it may be trimmed or fall behind. Where it and the code disagree, the
code and the READMEs win.

## Layout

Four independent pieces; only `core` is required, and core knows nothing about the other three.

| Path | Package / install | Role |
|---|---|---|
| `core/` | `v3mod` (`pipx install --editable ./core`) | The CLI: `new`, `add`, `mods`, `lint`, `test`, `launch`, `link`, `playset`, `paths`, `doctor`. |
| `errors/` | `v3mod-errors` | Optional: filter `error.log` to this mod, diff a vanilla baseline, read `database_conflicts.log`. |
| `settings/` | `v3mod-settings` | Optional: named `pdx_settings.json` profiles. Only for manual sessions — `v3mod test` is headless. |
| `skill/v3mod-modding/` | copied to `~/.claude/skills/` | Agent Skill teaching the workflow; calls the CLI. |

Each piece has its own README with the details; the root `README.md` is the overview.

## Conventions

- **Python 3.11+, standard library only** in `core`. The add-ons depend only on `v3mod`.
- **No agent-specific code in `core`.** The agent layer is the skill, installed globally.
- **No machine paths in files.** Anything path-shaped is resolved at run time by `v3mod paths`
  (overridable with `V3MOD_GAME_DIR` / `V3MOD_USER_DIR`), never hardcoded or committed.
- **One workspace, many mods.** `v3mod new <dir>` creates the workspace — `v3mod-workspace.toml`
  at the root, mods under `mods/<dir>/`, one git repo — and its first mod; `v3mod add` creates
  every later mod, inheriting the workspace's `[defaults]` and `[tools]`. Workspaces don't nest,
  and `new` refuses to run inside one.
- **Two config files, clear split.** `v3mod-workspace.toml` marks the root and holds what mods
  share; `mods/<dir>/v3mod.toml` holds only that mod's own name, id, prefix and run flags.
  `paths.resolve_project` picks the mod: `--mod` first, then the working directory, then the
  workspace's only mod; several mods and no selection is an error that lists them.
- **Mod folders stay clean**: a scaffolded mod contains mod content plus `v3mod.toml` and
  `framework/` — no `CLAUDE.md`, no tooling. The skill stays global in `~/.claude/skills/`, not
  in the workspace. That rule is about *mod* content; this file is the tooling repo's own guide.
- The community owns most of the stack — Tiger validates, the engine runs scripted tests natively
  (`-nographics -handsoff -scripted_tests`). `v3mod` is the Linux glue and the scaffold.

## Checks

```bash
python3 -m compileall -q core errors settings   # nothing else is wired up yet
```

There is no test suite in this repo yet.
