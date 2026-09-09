# Where a change goes

Vanilla and mod files load in **ASCII filename order**; files in subfolders load **after** files in
the parent folder. Between mods, playset order decides.

## Rule table

| Target | Mechanism | File naming |
|---|---|---|
| Folder that supports keywords (most of `common/`) | `INJECT:key` / `REPLACE:key` in your own file; brand-new keys need no keyword | `<prefix>_*.txt` |
| `events/`, `gui/` `type` and `template` | **First loaded wins** — own file in the folder root, sorted *before* vanilla | `000_<prefix>_*.txt` / `.gui` |
| `common/defines/` | Partial override: `NCategory = { ONE_DEFINE = x }` | `<prefix>_defines.txt` |
| `localization/` single keys | `localization/<lang>/replace/` | `<prefix>_*_l_english.yml` |
| Folder without keyword support (implicit replace, e.g. coat of arms) | Own file sorted *after* vanilla | `zz_<prefix>_*.txt` |
| Deleting an entry; changing an on_action `trigger`/`effect`; DNA data | Full-file copy at the vanilla path — **add it to `framework/overrides.txt`** | vanilla name |

## Database entry keywords (1.12+)

`INJECT:` (append, error if missing) · `REPLACE:` (replace, error if missing) ·
`TRY_INJECT:` / `TRY_REPLACE:` (no error if missing) ·
`INJECT_OR_CREATE:` / `REPLACE_OR_CREATE:` (create if missing).

Semantics that bite:

- **Top-level keys only.** `INJECT:law_x = { modifier = {...} }` is correct;
  `law_x = { INJECT:modifier = ... }` is not. There is no sub-block injection.
- **Injected modifiers are additive** (vanilla 25% + injected 50% = 75%). To remove one, inject the
  negative.
- `INJECT` **cannot add a trigger/effect block that already exists** (e.g. `is_visible`); it works
  if the entry has none.
- `script_values`, `scripted_effects`, `scripted_triggers`, `scripted_rules` are **REPLACE-only**
  (`INJECT` on them behaves as replace).
- Repeatable blocks are **appended at the end**, which can silently shadow an earlier one.
- **There is no delete keyword.** Removing an entry means a full-file copy.
- Known bug: `TRY_INJECT` silently no-ops on an entry another mod has `TRY_REPLACE`d; plain
  `INJECT` works.
- Implicit replacement (redefining a vanilla key with no keyword) does **not** work in
  keyword-supported folders — it errors.

The authoritative list of keyword-supported folders is the wiki's Mod compatibility page and
`Modding-Digests/1.12.0/inject_types.md`. When unsure whether a folder supports keywords, check
whether vanilla or another mod uses a keyword there, and prefer an own-named new key.

## Other traps

- `common/on_actions/`: you may append to `on_actions` / `events` / `random_events` lists, but you
  cannot replace a vanilla `trigger`/`effect` without copying the whole file. Prefer adding your own
  on_action to the list.
- Localization: later-loaded keys do **not** override earlier ones. Single-key overrides must go in
  `localization/<lang>/replace/`.
- `common/dna_data/`: duplicates rather than overwrites; only a file overwrite works.
- `common/genes/`: `INJECT:` applies at the **second** level.
- After a run, `<user data>/logs/database_conflicts.log` records which file won each contested
  override — use it to settle load-order questions rather than guessing.

## Deciding quickly

1. Is there a vanilla file for this kind of thing? Find it: `ls <game>/game/common/<folder>/`.
2. Is there a schema doc beside it (`<folder>.md`)? Read it for legal keys.
3. New entry → own file, no keyword. Changing a vanilla entry → `INJECT:`/`REPLACE:` in own file.
   Removing one → full-file copy, declared in `framework/overrides.txt`.
