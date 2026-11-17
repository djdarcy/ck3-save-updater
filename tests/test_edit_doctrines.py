"""The set-doctrines edit (E13): a faith's tenets and doctrines, faith and main rite in step, the game's rules from its
files (faith_rules.py). The game folder here is a small fake one, so the tests need no installed game."""

from __future__ import annotations

from pathlib import Path

import pytest

from ck3_save_migrator import cli
from ck3_save_migrator import edit as E
from ck3_save_migrator.savefile import read_save
from tests.fixtures.make_ck3 import DEFAULT_META, build_ck3

GAME = {
    "common/religion/doctrine_types/20_doctrines.txt":
        "doctrine_pilgrimage_forbidden = {\n\tdoctrine_group_type = doctrine_pilgrimage\n\tindex = 0\n}\n\n"
        "doctrine_pilgrimage_encouraged = {\n\tdoctrine_group_type = doctrine_pilgrimage\n\tindex = 1\n}\n\n"
        "doctrine_funeral_stoic = {\n\tdoctrine_group_type = doctrine_funeral\n\tindex = 0\n}\n\n"
        "doctrine_funeral_sky_burial = {\n\tdoctrine_group_type = doctrine_funeral\n\tindex = 1\n}\n",
    "common/religion/doctrine_types/40_doctrines_special.txt":
        "special_doctrine_is_christian_faith = {\n\tdoctrine_group_type = is_christian_faith\n}\n\n"
        "special_doctrine_ecumenical_christian = {\n\tdoctrine_group_type = ecumenical\n}\n",
    "common/religion/doctrine_group_types/00_doctrine_group_types.txt":
        "doctrine_pilgrimage = {\n\tcategory = main_group\n}\ndoctrine_funeral = {\n\tcategory = clergy\n}\n"
        "is_christian_faith = {\n\tcategory = special\n}\necumenical = {\n\tcategory = special\n}\n",
    "common/religion/tenet_types/00_tenet_types.txt":
        "tenet_gnosticism = {\n\ticon = x\n}\n\ntenet_esotericism = {\n\ticon = x\n}\n\ntenet_communion = {\n\ticon = x\n}\n\n"
        "tenet_jewish_syncretism = {\n\tcan_pick = {\n\t\tNOT = { religion = religion:judaism_religion }\n"
        "\t\tunique_syncretism_trigger = yes\n\t}\n}\n\n"
        "tenet_christian_syncretism = {\n\tcan_pick = {\n\t\tNOT = { religion = religion:christianity_religion }\n"
        "\t\tunique_syncretism_trigger = yes\n\t}\n}\n",
    "common/scripted_triggers/00_religious_triggers.txt":
        "unique_syncretism_trigger = {\n\tNOR = {\n\t\ttenet:tenet_christian_syncretism = { is_in_list = x }\n"
        "\t\ttenet:tenet_jewish_syncretism = { is_in_list = x }\n\t}\n}\n",
    "common/religion/religion_types/00_christianity.txt":
        "christianity_religion = {\n\tdoctrine = special_doctrine_is_christian_faith\n\tdoctrine = doctrine_pilgrimage_encouraged"
        "\n\tfaiths = {\n\t}\n}\n",
    "common/defines/00_defines.txt": "NReligion = {\n\tFAITH_CORE_TENETS_CAP = 3\n}\n",
}
LINES = ["tenet=tenet_gnosticism", "tenet=tenet_esotericism", "tenet=tenet_jewish_syncretism",
         "doctrine=special_doctrine_is_christian_faith", "doctrine=doctrine_funeral_stoic",
         "doctrine=special_doctrine_ecumenical_christian"]


def lines(tabs: int) -> bytes:
    return b"".join(b"\t" * tabs + ln.encode() + b"\n" for ln in LINES)


BODY = (b'religion={\n\treligions={\n\t\t8={\n\t\t\ttag="christianity_religion"\n\t\t}\n\t}\n}\n'
        b'faiths={\n\tdatabase={\n'
        b'\t\t103={\n\t\t\treligion=8\n\t\t\tmain_rite=152\n\t\t\tname="Way of Scarcity"\n' + lines(3) + b'\t\t}\n'
        b'\t\t12={\n\t\t\treligion=8\n\t\t\tmain_rite=0\n\t\t\ttag="catholic"\n'
        b'\t\t\tdoctrine=special_doctrine_is_christian_faith\n\t\t}\n\t}\n}\n'
        b'rites={\n\tdatabase={\n\t\t152={\n\t\t\tfaith=103\n\t\t\tdata={\n\t\t\t\tname="Way of Scarcity"\n'
        + lines(4) + b'\t\t\t}\n\t\t\tsource=fallback\n\t\t}\n\t}\n}\n')
OUT = "Camp__set-doctrines.ck3"


@pytest.fixture(autouse=True)
def no_terminal(monkeypatch):
    monkeypatch.setattr(cli, "interactive", lambda: False)


@pytest.fixture()
def game(tmp_path, monkeypatch):
    root = tmp_path / "game"
    for rel, text in GAME.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    monkeypatch.setattr(E.EditContext, "game_dir", property(lambda self: root))
    return root


