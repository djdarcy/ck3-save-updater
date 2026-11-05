"""R27 house-feuds: 1.8's house-feud stories become 1.20 house relations at the feud level, scored -0.9."""

from __future__ import annotations

from ck3_save_migrator import savefile as sf
from ck3_save_migrator.rules import REGISTRY, RuleContext
from tests.fixtures.make_ck3 import build_ck3

R27 = next(r for r in REGISTRY if r.id == "R27")
META = b'meta_data={\n\tsave_game_version=8\n\tversion="1.8.1"\n}\n'
PEOPLE = b"living={\n10={\n\tfirst_name=\"Jutta\"\n\tdynasty_house=4316\n}\n11={\n\tfirst_name=\"Ngodup\"\n\tdynasty_house=3981\n}\n}\n"


def story(sid, owner, rival):
    return (b"\t\t%d={\n\t\t\tstory_cycle=\"story_cycle_house_feud\"\n\t\t\towner=%d\n\t\t\tvariables={\n"
            b"\t\t\t\tdata={ {\n\t\t\t\t\t\tflag=\"house_feud_house\"\n\t\t\t\t\t\tdata={\n\t\t\t\t\t\t\ttype=dyn_house\n"
            b"\t\t\t\t\t\t\tidentity=%d\n\t\t\t\t\t\t}\n\t\t\t\t\t}\n }\n\t\t\t}\n\t\t}\n" % (sid, owner, rival))


STORIES = b"stories={\n\tactive={\n" + story(1, 10, 1633) + story(2, 11, 3974) + b"\t}\n}\n"


def run(body):
    save = sf.parse_save(build_ck3(meta=META, body=body))
    res = R27.run(save, RuleContext())
    return save, res


def test_each_feud_becomes_a_relation_at_the_feud_level_deep_in_it():
    save, res = run(PEOPLE + STORIES)
    g = save.gamestate
    assert b"house_relations={\n\tdatabase={\n" in g
    assert b"houses={ 4316 1633 }" in g and b"houses={ 3981 3974 }" in g
    assert g.count(b"level=default_house_relation_level_feud") == 2 and g.count(b"fraction=-0.9") == 2
    assert (res.matched, res.edited) == (2, 2)


def test_an_existing_relation_between_the_houses_is_left_as_it_is():
    hr = (b"house_relations={\n\tdatabase={\n\t\t7={\n\t\t\thouses={ 1633 4316 }\n\t\t\ttype=default_house_relation\n"
          b"\t\t\tlevel=default_house_relation_level_neutral\n\t\t\tfraction=0.1\n\t\t}\n\t}\n}\n")
    save, res = run(PEOPLE + STORIES + hr)
    g = save.gamestate
    assert g.count(b"house_relations={") == 1 and b"\t\t8={\n\t\t\thouses={ 3981 3974 }" in g
    assert b"houses={ 4316 1633 }" not in g and res.edited == 1


def test_running_twice_adds_nothing_more():
    save, _ = run(PEOPLE + STORIES)
    once = save.gamestate
    res = R27.run(save, RuleContext())
    assert save.gamestate == once and res.edited == 0


def test_a_save_without_feuds_is_untouched():
    save, res = run(PEOPLE)
    assert b"house_relations" not in save.gamestate and res.matched == 0
