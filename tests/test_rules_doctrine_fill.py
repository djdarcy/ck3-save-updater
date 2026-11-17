"""R10 fills a carried faith's empty choosable doctrine groups (the after-goal-pass goal, S2; the director's ruling
2026-11-17__03-48-44, B): the origin faith's doctrine first, the religion's default second, nothing without the game."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ck3_save_migrator.rules import religion_1_20 as REL
from tests.test_edit_doctrines import GAME

SAVE = (b'religion={\n\treligions={\n\t\t8={\n\t\t\ttag="christianity_religion"\n\t\t}\n\t}\n}\n'
        b"faiths={\n\tdatabase={\n"
        b"\t\t12={\n\t\t\treligion=8\n\t\t\tdoctrine=special_doctrine_is_christian_faith\n"
        b"\t\t\tdoctrine=doctrine_funeral_sky_burial\n\t\t}\n\t}\n}\n")


@pytest.fixture()
def game(tmp_path):
    root = tmp_path / "game"
    for rel, text in GAME.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return root


def fill(game_dir, doctrines):
    return REL._fill_doctrine_groups(SAVE, SimpleNamespace(game_dir=game_dir), REL._db(SAVE)[1], "12", doctrines)


def test_origin_first_then_the_religion_s_default_each_with_its_source(game):
    added, filled = fill(game, [b"doctrine=special_doctrine_is_christian_faith"])
    assert added == [b"doctrine=doctrine_funeral_sky_burial", b"doctrine=doctrine_pilgrimage_encouraged"]
    assert [(f["group"], f["doctrine"], f["source"].split(" (")[0]) for f in filled] == [
        ("doctrine_funeral", "doctrine_funeral_sky_burial", "origin faith 12"),
        ("doctrine_pilgrimage", "doctrine_pilgrimage_encouraged", "christianity_religion default")]
    assert "00_christianity.txt:" in filled[1]["source"]


def test_a_group_the_faith_already_fills_is_left_as_it_is(game):
    added, _ = fill(game, [b"doctrine=doctrine_pilgrimage_forbidden", b"doctrine=doctrine_funeral_stoic"])
    assert added == []


def test_without_the_game_s_files_nothing_is_filled():
    assert fill(None, []) == ([], [])
