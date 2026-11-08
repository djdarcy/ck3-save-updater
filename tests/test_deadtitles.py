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


# --------------------------------------------------------------------------- R15's own check (0.5.0, U4)
MOVED_OLD = "c_a = { b_a = { province = 1 } }\nb_moved = { province = 6 }\n"
MOVED_NEW = "c_a = { b_a = { province = 1 } }\nb_moved = { province = 7 }\nb_here = { province = 6 }\n"
MOVED_SAVE = gamestate(titles=title(0, "c_a", "\tde_jure_vassals={ 1 }\n") + title(1, "b_a", "\tde_jure_liege=0\n")
                       + title(2, '"b_moved"', ""))


def game_dirs(tmp_path, old_map: str, new_map: str):
    """Two game folders, each with common/landed_titles, as R15's check and rule read them."""
    out = []
    for name, text in (("old", old_map), ("new", new_map)):
        d = tmp_path / name / "common" / "landed_titles"
        d.mkdir(parents=True)
        (d / "00_landed_titles.txt").write_text(text)
        out.append(tmp_path / name)
    return out


def test_r15s_check_sees_a_moved_barony_when_no_title_was_removed(tmp_path):
    """The latent skip (draft 2026.11.07_01): R6's report check counts only removed titles, so it says done here;
    R15's own check, its rule's matcher, says needed."""
    from ck3_save_migrator import detect
    old, new = game_dirs(tmp_path, MOVED_OLD, MOVED_NEW)
    env = detect.Env(game_dir=new, old_game_dir=old)
    assert detect._dead_titles(MOVED_SAVE, env).state == "done"           # the old shared check: the skip
    d = detect.detect("R15", MOVED_SAVE, env)                              # what status and update ask
    assert d.state == "needed" and d.count >= 1 and any("moved" in x for x in d.examples)


def test_r15s_check_is_done_when_the_maps_agree(tmp_path):
    from ck3_save_migrator import detect
    old, new = game_dirs(tmp_path, MOVED_NEW, MOVED_NEW)
    assert detect._r15(MOVED_SAVE, detect.Env(game_dir=new, old_game_dir=old)).state == "done"


def test_r15s_check_needs_the_old_game_folder(tmp_path):
    from ck3_save_migrator import detect
    _, new = game_dirs(tmp_path, MOVED_OLD, MOVED_NEW)
    d = detect._r15(MOVED_SAVE, detect.Env(game_dir=new))
    assert d.state == "unknown" and "--old-game-dir" in d.why


# --------------------------------------------------------------------------- the built-in old map (0.5.0, 2026-11-07)
# A names-only landed_titles table under known_titles/<folder>/ stands in for the old game when none is given
# (DWP 2026-11-07 19:52, built-in old-map table).
NOISY_OLD = ("# a game file, with what the table drops\n"
             "e_x = { color = { 1 2 3 } capital = c_a\n"
             "\tk_x = { cultural_names = { name_list_a = k_x_alt }\n"
             "\t\td_x = { c_a = { color = hsv { 0.1 0.2 0.3 } b_a = { province = 1 color = { 9 9 9 } }\n"
             "\t\t\tb_b = { province = 2 } } } } }\n"
             "b_moved = { province = 6 holding = castle_holding }\n")


def table(root, text: str, line: str = "1.8", name: str = "t1"):
    """A built-in old-map table folder, as scripts/title_table.py writes one."""
    d = root / name / "common" / "landed_titles"
    d.mkdir(parents=True)
    (d / "00_landed_titles.txt").write_text(text)
    (root / name / "table.toml").write_text(f'name = "Test"\nversion = "{line}.9"\ngame_line = "{line}"\n')
    return root


