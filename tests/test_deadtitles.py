"""Tests for R15's classifier and actions (deadtitles.py) on a tiny old and new map.

Old map: c_a (b_a on 1, b_b on 2), c_split (b_s1 on 3, b_s2 on 4), b_waste on 5, b_moved on 6.
New map: c_a2 (b_a2 on 1, b_b2 on 2) -- a clean rename of c_a; b_s1/b_s2's provinces split over c_x and c_y;
province 5 is wasteland; b_moved now sits on 7 and province 6 is b_here.
"""

from __future__ import annotations

from ck3_save_migrator import deadtitles as D
from ck3_save_migrator import gamestate as gs
from ck3_save_migrator import translate as T
from tests.test_translate import char, gamestate, title

OLD = ("c_a = { b_a = { province = 1 } b_b = { province = 2 } }\n"
       "c_split = { b_s1 = { province = 3 } b_s2 = { province = 4 } b_keep = { province = 8 } }\n"
       "b_waste = { province = 5 }\nb_moved = { province = 6 }\n")
NEW = ("c_a2 = { b_a2 = { province = 1 } b_b2 = { province = 2 } }\n"
       "c_x = { b_x = { province = 3 } b_keep = { province = 8 } }\nc_y = { b_y = { province = 4 } }\n"
       "b_moved = { province = 7 }\nb_here = { province = 6 }\n")
SAVE = gamestate(
    living=char(40, "\tlanded_data={\n\t\tdomain={ 0 4 5 }\n\t\trealm_capital=4\n\t}\n"),
    titles=title(0, "c_a", "\tholder=40\n\tde_jure_vassals={ 1 2 }\n\their={ 5 }\n")   # heir 5: a CHARACTER
    + title(1, "b_a", "\tde_jure_liege=0\n")
    + title(2, "b_b", "\tde_jure_liege=0\n") + title(4, "c_split", "\tholder=40\n\tde_jure_vassals={ 6 }\n")
    + title(5, "b_waste", "\tholder=40\n") + title(6, "b_s1", "\tde_jure_liege=4\n")
    + title(7, '"b_moved"', "") + title(8, "b_keep", "\tholder=40\n\tde_jure_liege=4\n"),
)


def dirs(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    old.mkdir()
    new.mkdir()
    (old / "00_landed_titles.txt").write_text(OLD)
    (new / "00_landed_titles.txt").write_text(NEW)
    return old, new


def test_classes(tmp_path):
    old, new = dirs(tmp_path)
    got = {m.key: (m.cls, m.successors) for m in D.classify(SAVE, old, new)}
    assert got["c_a"] == ("clean", ["c_a2"]) and got["b_a"] == ("clean", ["b_a2"])
    assert got["c_split"][0] == "unclean" and sorted(got["c_split"][1]) == ["c_x", "c_y"]
    assert got["b_s1"] == ("unclean", ["b_x"])          # its county is unclean: it goes with it
    assert got["b_waste"][0] == "wasteland"
    assert got["b_moved"] == ("clean", ["b_here"])      # place-faithful: renamed to the barony on its old province
    assert got["b_keep"] == ("unclean", ["b_keep"])     # still defined, but its county is removed: it goes too


def test_apply_renames_and_removes_with_references(tmp_path):
    old, new = dirs(tmp_path)
    maps = D.classify(SAVE, old, new)
    ep = gs.EditPass()
    res = D.apply(SAVE, maps, ep)
    out = ep.apply(SAVE)
    keys = {T._depth0(out, e, T._KEY).decode(): i for i, e in T.entries(out, "landed_titles/landed_titles")}
    assert keys == {"c_a2": 0, "b_a2": 1, "b_b2": 2, '"b_here"'.strip('"'): 7}   # ids kept, quotes kept
    assert b'key="b_here"' in out
    holder = dict(T.entries(out, "living"))[40]
    text = out[holder.start:holder.end]
    assert b"domain={ 0 }" in text and b"realm_capital" not in text           # removed titles leave the holder
    assert set(res.removed) == {"c_split", "b_waste", "b_s1", "b_keep"}
    c_a2 = dict(T.entries(out, "landed_titles/landed_titles"))[0]
    assert b"heir={ 5 }" in out[c_a2.start:c_a2.end]    # a title's heirs are characters: title 5's removal leaves them
