# v3mod

Linux-first tooling for Victoria 3 mods. Three installable pieces plus a skill, so the core stays
small and nothing you don't use is in the way.

| Piece | Install | What it is |
|---|---|---|
| **`core/`** | `pipx install --editable ~/Tools/v3mod/core` | The CLI: scaffold, lint via Tiger, link, launch, headless scripted tests, playset, doctor. |
| **`errors/`** | `pipx install --editable ~/Tools/v3mod/errors` | `v3mod-errors`: filter `error.log` to your mod, diff against a vanilla baseline, read `database_conflicts.log`. **Optional.** |
| **`settings/`** | `pipx install --editable ~/Tools/v3mod/settings` | `v3mod-settings`: named `pdx_settings.json` profiles (potato vs play). **Optional** — headless test runs render nothing, so this is only for manual sessions. |
| **`skill/`** | `cp -r skill/v3mod-modding ~/.claude/skills/` | Agent Skill teaching Claude the workflow; calls the CLI. |

**Only `core` is required.** `errors`, `settings` and the skill are each independent and each
optional; core has no knowledge of them and works fully without any of them installed.

## Quick start

```bash
pipx install --editable ~/Tools/v3mod/core
v3mod doctor                      # checks git, steam, tiger, game install, Steam Linux Runtime
mkdir -p ~/Mods/V3 && v3mod new ~/Mods/V3
cd ~/Mods/V3/<name>
v3mod lint                        # Tiger
v3mod launch                      # straight into the game, no launcher, no shader step
v3mod test                        # headless scripted-test run
```

Each piece has its own README with the details.

## Design notes

- **Core has no agent-specific code.** The agent layer is a skill installed to `~/.claude/skills/`,
  which discovers paths by calling `v3mod paths` rather than pinning them in a per-repo file.
- **The community owns most of the stack.** Tiger validates, the engine runs scripted tests
  natively (`-nographics -handsoff -scripted_tests`), Modding Digests track patches, CMF provides
  runtime helpers. `v3mod` is the Linux glue and the scaffold — see the working document.
