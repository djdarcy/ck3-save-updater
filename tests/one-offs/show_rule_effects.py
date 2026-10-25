"""Show what the unit-3 rules did to a few real entries, and summarise an R6 report.

Usage: python -I tests/one-offs/show_rule_effects.py <save.ck3> <report.json>
Runs R1-R5 in memory (writes nothing) and prints before/after of one title, one
opinion with converging + flags, and the game_rules lists; then R6's rows.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator.rules import RuleContext, run_rules, select  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402


def title(data: bytes, key: bytes) -> bytes:
    lt = gs.locate(data, "landed_titles/landed_titles")
    for t in gs.iter_entries(data, *lt.body):
        if b'key="' + key + b'"' in data[t.open:t.open + 200] or b"key=" + key + b"\n" in data[t.open:t.open + 200]:
            return data[t.start:t.end]
    return b"?"


def first_opinion_with(data: bytes, needle: bytes) -> tuple[bytes, bytes]:
    ao = gs.locate(data, "opinions/active_opinions")
    for e in gs.iter_entries(data, *ao.body):
        if needle in data[e.open:e.end]:
            owner = gs.find_keys(data, e, "owner")[0]
            target = gs.find_keys(data, e, "target")[0]
            return data[owner.value_start:owner.value_end] + b"/" + data[target.value_start:target.value_end], data[e.start:e.end]
    return b"?", b"?"


def opinion(data: bytes, pair: bytes) -> bytes:
    ao = gs.locate(data, "opinions/active_opinions")
    o, t = pair.split(b"/")
    for e in gs.iter_entries(data, *ao.body):
        body = data[e.open:e.end]
        if b"owner=" + o + b"\n" in body and b"target=" + t + b"\n" in body:
            return data[e.start:e.end]
    return b"?"


save = read_save(sys.argv[1])
before = save.gamestate
pair, op_before = first_opinion_with(before, b'flags="AQAAAA=="')
t_before = title(before, b"k_papal_state")
run_rules(save, select("R1,R2,R3,R4,R5"), RuleContext())
after = save.gamestate
print("== title k_papal_state, before\n" + t_before.decode(errors="replace")[:700])
print("== after\n" + title(after, b"k_papal_state").decode(errors="replace")[:700])
print(f"== opinion {pair.decode()} before\n" + op_before.decode(errors="replace")[:1200])
print("== after\n" + opinion(after, pair).decode(errors="replace")[:1200])
meta = gs.find_section(after, "meta_data")
gr = gs.find_child(after, meta, "game_rules")
print("== meta game_rules after: " + after[gr.open:gr.open + 160].decode())

rep = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
r6 = next(r for r in rep["rules"] if r["id"] == "R6")["extra"]
print(f"== R6: {len(r6['dead'])} dead, converted by game {r6['converted_by_game']}, templates {r6['game_title_templates']}")
held = [r for r in r6["dead"] if r.get("holder")]
print(f"   held by someone: {len(held)}; tiers: " +
      str({t: sum(1 for r in r6['dead'] if r['key'].startswith(t + '_')) for t in 'hekdcb'}))
for r in sorted(r6["dead"], key=lambda r: -r["refs_whole_token"])[:12]:
    print(f"   {r['id']:>6} {r['key']:24} holder={r.get('holder','-'):>9} dfl={r.get('de_facto_liege','-'):>6} "
          f"djl={r.get('de_jure_liege','-'):>6} refs={r['refs_whole_token']:>7,} keys={r['ref_keys']}")
