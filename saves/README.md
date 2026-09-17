# v3mod-saves

`v3mod-save`: look inside a plaintext Victoria 3 save. Optional add-on for [v3mod](../README.md).

```bash
pipx install --editable ./saves    # from the root of this repo; needs node and npm on PATH
v3mod-save setup                   # installs the jomini parser into ~/.cache/v3mod/pdxq (also done on first use)
```

Saves must be plaintext: the `TEST_FAIL_*.v3` saves scripted tests write are, and so is any save made
with `-debug_mode`. Normal saves are binary and are not supported.

```
v3mod-save SAVE plays [INI [TGT]]           diplomatic plays: type, region, dates, sides, war goals
v3mod-save SAVE involvement TAG[,TAG] [REGION_SUBSTR...]   interest involvement per strategic region
v3mod-save SAVE states STATE_A[,STATE_B]    owner of each state region
v3mod-save SAVE pacts TAG                   pacts (subject, alliance, defensive pact, ...) of a country
v3mod-save SAVE strategies TAG[,TAG]        the AI strategies a country holds
v3mod-save SAVE techs TAG[,TAG] [TECH...]   researched technologies (all, or the named ones as yes/no)
v3mod-save SAVE movements TAG[,TAG]         political movements with their radicalism
v3mod-save SAVE civil-wars                  every civil war: country, type, progress, capital state
v3mod-save SAVE globals [SUBSTR]            global variable names
v3mod-save SAVE get /path [/path...]        raw JSON for save paths (one parse for all of them)
```

From Python:

```python
from v3mod_saves import Save
s = Save("TEST_FAIL_my_marker_1 January, 1848.v3")
s.get("/meta_data/game_date")
db = s.get("/technology/database")      # 200-400 MB files: ask for every path you need in one call
s.tag(95), s.id_of("TUR"), s.plays(initiator="TUR"), s.sides(play), s.state_regions()
```

Why jomini: Paradox's save grammar has quirks (duplicate keys, `{ }` lists of scalars, dates, RGB
blocks) that regexes and generic parsers get wrong on a 300 MB file; [jomini](https://github.com/rakaly/jomini)
is the maintained Rust parser with a WASM build, and node is the only runtime it needs. The query
script (`js/pdxq.mjs`) parses once and pulls the requested paths, so the cost is one parse per
`get()` call, about 10–20 s for a late-game save.