def title_table_script():
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "scripts" / "title_table.py"
    spec = importlib.util.spec_from_file_location("title_table", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_table_script_keeps_exactly_the_tree_r15_reads(tmp_path):
    """The written table reads back as the game's own tree (keys, nesting, provinces), and holds none of the rest."""
    game = tmp_path / "game" / "common" / "landed_titles"
    game.mkdir(parents=True)
    (game / "00_landed_titles.txt").write_text(NOISY_OLD)
    out = tmp_path / "known" / "test_1.8.9"
    assert title_table_script().main([str(tmp_path / "game"), str(out), "--version", "1.8.9", "--game-line", "1.8"]) == 0
    written = out / "common" / "landed_titles"
    assert D.title_tree(written) == D.title_tree(game)
    text = "".join(ln for ln in (written / "00_landed_titles.txt").read_text().splitlines(True)
                   if not ln.startswith("#"))
    assert not any(w in text for w in ("color", "capital", "cultural_names", "holding"))
    assert 'game_line = "1.8"' in (out / "table.toml").read_text()


def test_the_shipped_table_is_the_1_8_2_map():
    """Opt-in: runs where the 1.8.2 game files are on disk (private/data/versions/1.8.2)."""
    import pytest
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / "private" / "data" / "versions" / "1.8.2" / "game" / "common" / "landed_titles"
    if not src.is_dir():
        pytest.skip("the 1.8.2 game files are not on this machine")
    folder, label = D.old_map(None, "1.8.1")
    assert D.title_tree(folder) == D.title_tree(src) and "1.8.2" in label


def test_a_1_8_save_gets_the_built_in_table():
    folder, label = D.old_map(None, "1.8.1")
    assert folder is not None and folder.is_dir() and D.KNOWN_TITLES in folder.parents
    assert label.startswith("built-in table (") and "names only" in label


def test_a_given_old_game_wins_over_the_table(tmp_path):
    old, _ = game_dirs(tmp_path, MOVED_OLD, MOVED_NEW)
    folder, label = D.old_map(old, "1.8.1")
    assert folder == old / "common" / "landed_titles" and label.startswith("--old-game-dir")
    folder, label = D.old_map(tmp_path / "nowhere", "1.8.1")                # a wrong folder is not replaced by the table
    assert folder is None and "has no common/landed_titles" in label


def test_no_table_covers_a_save_on_another_line():
    for version in ("1.9.2", "1.12.5", None):
        folder, why = D.old_map(None, version)
        assert folder is None and "--old-game-dir" in why
    assert "a 1.9 save" in D.old_map(None, "1.9.2")[1]


def test_r15s_check_reads_the_table_when_no_old_game_is_given(tmp_path, monkeypatch):
    from ck3_save_migrator import detect
    _, new = game_dirs(tmp_path, MOVED_OLD, MOVED_NEW)
    monkeypatch.setattr(D, "KNOWN_TITLES", table(tmp_path / "known", MOVED_OLD))
    d = detect._r15(MOVED_SAVE, detect.Env(game_dir=new, save_version="1.8.1"))
    assert d.state == "needed" and any("moved" in x for x in d.examples)
    d = detect._r15(MOVED_SAVE, detect.Env(game_dir=new, save_version="1.9.2"))
    assert d.state == "unknown" and "a 1.9 save" in d.why


def test_r15_settles_titles_from_the_table_without_the_old_game(tmp_path, monkeypatch):
    """The rule itself: with no --old-game-dir, a 1.8 save's moved barony is renamed from the built-in map, and the
    result names that source."""
    from ck3_save_migrator import rules as R
    from ck3_save_migrator import savefile as sf
    from ck3_save_migrator.rules.transplant_1_20 import r15_dead_titles
    from tests.fixtures.make_ck3 import DEFAULT_META, build_ck3
    _, new = game_dirs(tmp_path, MOVED_OLD, MOVED_NEW)
    monkeypatch.setattr(D, "KNOWN_TITLES", table(tmp_path / "known", MOVED_OLD))
    save = sf.parse_save(build_ck3(meta=DEFAULT_META, body=MOVED_SAVE))
    rule = next(r for r in R.REGISTRY if r.id == "R15")
    res = r15_dead_titles(save, R.RuleContext(game_dir=new), rule)
    assert res.extra["old_map"].startswith("built-in table (Test 1.8.9")
    assert b'"b_here"' in save.gamestate or b"key=b_here" in save.gamestate


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


def test_county_records_follow_renames_and_removals(tmp_path):
    """county_manager/counties is keyed by the county's title KEY: a renamed county's record takes the new key, a
    removed county's record goes (census 2026-10-26: 11 records left under dead keys, 16 stale)."""
    save = SAVE + (b"county_manager={\n\tcounties={\n\t\tc_a={\n\t\t\tculture=1\n\t\t}\n"
                   b"\t\tc_split={\n\t\t\tculture=2\n\t\t}\n\t}\n}\n")
    old, new = dirs(tmp_path)
    ep = gs.EditPass()
    res = D.apply(save, D.classify(save, old, new), ep)
    out = ep.apply(save)
    b = gs.locate(out, "county_manager/counties")
    assert {e.key for e in gs.iter_entries(out, *b.body)} == {b"c_a2"}
    assert (res.county_records_renamed, res.county_records_removed) == (1, 1)
