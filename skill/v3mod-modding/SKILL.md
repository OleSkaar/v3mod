---
name: v3mod-modding
description: >-
  Build and test Victoria 3 mods in a workspace managed by the v3mod CLI. Use when the user asks to
  add or change Victoria 3 content (buildings, laws, journal entries, decisions, events, AI
  strategies, production methods, localization), when a directory contains v3mod-workspace.toml,
  v3mod.toml or a mod/.metadata/metadata.json, or when they ask to lint, launch, or run scripted
  tests for a Vic3 mod. Covers picking the right mod in a multi-mod workspace, where each kind of
  change belongs, INJECT/REPLACE override rules, verifying identifiers against the game's own docs,
  and the v3mod commands for linting and headless testing.
---

# Victoria 3 modding with v3mod

Three rules that prevent most wasted work:

1. **Never write an identifier from memory.** Every effect, trigger, scope and modifier is verified
   against the game's own dumps before it goes in a file (see "Verify identifiers").
2. **Copy a vanilla example** of the thing being built before writing it. Vanilla wins over docs
   where they disagree.
3. **Nothing is done until `v3mod lint --ci` passes.** The engine's default failure mode is silence:
   a missing BOM, a wrong folder or one unbalanced brace makes the game ignore the file with no error.

## Orient first

Run `v3mod paths` to get the resolved game directory, user-data directory, logs, and the workspace
and mod for this machine. Do not hardcode paths.

Mods live together in one **workspace**: `v3mod-workspace.toml` at the root, one mod per
`mods/<dir>/`, each with its own `mod/` (what the game loads) and `framework/` (tooling state).

- `v3mod paths` reports no workspace → nothing is set up here. `v3mod new` makes the *working
  directory* a workspace, so ask where it should go and `cd` there first; never run it blind.
- It reports a workspace but no selected mod → several mods and none chosen. Run `v3mod mods`, then
  either `cd mods/<dir>` or pass `--mod <dir>` to every command. Ask which one if it isn't obvious;
  never guess when a change could land in the wrong mod.
- A new mod goes in with `v3mod add "<name>"` — never by hand, and never a second workspace.

Key locations it reports:

- `<game>/game/` — vanilla script. Read-only reference; copy examples from here.
- `<game>/game/**/*.md` — ~91 schema docs beside the folders they describe (e.g.
  `common/buildings/buildings.md`): legal keys, types, defaults, scopes.
- `<user data>/docs/` — `script_docs` dump (effects, triggers, scopes, event targets).
- `<user data>/logs/` — `error.log`, `database_conflicts.log`.

If `<user data>/docs/` is missing or stale, ask the user to run `script_docs` and `dump_data_types`
in the in-game console (debug mode) — those dumps are the authoritative per-patch reference.

## Verify identifiers

Before using any effect, trigger, scope or modifier name:

- Grep the `script_docs` dump in `<user data>/docs/` for the exact name. Note the file uses several
  internal formats and `modifiers.log` embeds a control byte, so match on the name, not on layout.
- Check the schema `.md` next to the target folder for legal keys of that entry type.
- Grep vanilla for a real usage: `grep -rl "<name>" <game>/game/common/ | head`.

Vic3 has **no country or character flags** — `set_country_flag` does not exist. Use variables and
saved scopes. CK3 habits ported blindly fail silently.

If a name cannot be confirmed in the dumps or vanilla, say so rather than guessing.

## Where a change goes

Load `references/placement.md` before writing files. It has the full rule table (which folders take
`INJECT:`/`REPLACE:`, which are first-wins, which need a full-file copy) and the keyword semantics.
Short version: most of `common/` takes keywords on top-level keys in your own file; `events/` and
`gui/` types are first-wins so sort your file *before* vanilla; deleting an entry needs a full-file
copy declared in `framework/overrides.txt`.

Every `.txt` and `.yml` under `mod/` is UTF-8 **with BOM**. Every new key needs localization.

## Test it

Load `references/testing.md` before writing a scripted test. Short version: tests live in
`mod/tools/scripted_tests/`, `success` and `fail` are trigger blocks evaluated daily, and
`v3mod test` runs them headless and reports pass/fail.

## Commands

```
v3mod paths                  resolved directories, workspace and selected mod
v3mod mods                   every mod in the workspace, and what is linked
v3mod add "<name>"           scaffold another mod in the workspace
v3mod lint --ci              Tiger; exit 1 on new warning+ (baseline-suppressed)
v3mod lint --ci --all        the same for every mod in the workspace
v3mod check-overrides        fails on undeclared full-file overrides of vanilla
v3mod test                   headless scripted-test run, prints OK/FAIL table
v3mod launch                 straight into the game, debug mode, no launcher
v3mod-errors --mine          error.log lines referencing this mod   (optional add-on)
v3mod-errors --conflicts     which file won each override            (optional add-on)
```

Every command above acts on the mod containing the working directory. From the workspace root, add
`--mod <dir>`; `lint`, `check-overrides`, `link` and `unlink` also take `--all`.

Run `v3mod lint --ci` after every batch of edits. Never tell the user a change works before it has
passed lint; never claim a behavioural change works before a test or a run has shown it.

## Definition of done

1. Identifiers verified against the dumps or vanilla, not memory.
2. Right folder, right naming class, right override mechanism (`references/placement.md`).
3. Localization for every new key; BOM on every file. Keys and global variables carry the mod's
   own script prefix, so sibling mods in the workspace never collide.
4. `v3mod lint --ci` and `v3mod check-overrides` pass.
5. A scripted test exists where the behaviour is testable.
6. After a run, read the error log yourself: `v3mod-errors --mine` if that add-on is installed,
   otherwise read `<user data>/logs/error.log` directly (its path comes from `v3mod paths`).
   Never assume an optional add-on is present — check, or fall back to reading the file.
