"""The set-faith edit (E12): a character's rite= set to a rite, or to a faith's main rite, as a conversion would."""

from __future__ import annotations

from pathlib import Path

import pytest

from ck3_save_migrator import cli
from ck3_save_migrator.savefile import read_save
from tests.fixtures.make_ck3 import DEFAULT_META, build_ck3

LIVING = (b'living={\n'
          b'10={\n\tfirst_name="Gabran"\n\tbirth=976.7.13\n\trite=152\n}\n'
          b'20={\n\tfirst_name="Bruide"\n\tbirth=954.4.24\n\trite=16\n}\n'
          b'}\n'
          b'dead_unprunable={\n30={\n\tfirst_name="Aethelwine"\n\tbirth=936.12.23\n\trite=152\n}\n}\n')
FAITHS = (b'faiths={\n\tdatabase={\n'
          b'\t\t103={\n\t\t\treligion=8\n\t\t\tmain_rite=152\n\t\t\ttag="dynamic_faith_103"\n\t\t\tname="Way of Scarcity"\n\t\t}\n'
          b'\t\t50={\n\t\t\treligion=19\n\t\t\tmain_rite=13\n\t\t\ttag="sunni"\n\t\t\tname="Sunni"\n\t\t}\n\t}\n}\n')
RITES = (b'rites={\n\tdatabase={\n'
         b'\t\t13={\n\t\t\trite_type=hanafi\n\t\t\tfaith=50\n\t\t}\n'
         b'\t\t16={\n\t\t\trite_type=shafii\n\t\t\tfaith=50\n\t\t}\n'
         b'\t\t152={\n\t\t\tfaith=103\n\t\t\tsource=fallback\n\t\t}\n\t}\n}\n')
BODY = b"date=987.10.27\n" + LIVING + FAITHS + RITES
OUT = "Camp__set-faith.ck3"


@pytest.fixture(autouse=True)
def no_terminal(monkeypatch):
    monkeypatch.setattr(cli, "interactive", lambda: False)


def save(tmp_path: Path) -> Path:
    p = tmp_path / "Camp.ck3"
    p.write_bytes(build_ck3(body=BODY))
    return p


def out(p: Path) -> bytes:
    return read_save(p.with_name(OUT)).gamestate


def run(p: Path, *values) -> int:
    return cli.main(["edit", str(p), "set-faith", *values])


def test_gabran_takes_bruide_s_rite_and_only_his_rite_line_changes(tmp_path, capsys):
    p = save(tmp_path)
    assert run(p, "10", "shafii") == 0
    assert out(p) == DEFAULT_META + BODY.replace(b'"Gabran"\n\tbirth=976.7.13\n\trite=152', b'"Gabran"\n\tbirth=976.7.13\n\trite=16')
    said = capsys.readouterr().out
    assert "rite Way of Scarcity's own rite (152) -> shafii (16)" in said
    assert "faith Way of Scarcity (103) -> Sunni (50): under a same-faith succession law" in said


def test_a_faith_means_its_main_rite(tmp_path, capsys):
    p = save(tmp_path)
    assert run(p, "10", "sunni") == 0
    assert b'"Gabran"\n\tbirth=976.7.13\n\trite=13\n' in out(p)
    assert "hanafi (13), the main rite of Sunni (50)" in capsys.readouterr().out


@pytest.mark.parametrize("target", ["Shafi'i", "16", "SHAFII"])
def test_a_rite_by_its_spelling_or_number(tmp_path, target):
    p = save(tmp_path)
    assert run(p, "Gabran", target) == 0
    assert b'"Gabran"\n\tbirth=976.7.13\n\trite=16\n' in out(p)


def test_a_rite_within_the_same_faith_says_nothing_of_succession(tmp_path, capsys):
    p = save(tmp_path)
    assert run(p, "20", "hanafi") == 0
    said = capsys.readouterr().out
    assert "shafii (16) -> hanafi (13)" in said and "succession" not in said


def test_an_unknown_target_is_refused_naming_the_nearest_rite(tmp_path, capsys):
    p = save(tmp_path)
    assert run(p, "10", "shafi") != 0
    err = capsys.readouterr().err
    assert "'shafi' is neither a rite nor a faith" in err and "nearest: shafii" in err
    assert not p.with_name(OUT).exists()


def test_a_dead_character_is_refused_unless_dangerous(tmp_path, capsys):
    p = save(tmp_path)
    assert run(p, "30", "shafii") != 0
    assert "30 Aethelwine is dead; the game converts only the living" in capsys.readouterr().err
    assert not p.with_name(OUT).exists()
    assert run(p, "30", "shafii", "--dangerous") == 0
    assert b'"Aethelwine"\n\tbirth=936.12.23\n\trite=16\n' in out(p) and "dead: forced" in capsys.readouterr().out


def test_the_rite_they_already_follow_writes_nothing(tmp_path, capsys):
    p = save(tmp_path)
    run(p, "20", "shafii")
    assert "20 Bruide already follows shafii (16)" in capsys.readouterr().err
    assert not p.with_name(OUT).exists()


def test_with_the_game_s_names_the_rite_and_the_character_read_as_the_game_shows_them(tmp_path, capsys, monkeypatch):
    from ck3_save_migrator import edit as E
    loc = tmp_path / "game" / "localization" / "english"
    loc.mkdir(parents=True)
    (loc / "l_english.yml").write_text('l_english:\n shafii: "Shafi\'i"\n hanafi: "Hanafi"\n GabrA_n: "Gabrán"\n',
                                       encoding="utf-8")
    monkeypatch.setattr(E.EditContext, "game_dir", property(lambda self: tmp_path / "game"))
    p = tmp_path / "Camp.ck3"
    p.write_bytes(build_ck3(body=BODY.replace(b'"Gabran"', b'"GabrA_n"')))     # the save stores the key
    assert run(p, "Gabrán", "Shafi'i") == 0
    assert "10 Gabrán: rite Way of Scarcity's own rite (152) -> Shafi'i (16)" in capsys.readouterr().out


def test_a_name_nobody_answers_to_is_refused(tmp_path, capsys):
    p = save(tmp_path)
    assert run(p, "Nobody", "shafii") != 0
    assert "no living character answers to 'Nobody'" in capsys.readouterr().err
