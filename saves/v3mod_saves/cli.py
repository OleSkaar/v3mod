"""`v3mod-save` — look inside a plaintext Victoria 3 save.

  v3mod-save setup                            install the jomini parser (done on first use anyway)
  v3mod-save SAVE plays [INI [TGT]]           diplomatic plays: type, region, dates, sides, war goals
  v3mod-save SAVE involvement TAG[,TAG] [REGION_SUBSTR...]   interest involvement per strategic region
  v3mod-save SAVE states STATE_A[,STATE_B]    owner of each state region
  v3mod-save SAVE pacts TAG                   pacts (subject, alliance, defensive pact, ...) of a country
  v3mod-save SAVE strategies TAG[,TAG]        the AI strategies a country holds
  v3mod-save SAVE techs TAG[,TAG] [TECH...]   researched technologies (all, or the named ones as yes/no)
  v3mod-save SAVE movements TAG[,TAG]         political movements with their radicalism
  v3mod-save SAVE civil-wars                  every civil war: country, type, progress, capital state
  v3mod-save SAVE globals [SUBSTR]            global variables (names)
  v3mod-save SAVE get /path [/path...]        raw JSON for save paths (one parse for all of them)

Saves are plaintext only (TEST_FAIL_* saves from scripted tests, or -debug_mode saves).
"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .save import Save, ensure_parser, cache_dir


def _tags(s: str) -> list[str]:
    return [t for t in s.split(",") if t]


def cmd_plays(s: Save, a: list[str]) -> None:
    goals = s.get("/war_goal_manager/database")
    states = s.state_regions()
    ini, tgt = (a + [None, None])[:2]
    for pid, p in s.plays(ini, tgt):
        if not ini and str(p.get("type", "")).startswith("dp_native"):
            continue
        print(f"PLAY {p.get('type')} {s.tag(p.get('initiator'))} -> {s.tag(p.get('target'))} "
              f"{p.get('strategic_region', '?')} start {str(p.get('start_date'))[:10]} "
              f"end {str(p.get('end_date'))[:10]} war={p.get('war')} escalation={p.get('escalation')}")
        print("   sides: " + ", ".join(f"{t}:{sd[0]}" for t, sd in s.sides(p)))
        for gid, g in goals.items():
            if not isinstance(g, dict) or str(g.get("diplomatic_play")) != str(pid):
                continue
            t = g.get("target", {}) or {}
            print(f"   {s.tag(g.get('holder')):4s} {str(g.get('type')):22s} vs {s.tag(t.get('country')):4s} "
                  f"{states.get(str(t.get('state')), '-'):20s} {g.get('demand_type', '')} {g.get('status', '')} "
                  f"initial={g.get('initial_war_goal', '')} progress={g.get('enforcement_progress', '')}")


def cmd_involvement(s: Save, a: list[str]) -> None:
    db = s.get("/interest_manager/database")
    want, regs = _tags(a[0]), a[1:]
    rows: dict[str, list[tuple[str, float]]] = {}
    for v in db.values():
        if isinstance(v, dict):
            rows.setdefault(s.tag(v.get("country")), []).append(
                (str(v.get("strategic_region", "")).replace("region_", ""), float(v.get("current_involvement", 0) or 0)))
    for t in want:
        print(t + ": " + ", ".join(f"{r} {i:.0f}" for r, i in sorted(rows.get(t, []), key=lambda x: -x[1])
                                   if not regs or any(k in r for k in regs)))


def cmd_states(s: Save, a: list[str]) -> None:
    want = set(_tags(a[0]))
    for v in s.get("/states/database").values():
        if isinstance(v, dict) and v.get("region") in want:
            print(f"  {v['region']:22s} {s.tag(v.get('country'))}")


def cmd_pacts(s: Save, a: list[str]) -> None:
    for v in s.get("/pacts/database").values():
        if not isinstance(v, dict):
            continue
        t = v.get("targets", {}) if isinstance(v.get("targets"), dict) else {}
        first, second = s.tag(v.get("first", t.get("first"))), s.tag(v.get("second", t.get("second")))
        if a[0] in (first, second):
            print(f"  {first} - {second}: {v.get('action') or v.get('type')}")


def cmd_strategies(s: Save, a: list[str]) -> None:
    db = s.get("/ai/database")
    by_country = {str(v.get("country")): v for v in db.values() if isinstance(v, dict)}
    for t in _tags(a[0]):
        strats = by_country.get(s.id_of(t) or "", {}).get("ai_strategy") or []
        if isinstance(strats, dict):
            strats = [strats]
        print(f"  {t}: " + ", ".join(x.get("type", "?") for x in strats))


def _tech_records(s: Save) -> dict[str, dict]:
    db = s.get("/technology/database")
    return {str(v["country"]): v for v in db.values() if isinstance(v, dict) and "country" in v}


def cmd_techs(s: Save, a: list[str]) -> None:
    rec = _tech_records(s)
    want = a[1:]
    for t in _tags(a[0]):
        v = rec.get(s.id_of(t) or "")
        if not v:
            print(f"  {t}: -")
            continue
        got = set(v.get("acquired_technologies", []))
        if want:
            print(f"  {t}: " + "  ".join(f"{w}={'yes' if w in got else 'no'}" for w in want)
                  + f"   researching {v.get('research_technology', '-')}")
        else:
            print(f"  {t} ({len(got)}): " + " ".join(sorted(got)) + f"\n     researching {v.get('research_technology', '-')}")


def cmd_movements(s: Save, a: list[str]) -> None:
    db = s.get("/political_movement_manager/database")
    for t in _tags(a[0]):
        cid = s.id_of(t)
        ms = [(str((m.get("identity") or {}).get("type", "?")).replace("movement_", ""), float(m.get("radicalism", 0) or 0))
              for m in db.values() if isinstance(m, dict) and str(m.get("country")) == cid]
        print(f"  {t}: " + ", ".join(f"{n} {r:.2f}" for n, r in sorted(ms, key=lambda x: -x[1])))


def cmd_civil_wars(s: Save, a: list[str]) -> None:
    movements = s.get("/political_movement_manager/database")
    for v in s.get("/civil_war/database").values():
        if not isinstance(v, dict):
            continue
        m = movements.get(str(v.get("political_movement")), {}) if isinstance(movements, dict) else {}
        mt = str((m.get("identity") or {}).get("type", "?")).replace("movement_", "") if isinstance(m, dict) else "?"
        print(f"  {s.tag(v.get('origin_country')):4s} {v.get('type'):10s} {float(v.get('progress', 0) or 0):5.2f} "
              f"{mt:24s} capital {v.get('capital', '-')}")


def cmd_globals(s: Save, a: list[str]) -> None:
    v = s.get("/variables")
    names: list[str] = []
    if isinstance(v, dict):
        data = v.get("data", v)
        if isinstance(data, dict):
            names = [k for k in data.keys()] if all(isinstance(x, str) for x in data.keys()) else \
                    [str(d.get("flag", d.get("name", ""))) for d in data.values() if isinstance(d, dict)]
        elif isinstance(data, list):
            names = [str(d.get("flag", d.get("name", ""))) for d in data if isinstance(d, dict)]
    sub = a[0] if a else ""
    for n in sorted(names):
        if sub in n:
            print("  " + n)


def cmd_get(s: Save, a: list[str]) -> None:
    print(json.dumps(s.get(*a), indent=1)[:200000])


COMMANDS = {
    "plays": (cmd_plays, 0), "involvement": (cmd_involvement, 1), "states": (cmd_states, 1),
    "pacts": (cmd_pacts, 1), "strategies": (cmd_strategies, 1), "techs": (cmd_techs, 1),
    "movements": (cmd_movements, 1), "civil-wars": (cmd_civil_wars, 0), "globals": (cmd_globals, 0),
    "get": (cmd_get, 1),
}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="v3mod-save", description=__doc__.split("\n\n")[0],
                                epilog=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"v3mod-save {__version__}")
    p.add_argument("save", help="plaintext .v3 save, or 'setup'")
    p.add_argument("command", nargs="?", choices=sorted(COMMANDS))
    p.add_argument("args", nargs="*")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.save == "setup":
            print(f"parser ready: {ensure_parser()} (cache {cache_dir()})")
            return 0
        if not args.command:
            print("error: a command is required", file=sys.stderr)
            return 2
        fn, min_args = COMMANDS[args.command]
        if len(args.args) < min_args:
            print(f"error: {args.command} needs {min_args} argument(s); see --help", file=sys.stderr)
            return 2
        fn(Save(args.save), args.args)
        return 0
    except KeyboardInterrupt:
        print("\naborted")
        return 130
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    sys.exit(main())
