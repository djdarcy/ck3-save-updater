"""reference-mod's --culture/--religion/--house/--title take the names the game shows as well as keys (after-goal-pass
goal, S4): a key stays as it is, a name becomes its key, a shared name is refused with the candidates, an unknown one
with the nearest names, and without the game's files only keys pass."""

from __future__ import annotations

from pathlib import Path

import pytest

from ck3_save_migrator import cli
from ck3_save_migrator import refmod as M

FILES = {
    "common/culture/cultures/00_test.txt": "irish = {\n\tcolor = { 1 1 1 }\n}\nnorse = {\n\tcolor = { 1 1 1 }\n}\n",
    "common/religion/rite_types/00_test.txt": "insular_celtic = {\n\tfaith = christian_faith\n}\n"
                                              "roman_rite = {\n\tfaith = christian_faith\n}\n",
    "common/dynasty_houses/00_test.txt": 'house_briuin = {\n\tprefix = "dynnp_ua"\n\tname = "dynn_briuin"\n\tdynasty = 1\n}\n',
    "common/landed_titles/00_test.txt": "k_ireland = {\n\td_leinster = {\n\t\tc_leinster = {\n\t\t\tb_naas = { }\n"
                                        "\t\t}\n\t}\n\td_munster = { }\n}\n",
    "localization/english/test_l_english.yml": "﻿l_english:\n irish:0 \"Irish\"\n norse:0 \"Norse\"\n"
                                               " insular_celtic:0 \"Insularism\"\n roman_rite:0 \"Roman Rite\"\n"
                                               " dynnp_ua:0 \"ua \"\n dynn_briuin:0 \"Briúin Seóla\"\n"
                                               " k_ireland:0 \"Ireland\"\n d_leinster:0 \"Leinster\"\n"
                                               " c_leinster:0 \"Leinster\"\n d_munster:0 \"Munster\"\n b_naas:0 \"Naas\"\n",
}


@pytest.fixture
def game(tmp_path) -> Path:
    g = tmp_path / "game"
    for rel, text in FILES.items():
        (g / rel).parent.mkdir(parents=True, exist_ok=True)
        (g / rel).write_text(text, encoding="utf-8")
    return g


def test_names_the_game_shows_become_keys_and_keys_stay(game):
    got, notes = M.resolve_names(game, {"culture": "Irish", "religion": "Insularism", "house": "ua Briuin Seola",
                                        "title": "Munster", "birth": "941.1.1"})
    assert got == {"culture": "irish", "religion": "insular_celtic", "house": "house_briuin", "title": "d_munster",
                   "birth": "941.1.1"}
    assert "--religion 'Insularism' is insular_celtic" in notes
    assert M.resolve_names(game, {"culture": "norse", "title": "k_ireland"}) == ({"culture": "norse",
                                                                                  "title": "k_ireland"}, [])


def test_accents_and_case_are_ignored_and_the_house_name_alone_works(game):
    got, _ = M.resolve_names(game, {"house": "BRIÚIN SEÓLA", "religion": "roman rite"})
    assert got == {"house": "house_briuin", "religion": "roman_rite"}


def test_a_shared_name_is_refused_with_the_candidates(game):
    with pytest.raises(M.RefModError, match=r"--title: .*Leinster \(c_leinster\), Leinster \(d_leinster\)"):
        M.resolve_names(game, {"title": "Leinster"})


def test_an_unknown_name_is_refused_with_the_nearest(game):
    with pytest.raises(M.RefModError, match=r"--culture: no culture 'Irsh'; nearest: .*Irish"):
        M.resolve_names(game, {"culture": "Irsh"})


def test_without_the_game_s_files_keys_pass_and_names_are_refused():
    assert M.resolve_names(None, {"culture": "irish"}) == ({"culture": "irish"}, [])
    with pytest.raises(M.RefModError, match="give --game-dir"):
        M.resolve_names(None, {"religion": "Roman Rite"})


def test_the_command_writes_the_keys_for_the_names_given(game, tmp_path, capsys):
    out = tmp_path / "mods"
    out.mkdir()
    assert cli.main(["reference-mod", "--date", "987.10.27", "--game-dir", str(game), "--out", str(out),
                     "--character", "900", "--title", "Ireland", "--culture", "Irish", "--religion", "Insularism",
                     "--house", "ua Briúin Seóla", "--birth", "941.1.1"]) == 0
    text = next(out.rglob("zz_ref.txt")).read_text(encoding="utf-8-sig")
    for key in ("k_ireland", "irish", "insular_celtic", "house_briuin"):
        assert key in text
    assert "--title 'Ireland' is k_ireland" in capsys.readouterr().out
