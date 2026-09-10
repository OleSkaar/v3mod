# v3mod-modding skill

An [Agent Skill](https://code.claude.com/docs/en/skills) that teaches Claude how to build and test
Victoria 3 mods in a workspace managed by the `v3mod` CLI.

## Install

Skills are discovered from `~/.claude/skills/` (all projects) or `.claude/skills/` (one project).
Install it globally so nothing agent-related has to live inside a mod workspace:

```bash
mkdir -p ~/.claude/skills
cp -r v3mod-modding ~/.claude/skills/
```

Restart Claude Code, then confirm with `/skills`.

## Why global, and why no CLAUDE.md

An earlier version wrote `CLAUDE.md` and `AGENTS.md` into each mod repo, with machine paths pinned
in a table. That produced warnings about importing from outside the working directory and put
machine-specific state under version control. Installing it into the mod workspace has the same
problem one level up: the skill would be versioned per workspace and drift from the CLI it drives.
It instead:

- lives outside every mod workspace, installed once for all projects,
- discovers paths at run time by calling `v3mod paths`,
- loads its reference files only when the task needs them (progressive disclosure).

A mod workspace therefore contains only mod content plus `v3mod-workspace.toml`, each mod's
`v3mod.toml`, and `framework/`.

## Layout

```
v3mod-modding/
  SKILL.md                 always-loaded: rules, orientation, commands, definition of done
  references/placement.md  loaded when writing files: override rules, INJECT/REPLACE semantics
  references/testing.md    loaded when writing or running tests
```

## Companion skill

For deeper per-system game knowledge (economy, politics, GUI, localization) install
[`JDeffner/paradox-ai-modding`](https://github.com/JDeffner/paradox-ai-modding)'s `vic3-modding`
skill alongside this one. That skill owns *game* knowledge; this one owns the *workflow* and the
`v3mod` commands. They compose.

```bash
git clone --depth 1 https://github.com/JDeffner/paradox-ai-modding /tmp/pam
cp -r /tmp/pam/plugins/paradox-ai-modding/skills/vic3-modding ~/.claude/skills/
```

That skill detects the game and user-data directories itself, using the locations that are typical
on Windows. On a Proton install those guesses are wrong — the user data lives inside the Steam
compatdata prefix — so prefer `v3mod paths` when the two disagree.

## Requires

`v3mod` on PATH. Optional: `v3mod-errors` for the `--mine` / `--conflicts` log filtering the skill
mentions.
