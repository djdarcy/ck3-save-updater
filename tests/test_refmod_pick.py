"""reference-mod picks its ruler from the game's history files, and writes the bookmark with a byte-order mark.

A tiny fake ``game/history`` holds, on 987.10.27: a ruler alive and holding (900); one dead before the date (901);
one not yet born (902); a duchy that changed hands before the date (from 903 to 904, who also changed faith and
took a tribal government); a child holding a kingdom (905); a ruler whose history has no dynasty house (906); a
count (907); and a county its holder gave up. The last test runs on the real game files when CK3SM_REAL_GAME_DIR names them."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ck3_save_migrator import cli
from ck3_save_migrator import history as H
from ck3_save_migrator import refmod as M
from tests.fixtures.make_ck3 import build_ck3
from tests.fixtures.religion import OLD_BODY, OLD_META

CHARACTERS = """# characters, as the game writes them
900 = {
\tname = "Brian"
\tdynasty_house = house_british_isles_briain
\treligion = "insular_celtic"
\tculture = "irish"
\t941.1.1 = { birth = yes }
\t1014.4.23 = { death = { death_reason = death_battle killer = 999 } }
}
901 = {
\tname = "Old" dynasty_house = house_old religion = catholic culture = french
\t900.1.1 = { birth = yes }
\t980.1.1 = { death = yes }
}
902 = {
\tname = "Later" dynasty_house = house_later religion = catholic culture = french
\t990.1.1 = { birth = yes }
}
903 = {
\tname = "Mael" dynasty_house = house_leinster religion = insular_celtic culture = irish
\t930.1.1 = { birth = yes }
}
904 = {
\tname = "Donn" female = yes dynasty_house = house_leinster religion = insular_celtic culture = irish
\t960.1.1 = { birth = yes }
\t985.1.1 = { religion = catholic effect = { add_gold = 5 } }
\t990.1.1 = { culture = norse }
}
905 = {
\tname = "Child" dynasty_house = house_child religion = catholic culture = french
\t980.1.1 = { birth = yes }
}
906 = {
\tname = "Nohouse" dynasty = 77 religion = catholic culture = french
\t940.1.1 = { birth = yes }
}
907 = {
\tname = "Count" dynasty_house = house_count religion = catholic culture = french
\t940.1.1 = { birth = yes }
}
"""

TITLES = """d_munster = {
\t970.1.1 = { holder = 900 }
}
d_leinster = {
\t950.1.1 = { holder = 903 }
\t985.1.1 = { holder = 904 government = tribal_government }
}
d_dead = {
\t950.1.1 = { holder = 901 }
}
d_unborn = {
\t990.1.1 = { holder = 902 }
}
k_child = {
\t985.1.1 = { holder = 905 }
}
k_nohouse = {
\t985.1.1 = { holder = 906 }
}
c_cashel = {
\t950.1.1 = { holder = 907 }
}
c_given_up = {
\t950.1.1 = { holder = 900 }
\t980.1.1 = { holder = 0 }
}
"""


@pytest.fixture
def game(tmp_path) -> Path:
    g = tmp_path / "game"
    for sub, name, text in (("characters", "00_test.txt", CHARACTERS), ("titles", "00_test.txt", TITLES)):
        (g / "history" / sub).mkdir(parents=True)
        (g / "history" / sub / name).write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))
    (g / "common" / "landed_titles").mkdir(parents=True)
    return g


DATE = (987, 10, 27)


# --------------------------------------------------------------------------- the history reader
def test_characters_are_read_with_birth_death_and_dated_changes(game):
    chars = H.characters(game / "history" / "characters")
    assert chars["900"].birth == (941, 1, 1) and chars["900"].death == (1014, 4, 23)
    assert chars["900"].alive_on(DATE) and not chars["901"].alive_on(DATE) and not chars["902"].alive_on(DATE)
    now = chars["904"].as_of(DATE)
    assert now["religion"] == "catholic" and now["culture"] == "irish"      # 985 changed faith; 990 is later
    assert chars["905"].age_on(DATE) == 7


def test_title_holders_on_a_date(game):
    held = H.holders(H.titles(game / "history" / "titles"), DATE)
    assert held == {"900": ["d_munster"], "904": ["d_leinster"], "901": ["d_dead"], "905": ["k_child"],
                    "906": ["k_nohouse"], "907": ["c_cashel"]}


def test_the_reader_keeps_what_it_read_from_an_unbalanced_file():
    assert H.parse('a = { b = "c d" # x\n e = { f } ') == [("a", [("b", "c d"), ("e", [(None, "f")])])]


# --------------------------------------------------------------------------- picking
def test_the_pick_is_an_adult_living_holder_with_every_field_known(game):
    p = M.pick_ruler(game, "987.10.27")
    # 900 and 904 both qualify with a duchy; d_leinster sorts first; 905 is a child, 906 has no house, 907 holds
    # only a county (whose key sorts before both duchies)
    assert (p.character, p.title) == ("904", "d_leinster")
    assert (p.culture, p.religion, p.house, p.birth) == ("irish", "catholic", "house_leinster", "960.1.1")
    assert p.female and p.name == "Donn" and p.government == "tribal_government"
    assert "alive and holding d_leinster on 987.10.27" in p.why


def test_before_the_title_changed_hands_the_earlier_holder_is_picked(game):
    p = M.pick_ruler(game, "984.1.1")
    assert (p.character, p.title) == ("903", "d_leinster") and p.government == "feudal_government"


def test_a_given_character_is_checked_and_filled_in(game):
    p = M.pick_ruler(game, "987.10.27", character="900")
    assert (p.title, p.culture, p.religion, p.house, p.birth, p.female) == (
        "d_munster", "irish", "insular_celtic", "house_british_isles_briain", "941.1.1", False)
    with pytest.raises(M.RefModError, match="901 is not alive"):
        M.pick_ruler(game, "987.10.27", character="901")
    with pytest.raises(M.RefModError, match="902 is not alive"):
        M.pick_ruler(game, "987.10.27", character="902")
    with pytest.raises(M.RefModError, match="903 holds no title"):
        M.pick_ruler(game, "987.10.27", character="903")


def test_nobody_to_pick_and_no_history(game, tmp_path):
    with pytest.raises(M.RefModError, match="no character .* alive and holds a title on 800.1.1"):
        M.pick_ruler(game, "800.1.1")
    with pytest.raises(M.RefModError, match="no history folders"):
        M.pick_ruler(tmp_path / "empty", "987.10.27")


# --------------------------------------------------------------------------- the command
def bookmark_text(out: Path) -> bytes:
    return (out / "zz_ref_987_10_27" / "common" / "bookmarks" / "bookmarks" / "zz_ref.txt").read_bytes()


def test_the_command_with_only_a_date_picks_and_says_why(game, tmp_path, capsys):
    out = tmp_path / "mods"
    out.mkdir()
    assert cli.main(["reference-mod", "--date", "987.10.27", "--game-dir", str(game), "--out", str(out)]) == 0
    said = capsys.readouterr().out
    assert "ruler: character 904 (Donn), d_leinster: alive and holding d_leinster" in said
    t = bookmark_text(out).decode("utf-8-sig")
    for line in ("history_id = 904", "title = d_leinster", "culture = irish", "religion = catholic",
                 "government = tribal_government", "birth = 960.1.1", "type = female",
                 "dynasty_house = house_leinster"):
        assert f"\t\t{line}\n" in t, line


def test_the_date_can_come_from_a_save(game, tmp_path, capsys):
    save = tmp_path / "old.ck3"
    save.write_bytes(build_ck3(meta=OLD_META, body=OLD_BODY))                # meta_date=987.10.27
    out = tmp_path / "mods"
    out.mkdir()
    assert cli.main(["reference-mod", "--save", str(save), "--game-dir", str(game), "--out", str(out)]) == 0
    assert b"start_date = 987.10.27" in bookmark_text(out)
    assert cli.main(["reference-mod", "--save", str(save), "--date", "987.10.27", "--out", str(out)]) == 1
    assert "one of the two" in capsys.readouterr().err


def test_explicit_flags_override_what_the_history_says(game, tmp_path, capsys):
    out = tmp_path / "mods"
    out.mkdir()
    assert cli.main(["reference-mod", "--date", "987.10.27", "--game-dir", str(game), "--character", "900",
                     "--culture", "norse", "--government", "clan_government", "--out", str(out)]) == 0
    t = bookmark_text(out).decode("utf-8-sig")
    assert "\t\thistory_id = 900\n" in t and "\t\tculture = norse\n" in t and "clan_government" in t
    assert "\t\treligion = insular_celtic\n" in t                               # still from the history
    assert "--culture" in capsys.readouterr().out


def test_without_a_game_folder_every_ruler_flag_is_needed(tmp_path, capsys):
    out = tmp_path / "mods"
    out.mkdir()
    assert cli.main(["reference-mod", "--date", "987.10.27", "--out", str(out)]) == 1      # CK3_GAME_DIR=none
    assert "--character" in capsys.readouterr().err and not any(out.iterdir())


def test_the_bookmark_file_is_written_with_a_byte_order_mark(tmp_path):
    b = M.make_bookmark(date="987.10.27", character=900, title="d_munster", culture="irish",
                        religion="insular_celtic", house="house_british_isles_briain", birth="941.1.1")
    M.write_mod(b, tmp_path)
    assert bookmark_text(tmp_path)[:3] == b"\xef\xbb\xbf"


# --------------------------------------------------------------------------- 1.20's own shapes
# Measured on the real 1.20 history (2026-10-30): the faith is `rite = ...` (no `religion =` or `faith =` at all),
# most characters name a numeric `dynasty = <id>` and no dynasty_house, the house key comes from
# common/dynasty_houses, and the birth is a dated block `<date> = { birth = "<date>" }`.
CHARACTERS_120 = """900 = {
\tname = "Brian"
\tdynasty = 100009 #Dál gCais
\trite = insular_celtic
\tculture = "irish"
\t941.1.1 = {
\t\tbirth = "941.1.1"
\t}
\t1014.4.23 = {
\t\tdeath = { death_reason = death_battle }
\t}
}
910 = {
\tname = "Branch" dynasty = 200 rite = catholic culture = french
\t940.1.1 = { birth = "940.1.1" }
}
911 = {
\tname = "Housless" dynasty = 999 rite = catholic culture = french
\t940.1.1 = { birth = "940.1.1" }
}
912 = {
\tname = "Older" dynasty = 300 religion = catholic culture = french
\t940.1.1 = { birth = "940.1.1" }
}
"""
TITLES_120 = """d_munster = {
\t978.7.1 = { holder = 900 }
}
c_branch = {
\t975.1.1 = { holder = 910 }
}
c_older = {
\t975.1.1 = { holder = 912 }
}
k_housless = {
\t950.1.1 = { holder = 911 }
}
"""
HOUSES_120 = """house_british_isles_briain = {
\tname = "dynn_Briain"
\tdynasty = 100009
\tmotto = dynn_Briain_motto
}
house_cadet_200 = { name = "dynn_cadet" dynasty = 200 parent_house = house_main_200 }
house_main_200 = { name = "dynn_main" dynasty = 200 }
house_first_300 = { name = "dynn_a" dynasty = 300 }
house_second_300 = { name = "dynn_b" dynasty = 300 }
"""


@pytest.fixture
def game120(tmp_path) -> Path:
    g = tmp_path / "game120"
    for sub, text in (("history/characters", CHARACTERS_120), ("history/titles", TITLES_120),
                      ("common/dynasty_houses", HOUSES_120)):
        (g / sub).mkdir(parents=True)
        (g / sub / "00_test.txt").write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))
    (g / "common" / "landed_titles").mkdir(parents=True)
    return g


def test_on_1_20_shapes_the_faith_is_the_rite_and_the_house_comes_from_the_dynasty(game120):
    p = M.pick_ruler(game120, "987.10.27")
    assert (p.character, p.title, p.culture, p.religion, p.house, p.birth) == (
        "900", "d_munster", "irish", "insular_celtic", "house_british_isles_briain", "941.1.1")
    assert "the house of dynasty 100009" in p.why


def test_a_dynastys_main_house_is_its_first_that_is_not_a_cadet_branch_else_its_first(game120):
    p = M.pick_ruler(game120, "987.10.27", character="910")
    assert p.house == "house_main_200" and "not a cadet branch" in p.why
    p = M.pick_ruler(game120, "987.10.27", character="912")
    assert p.house == "house_first_300" and "first of dynasty 300's 2 houses defined" in p.why
    assert p.religion == "catholic"                       # an older game's `religion =` is still read


def test_an_incomplete_ruler_is_never_picked(game120, tmp_path, capsys):
    # on 960.1.1 the only living title holder is 911, whose dynasty has no house
    with pytest.raises(M.RefModError, match=r"none of the 1 living title holders.*911 holding k_housless.*no house"):
        M.pick_ruler(game120, "960.1.1")
    out = tmp_path / "mods"
    out.mkdir()
    assert cli.main(["reference-mod", "--date", "960.1.1", "--game-dir", str(game120), "--out", str(out)]) == 1
    assert "no house" in capsys.readouterr().err and not any(out.iterdir())


def test_the_command_on_1_20_shapes_writes_brians_bookmark(game120, tmp_path):
    out = tmp_path / "mods"
    out.mkdir()
    assert cli.main(["reference-mod", "--date", "987.10.27", "--game-dir", str(game120), "--out", str(out)]) == 0
    t = bookmark_text(out).decode("utf-8-sig")
    for line in ("history_id = 900", "title = d_munster", "culture = irish", "religion = insular_celtic",
                 "dynasty_house = house_british_isles_briain", "birth = 941.1.1", "type = male"):
        assert f"\t\t{line}\n" in t, line


# --------------------------------------------------------------------------- the real game, where it is installed
@pytest.mark.skipif(not os.environ.get("CK3SM_REAL_GAME_DIR"), reason="set CK3SM_REAL_GAME_DIR to the real game folder")
def test_on_the_real_game_the_pick_for_987_10_27_is_alive_and_holding():
    game = Path(os.environ["CK3SM_REAL_GAME_DIR"])
    p = M.pick_ruler(game, "987.10.27")
    chars = H.characters(game / "history" / "characters")
    assert chars[p.character].alive_on(DATE)
    assert p.title in H.holders(H.titles(game / "history" / "titles"), DATE)[p.character]
    assert all((p.culture, p.religion, p.house, p.birth)), (p.culture, p.religion, p.house, p.birth)
    print(f"\npicked {p.character} ({p.name}), {p.title}: {p.why}")