def save(tmp_path: Path) -> Path:
    p = tmp_path / "Camp.ck3"
    p.write_bytes(build_ck3(body=BODY))
    return p


def out(p: Path) -> bytes:
    return read_save(p.with_name(OUT)).gamestate


def run(p: Path, *values) -> int:
    return cli.main(["edit", str(p), "set-doctrines", *values])


def both(old: str, *new: str) -> bytes:
    """The whole save with one line of the faith (3 tabs) and of the rite's data (4 tabs) replaced by `new` lines
    (none removes it). The faith and the rite are edited as separate sections: a 3-tab line is a suffix of a 4-tab one."""
    whole = DEFAULT_META + BODY
    cut = whole.index(b"rites={")
    faith, rite = whole[:cut], whole[cut:]
    faith = faith.replace(b"\n\t\t\t" + old.encode() + b"\n", b"\n" + b"".join(b"\t\t\t" + n.encode() + b"\n" for n in new))
    rite = rite.replace(b"\n\t\t\t\t" + old.encode() + b"\n",
                        b"\n" + b"".join(b"\t\t\t\t" + n.encode() + b"\n" for n in new))
    return faith + rite


def test_a_doctrine_fills_an_empty_group_in_the_faith_and_its_main_rite(tmp_path, game, capsys):
    p = save(tmp_path)
    assert run(p, "Way of Scarcity", "+doctrine_pilgrimage_encouraged") == 0
    last = "doctrine=special_doctrine_ecumenical_christian"
    assert out(p) == both(last, last, "doctrine=doctrine_pilgrimage_encouraged")
    assert "doctrine_pilgrimage: empty -> doctrine_pilgrimage_encouraged" in capsys.readouterr().out


def test_a_doctrine_replaces_its_group_s_current_one_in_place(tmp_path, game):
    p = save(tmp_path)
    assert run(p, "103", "+doctrine_funeral_sky_burial") == 0
    assert out(p) == both("doctrine=doctrine_funeral_stoic", "doctrine=doctrine_funeral_sky_burial")


def test_a_tenet_swap_is_written_in_place_in_both(tmp_path, game):
    p = save(tmp_path)
    assert run(p, "103", "-tenet_gnosticism +tenet_communion") == 0
    assert out(p) == both("tenet=tenet_gnosticism", "tenet=tenet_communion")


def test_a_special_doctrine_the_religion_does_not_carry_everywhere_may_be_removed(tmp_path, game):
    p = save(tmp_path)
    assert run(p, "103", "-special_doctrine_ecumenical_christian") == 0
    assert out(p) == both("doctrine=special_doctrine_ecumenical_christian")


@pytest.mark.parametrize("changes, says", [
    ("-tenet_jewish_syncretism +tenet_christian_syncretism",
     "tenet_christian_syncretism cannot be chosen by a faith of christianity_religion (00_tenet_types.txt:"),
    ("+tenet_christian_syncretism", "a faith holds 3 tenets, not 4 (00_defines.txt:2)"),
    ("+tenet_christian_syncretism", "a faith may hold only one of tenet_christian_syncretism, tenet_jewish_syncretism "
                                    "(unique_syncretism_trigger, 00_religious_triggers.txt:1)"),
    ("-tenet_gnosticism", "a faith holds 3 tenets, not 2"),
    ("-special_doctrine_is_christian_faith", "special_doctrine_is_christian_faith is carried by every faith of "
                                             "christianity_religion and is not a faith's to drop (00_christianity.txt:2)"),
    ("-doctrine_funeral_stoic", "removing doctrine_funeral_stoic leaves doctrine_funeral (clergy) with no doctrine"),
    ("+doctrine_no_such_thing", "doctrine_no_such_thing is not a doctrine or tenet the game defines"),
])
def test_what_the_game_refuses_is_refused_naming_its_rule(tmp_path, game, capsys, changes, says):
    p = save(tmp_path)
    assert run(p, "103", changes) != 0
    assert says in capsys.readouterr().err
    assert not p.with_name(OUT).exists()


def test_dangerous_forces_christian_syncretism_and_dropping_teachings_of_jesus(tmp_path, game, capsys):
    p = save(tmp_path)
    assert run(p, "103", "-tenet_jewish_syncretism +tenet_christian_syncretism -special_doctrine_is_christian_faith",
               "--dangerous") == 0
    g = out(p)
    assert g.count(b"tenet=tenet_christian_syncretism\n") == 2 and b"jewish" not in g
    assert g.count(b"special_doctrine_is_christian_faith") == 1          # only faith 12's line is left
    assert "forced: " in capsys.readouterr().out


def test_removing_what_the_faith_does_not_have_is_refused(tmp_path, game, capsys):
    p = save(tmp_path)
    assert run(p, "103", "-doctrine_pilgrimage_encouraged") != 0
    assert "faith 103 does not have doctrine_pilgrimage_encouraged" in capsys.readouterr().err


def test_without_the_game_s_files_the_edit_is_refused(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(E.EditContext, "game_dir", property(lambda self: None))
    p = save(tmp_path)
    assert run(p, "103", "+doctrine_pilgrimage_encouraged", "--dangerous") != 0
    assert "the game's own files are needed" in capsys.readouterr().err
