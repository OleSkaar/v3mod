# v3mod-modding skill

An [Agent Skill](https://code.claude.com/docs/en/skills) that teaches Claude how to build and test
Victoria 3 mods in a repo managed by the `v3mod` CLI.

## Install

Skills are discovered from `~/.claude/skills/` (all projects) or `.claude/skills/` (one project).
Install it globally so nothing agent-related has to live inside a mod repo:

```bash
mkdir -p ~/.claude/skills
cp -r v3mod-modding ~/.claude/skills/
```

Restart Claude Code, then confirm with `/skills`.

## Why global, and why no CLAUDE.md

An earlier version wrote `CLAUDE.md` and `AGENTS.md` into each mod repo, with machine paths pinned
in a table. That produced warnings about importing from outside the working directory and put
machine-specific state under version control. The skill instead:

- lives outside every mod repo,
- discovers paths at run time by calling `v3mod paths`,
- loads its reference files only when the task needs them (progressive disclosure).

A mod repo therefore contains only mod content plus `v3mod.toml` and `framework/`.

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
cp -r /tmp/pam/skills/vic3-modding ~/.claude/skills/
```

## Requires

`v3mod` on PATH. Optional: `v3mod-errors` for the `--mine` / `--conflicts` log filtering the skill
mentions.
