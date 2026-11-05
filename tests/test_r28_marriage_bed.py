"""R28 marriage-bed: 1.8's rejected_from_marriage_bed_modifier becomes 1.20's wedding_very_bad_fertility relation
with each living spouse, stored both ways; the modifier the game no longer defines is removed."""

from __future__ import annotations

from ck3_save_migrator import savefile as sf
from ck3_save_migrator.rules import REGISTRY, RuleContext
from tests.fixtures.make_ck3 import build_ck3

R28 = next(r for r in REGISTRY if r.id == "R28")
META = b'meta_data={\n\tsave_game_version=8\n\tversion="1.8.1"\n}\n'
BED = (b'\talive_data={\n\t\tgold=3\n\t\tmodifier={\n\t\t\tmodifier="rejected_from_marriage_bed_modifier"\n'
       b"\t\t\texpiration_date=9999.1.1\n\t\t}\n\t}\n")


def person(cid, spouses=(), bed=False):
    fam = b"".join(b"\t\tspouse=%d\n" % s for s in spouses)
    return (b"%d={\n\tfirst_name=\"P%d\"\n" % (cid, cid) + (b"\tfamily_data={\n" + fam + b"\t}\n" if fam else b"")
            + (BED if bed else b"") + b"}\n")


# 10 rejected, married to 11 (alive) and 12 (dead); 20 rejected, unmarried; 11 and 10 already have an opinion entry
LIVING = b"living={\n" + person(10, (11, 12), bed=True) + person(11, (10,)) + person(20, bed=True) + b"}\n"
DEAD = b"dead_unprunable={\n12={\n\tfirst_name=\"P12\"\n}\n}\n"
OPINIONS = (b"opinions={\n\tactive_opinions={ {\n\t\t\towner=11\n\t\t\ttarget=10\n\t\t\tscripted_relations={\n"
            b'\t\t\t\tfriend={\n\t\t\t\t\tflags="AA=="\n\t\t\t\t}\n\n\t\t\t}\n\t\t}\n}\n}\n')


def run(body):
    save = sf.parse_save(build_ck3(meta=META, body=body))
    return save, R28.run(save, RuleContext())


def test_the_living_spouse_gets_the_relation_both_ways_and_the_modifier_goes():
    save, res = run(LIVING + DEAD + OPINIONS)
    g = save.gamestate
    assert b"rejected_from_marriage_bed_modifier" not in g
    assert g.count(b"wedding_very_bad_fertility={") == 2
    # 11 -> 10 joins the existing entry's scripted_relations; 10 -> 11 is a new entry
    assert b"target=10\n\t\t\tscripted_relations={\n\t\t\t\twedding_very_bad_fertility={" in g
    assert b"owner=10\n\t\t\ttarget=11\n\t\t\tscripted_relations={\n\t\t\t\twedding_very_bad_fertility={" in g
    assert b"target=12" not in g                                  # the dead spouse gets nothing
    assert (res.matched, res.edited) == (2, 2)                     # 2 holders, 2 relation directions


def test_an_unmarried_holder_loses_only_the_modifier():
    save, res = run(b"living={\n" + person(20, bed=True) + b"}\n" + OPINIONS)
    g = save.gamestate
    assert b"rejected_from_marriage_bed_modifier" not in g and b"wedding_very_bad_fertility" not in g
    assert b"\talive_data={\n\t\tgold=3\n\t}\n" in g and (res.matched, res.edited) == (1, 0)


def test_running_twice_adds_nothing_more():
    save, _ = run(LIVING + DEAD + OPINIONS)
    once = save.gamestate
    res = R28.run(save, RuleContext())
    assert save.gamestate == once and res.matched == 0


def test_a_save_without_the_modifier_is_untouched():
    body = b"living={\n" + person(10, (11,)) + person(11, (10,)) + b"}\n" + OPINIONS
    save, res = run(body)
    assert b"wedding_very_bad_fertility" not in save.gamestate and res.matched == 0
