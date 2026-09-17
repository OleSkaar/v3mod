# Testing a change

## Scripted tests

Files live in `mod/tools/scripted_tests/*.txt`. `success` and `fail` are trigger blocks evaluated
**daily** inside a running game; the test passes if `success` is true before `fail` and before
`last_date`. If both are true on the same day, it passes.

```
last_date = "1846.1.1"

tests = {
	<prefix>_<feature> = {
		acceptable_fail_rate = 0.0
		run_count = 1
		success = { c:SWE = { has_variable = <prefix>_done } }
		fail    = { game_date > "1845.1.1" }
	}
}
```

Rules of thumb:

- Assert something **deterministic and cheap**: a variable your effect sets, a law enacted, a
  building that exists, a journal entry completed. These resolve in days of game time.
- AI *behaviour* is stochastic. Put those in a separate test with `run_count > 1` and a non-zero
  `acceptable_fail_rate`, and expect a long run.
- `last_date` gates the whole file — a distant `last_date` means a long run even if your test
  resolves early.
- Verify every trigger name used in `success`/`fail` against the dumps first. A misspelled trigger
  does not fail the test; it silently never becomes true.
- Optional annotations `### name = ...` and `### desc = ...` above a test are picked up by report
  tooling.

## Running them

```
v3mod test                   # headless: -nographics -handsoff -scripted_tests
v3mod test --seed 42         # reproducible RNG
v3mod test --keep-vanilla-tests   # also run the base game's tests (slow)
v3mod test --seeds 13-16 --out framework/bench/mod      # one game per seed, sequentially, seed-N/ each
v3mod test --load other_mod,this_mod --only suite_a      # which workspace mods load; which suite files run
v3mod test --tail "MY WATCH" --timeout 240 --retries 1   # keep matching debug.log lines; relaunch on a startup crash
v3mod report framework/bench/mod                         # marker x run table with pass rates
```

What happens: the game launches with no window and auto-starts an AI-only game; the base game's own
scripted tests are hidden for the run (they have `last_date` up to 1936 and would gate the results
file); `<user data>/tests.txt` is polled until the engine writes `[ OK ]` / `[ FAIL ]` lines; the
process group is stopped; results and any `TEST_FAIL_*.v3` saves are copied to
`framework/test-output/<timestamp>/`. Exit code is 1 if any test failed.

**First run on a machine:** the binary must have been started directly once (`v3mod launch`) or no
DLCs load in hands-off runs.

**Long runs and batches.** Vanilla pace on a mid-range machine is 1.5–3 minutes per game year;
`--timeout` is in minutes and defaults to 180. Never start two game instances at once — `--seeds`
runs them one after another and, when `kde-inhibit`/`systemd-inhibit` exists, keeps the desktop
from sleeping. The game needs a connected display even with `-nographics` (Proton exits with
"No displays available" otherwise); `v3mod test` warns when `/sys/class/drm` shows none. A run cut
off by the timeout writes no `tests.txt`, but every marker that failed already wrote its
`TEST_FAIL_<marker>_<date>.v3` save, so `failed.txt` lists those and `v3mod report` counts them;
markers still open at the cut-off are "unresolved", not failed. Stale `TEST_FAIL_*` saves are
deleted before each run because the engine will not overwrite a same-named save.

**Benchmarking against vanilla.** Put the markers and any `debug_log` diagnostics in a *companion
tests mod* (its own `mods/<x>_tests/`, scripted tests plus on_actions only), so the identical
instrumentation runs alone (`--load x_tests`: the vanilla baseline) and together with the mod
(`--load my_mod,x_tests`). Compare the two with `v3mod report`. `debug.log` is truncated in place
partway through a run, so anything the diagnostics print must be caught live with `--tail REGEX`
(it lands in `watch.log`); `--debug-log` copies the whole log at the end.

**Reading a failure save.** `TEST_FAIL_*.v3` saves are plaintext; `v3mod-save` (optional add-on)
queries them: `v3mod-save SAVE plays TUR EGY`, `involvement AUS`, `states STATE_SYRIA`,
`pacts EGY`, `strategies AUS`, `techs SIC egalitarianism`, `movements FRA`, `civil-wars`,
`globals springtime`, `get /path`. Do not parse saves with regexes; the jomini parser is exact.

If no results appear, check `error.log` — `v3mod-errors --tail 40` if that optional add-on is
installed, otherwise `tail -40 "$(v3mod paths | awk '/^logs/{$1=""; print substr($0,2)}')/error.log"`.
The usual causes are a script error preventing load, or the mod not being in the active playset
(`v3mod playset show`; `v3mod playset set my_mod` writes `content_load.json`, the file the game
reads at startup — the launcher's own playset is not what a direct launch uses).

## The wider loop

| Tier | Command | Catches |
|---|---|---|
| Static | `v3mod lint --ci` | brackets, typos, unknown references, missing loc, scope misuse, encoding |
| Structural | `v3mod check-overrides` | undeclared full-file overrides of vanilla |
| Behavioural | `v3mod test` | did the feature actually happen in a running game |
| Manual | `v3mod launch` | everything else; debug mode hotloads most files on save |

Useful in-game console commands during a manual session: `inspect_country <TAG>` opens a script
runner for evaluating triggers and effects interactively; `testevent`, `date`, `tag`, `observe`;
`Log.ClearErrorLog` to bracket a single action.
