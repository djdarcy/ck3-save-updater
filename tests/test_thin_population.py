"""tests/one-offs/thin_population.py: a diagnostic that writes a copy of a save with fewer characters.

One synthetic save has every case: the player and their family, a title holder, house heads, spouses, an employer,
free commoners, dead characters mentioned from each kind of place, a dead_unprunable entry written twice (as 1.20
does), opinions, relations, memories, AI strategies, and a section the id schema does not know.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from ck3_save_migrator import gamestate as gs
from ck3_save_migrator import idschema as S
from ck3_save_migrator import savefile as sf
from ck3_save_migrator import translate as T
from ck3_save_migrator.lint import lint_gamestate
from tests.fixtures.make_ck3 import build_ck3

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("thin_population", ROOT / "tests" / "one-offs" / "thin_population.py")
TP = importlib.util.module_from_spec(_spec)
sys.modules["thin_population"] = TP                 # before it runs: its dataclasses look their module up there
_spec.loader.exec_module(TP)

META = b'meta_data={\n\tsave_game_version=18\n\tversion="1.20.1.2"\n}\n'


def char(cid: int, name: str, house: int, extra: str = "") -> str:
    return f'{cid}={{\n\tfirst_name="{name}"\n\tbirth=950.1.1\n\tdynasty_house={house}\n{extra}}}\n'


FREE = list(range(20, 30))                      # commoners nobody needs: the living-half pool
BODY = (
    "character_lookup={\n\t1001=10\n\t1060=60\n\t1061=61\n\t1080=80\n}\n"
    "played_character={\n\tname=\"player\"\n\tcharacter=10\n}\n"
    "currently_played_characters={ 10 }\n"
    "living={\n"
    + char(10, "Player", 100, "\tfamily_data={\n\t\tprimary_spouse=11\n\t\tspouse=11\n\t\tchild={ 12 }\n\t}\n")
    + char(11, "Wife", 101, "\tfamily_data={\n\t\tprimary_spouse=10\n\t\tspouse=10\n\t\tchild={ 12 }\n\t}\n")
    + char(12, "Heir", 100, "\tfamily_data={\n\t\treal_father=10\n\t}\n")
    + char(13, "Cousin", 100)                                                   # the player's house
    + char(14, "Widow", 102, "\tfamily_data={\n\t\tformer_spouses={ 81 }\n\t\treal_father=63\n\t}\n")
    + char(15, "Betrothed", 102, "\tfamily_data={\n\t\tbetrothed=16\n\t}\n")
    + char(16, "Promised", 102, "\tfamily_data={\n\t\tbetrothed=15\n\t}\n")
    + char(17, "Steward", 102, "\tcourt_data={\n\t\temployer=40\n\t}\n")
    + char(19, "Secret keeper", 102)                                            # named in an unknown section
    + "".join(char(c, f"Commoner{c}", 102,
                   (f"\tfamily_data={{\n\t\tchild={{ {c + 1} }}\n\t}}\n" if c == 20 else "")
                   + (f"\tfamily_data={{\n\t\treal_father=20\n\t}}\n" if c == 21 else "")
                   + "\tcourt_data={\n\t\temployer=40\n\t}\n")
              for c in FREE)
    + char(40, "Duke", 102, "\tplayable_data={\n\t\tknights={ 23 24 }\n\t}\n")
    + "}\n"
    "dead_unprunable={\n"
    + char(60, "Old duke", 102, "\tdead_data={\n\t\tdate=900.1.1\n\t\tliege=61\n\t}\n")   # a title's history
    + char(61, "Liege of the dead", 102, "\tdead_data={\n\t\tdate=899.1.1\n\t}\n")        # only the dead mention him
    + char(62, "Twice", 102) + char(62, "Twice", 102)                                     # written twice
    + char(63, "Father", 102, "\tdead_data={\n\t\tdate=930.1.1\n\t\tkills={ 61 }\n\t}\n")  # a living one's father
    + char(64, "Founder", 102)                                                            # house history
    + char(65, "Disliked", 102)                                                           # opinions only
    + char(66, "Keeper", 102)                                                             # an unknown section
    + "}\n"
    "characters={\n\tdead_prunable={\n"
    + char(80, "Pruned", 102) + char(81, "Late husband", 102)
    + "\t}\n}\n"
    "landed_titles={\n\tlanded_titles={\n"
    "500={\n\tkey=\"d_test\"\n\tholder=40\n\thistory={\n\t\t900.1.1=60\n\t\t950.1.1=81\n\t}\n}\n"
    "\t}\n}\n"
    "dynasties={\n\tdynasty_house={\n"
    "100={\n\tname=\"house\"\n\thead_of_house=10\n\tdynasty=200\n}\n"
    "101={\n\tname=\"other\"\n\thead_of_house=11\n\tdynasty=200\n}\n"
    "102={\n\tname=\"commons\"\n\thead_of_house=40\n\thistorical={ 64 40 }\n\tdynasty=201\n}\n"
    "\t}\n\tdynasties={\n200={\n\tdynasty_head=10\n}\n201={\n\tdynasty_head=40\n}\n\t}\n}\n"
    "opinions={\n\tactive_opinions={ {\n\t\towner=21\n\t\ttarget=40\n\t\tvalue=10\n\t}\n"
    " {\n\t\towner=40\n\t\ttarget=65\n\t\tvalue=-5\n\t}\n"
    " {\n\t\towner=40\n\t\ttarget=22\n\t\tvalue=-5\n\t}\n"
    " {\n\t\towner=10\n\t\ttarget=40\n\t\tvalue=3\n\t}\n\t}\n}\n"
    "relations={\n\tactive_relations={ {\n\t\tfirst=40\n\t\tsecond=25\n\t}\n {\n\t\tfirst=10\n\t\tsecond=40\n\t}\n\t}\n}\n"
    "character_memory_manager={\n\tdatabase={\n700={\n\ttype=x\n\tparticipants={\n\t\tvictim=26\n\t\twitness=40\n"
    "\t}\n}\n\t}\n}\n"
    "ai={\n\tai_strategies={\n27={\n\tx=1\n}\n40={\n\ty=2\n}\n\t}\n}\n"
    "secrets={\n\tsecrets={\n1={\n\towner=19\n\ttarget=66\n}\n\t}\n}\n"
).encode()

LIVING = {10, 11, 12, 13, 14, 15, 16, 17, 19, 40, *FREE}
# who living-half may remove: the commoners, the widow (no one's spouse now) and the steward (employed, employing
# no one); everyone else is the player, their family, betrothed, a title holder, or named in an unknown section
POOL = {14, 17, *FREE}


@pytest.fixture
def save(tmp_path) -> Path:
    p = tmp_path / "in.ck3"
    p.write_bytes(build_ck3(meta=META, body=BODY))
    return p


def thin(save: Path, mode: str, seed: int = 0, name: str = "out"):
    out = save.parent / f"{name}.ck3"
    rep = TP.run(save, out, mode, seed, say=lambda m: None)
    return rep, sf.read_save(out).gamestate


def char_ids(g: bytes, sec: str) -> set[int]:
    return {i for i, _ in T.entries(g, sec)}


def all_chars(g: bytes) -> set[int]:
    return set().union(*(char_ids(g, s) for s in S.SPACES["character"]))


def dangling(g: bytes) -> list:
    """Every character reference, by the id schema, to a character not in the save."""
    have = all_chars(g)
    out = []
    for kind in S.FIELDS:
        if kind == "character":
            continue
        try:
            blk = gs.locate(g, kind)
        except gs.GamestateError:
            continue
        for e in gs.iter_entries(g, *blk.body):
            for path, space, i in T.references(g, e, kind):
                if space == "character" and i not in have:
                    out.append((kind, path, i))
    return out


def test_the_input_is_clean():
    assert not dangling(BODY) and lint_gamestate(META + BODY, keys=False).errors == 0


def test_prunable_removes_every_dead_prunable_and_its_references(save):
    rep, g = thin(save, "prunable")
    assert char_ids(g, "characters/dead_prunable") == set()
    assert dict(rep.removed) == {"characters/dead_prunable": 2}
    assert char_ids(g, "living") == LIVING and char_ids(g, "dead_unprunable") == {60, 61, 62, 63, 64, 65, 66}
    assert b"former_spouses={ }" in g or b"former_spouses" not in g          # 81 left the widow's list
    assert b"950.1.1=81" not in g and b"1080=80" not in g
    assert not dangling(g) and rep.lint_errors == 0


def test_dead_keeps_the_dead_someone_still_needs(save):
    rep, g = thin(save, "dead")
    assert char_ids(g, "dead_unprunable") == {60, 63, 64, 66}
    # 60 a title's history, 63 a living one's father, 64 a house's history, 66 an unknown section (secrets)
    assert rep.removed["dead_unprunable"] == 3 and rep.removed["characters/dead_prunable"] == 2
    assert rep.kept == {"a title mentions them": 1, "a living character mentions them": 1,
                        "a house or dynasty mentions them": 1, "mentioned in secrets": 1}
    assert g.count(b"\n62={") == 0                                          # both copies of the repeated entry
    assert b"target=65" not in g and rep.deleted_records["opinions/active_opinions"] == 1
    assert b"liege=61" not in g and b"kills={ 61 }" not in g and b"1061=61" not in g
    assert not dangling(g) and rep.lint_errors == 0


def test_living_half_removes_half_of_the_free_and_keeps_everyone_needed(save):
    rep, g = thin(save, "living-half", seed=7)
    living = char_ids(g, "living")
    gone = LIVING - living
    assert len(gone) == len(POOL) // 2 == 6 and gone <= POOL
    for needed in (10, 11, 12, 13, 15, 16, 19, 40):      # player, wife, heir, cousin, betrothed pair, secrets, duke
        assert needed in living, needed
    assert rep.kept == {"the player": 1, "the player's family": 2,           # the heir and the cousin
                        "someone's primary_spouse": 1,                       # the wife (a spouse first)
                        "someone's betrothed": 2, "someone's employer": 1,    # the pair, the duke
                        "mentioned in secrets": 1}
    assert rep.removed == {"living": 6}
    assert not dangling(g) and rep.lint_errors == 0


def test_living_half_drops_the_references_of_those_it_removes(save):
    rep, g = thin(save, "living-half", seed=7)
    gone = LIVING - char_ids(g, "living")
    for c in gone:
        assert f"owner={c}\n".encode() not in g and f"target={c}\n".encode() not in g
        assert f"second={c}\n".encode() not in g and f"\n{c}={{\n\tx=1".encode() not in g
        assert f"victim={c}\n".encode() not in g
    knights = g[g.find(b"knights={"):g.find(b"}", g.find(b"knights={"))]
    assert not any(str(c).encode() in knights.split() for c in gone)


def test_living_half_is_deterministic_by_seed(save):
    a = thin(save, "living-half", seed=3, name="a")[1]
    b = thin(save, "living-half", seed=3, name="b")[1]
    c = thin(save, "living-half", seed=4, name="c")[1]
    assert a == b
    assert char_ids(a, "living") != char_ids(c, "living")


def test_it_never_writes_in_place_or_over_an_existing_file(save):
    with pytest.raises(sf.OutputExistsError):
        TP.run(save, save, "prunable", say=lambda m: None)
    other = save.parent / "exists.ck3"
    other.write_bytes(b"keep me")
    with pytest.raises(sf.OutputExistsError):
        TP.run(save, other, "prunable", say=lambda m: None)
    assert other.read_bytes() == b"keep me"


def test_the_counts_are_printed(save):
    lines = []
    TP.run(save, save.parent / "o.ck3", "dead", say=lines.append)
    text = "\n".join(lines)
    assert "mode dead: 5 characters removed" in text and "removed from dead_unprunable: 3" in text
    assert "records deleted whole, opinions/active_opinions: 1" in text and "lint: 0 error(s)" in text
