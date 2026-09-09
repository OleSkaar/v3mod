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
```

What happens: the game launches with no window and auto-starts an AI-only game; the base game's own
scripted tests are hidden for the run (they have `last_date` up to 1936 and would gate the results
file); `<user data>/tests.txt` is polled until the engine writes `[ OK ]` / `[ FAIL ]` lines; the
process group is stopped; results and any `TEST_FAIL_*.v3` saves are copied to
`framework/test-output/<timestamp>/`. Exit code is 1 if any test failed.

**First run on a machine:** the binary must have been started directly once (`v3mod launch`) or no
DLCs load in hands-off runs.

If no results appear, check `error.log` — `v3mod-errors --tail 40` if that optional add-on is
installed, otherwise `tail -40 "$(v3mod paths | awk '/^logs/{$1=""; print substr($0,2)}')/error.log"`.
The usual causes are a script error preventing load, or the mod not being in the active playset
(`v3mod playset show`).

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
