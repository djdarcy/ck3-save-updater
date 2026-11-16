"""The set-eminent-holy-sites edit (E11): 1 to 3 of a faith's own holy sites, as its head of faith may choose in play."""

from __future__ import annotations

from pathlib import Path

import pytest

from ck3_save_migrator import cli
from ck3_save_migrator.savefile import read_save
from tests.fixtures.make_ck3 import DEFAULT_META, build_ck3

FAITH = (b'faiths={\n\tdatabase={\n'
         b'\t\t103={\n\t\t\tfaith_type=christian_faith\n\t\t\treligion=8\n\t\t\tholy_sites={ 0 1 4 15 }\n'
         b'\t\t\teminent_holy_sites={ 0 1 }\n\t\t\ttag="dynamic_faith_103"\n\t\t\tname="Way of Scarcity"\n\t\t}\n'
         b'\t\t12={\n\t\t\tfaith_type=christian_faith\n\t\t\treligion=8\n\t\t\tholy_sites={ 0 1 5 }\n'
         b'\t\t\ttag="catholic"\n\t\t}\n\t}\n}\n')
SITES = (b'religion={\n\tholy_sites={\n'
         b'\t\t0={\n\t\t\tholy_site_type=jerusalem\n\t\t}\n\t\t1={\n\t\t\tholy_site_type=rome\n\t\t}\n'
         b'\t\t4={\n\t\t\tholy_site_type=kent\n\t\t}\n\t\t5={\n\t\t\tholy_site_type=constantinople\n\t\t}\n'
         b'\t\t15={\n\t\t\tbarony=12\n\t\t\tholy_site_type=iona\n\t\t}\n\t}\n}\n')
BODY = b"living={\n}\n" + FAITH + SITES


@pytest.fixture(autouse=True)
def no_terminal(monkeypatch):
    monkeypatch.setattr(cli, "interactive", lambda: False)


def save(tmp_path: Path, body: bytes = BODY) -> Path:
    p = tmp_path / "Camp.ck3"
    p.write_bytes(build_ck3(body=body))
    return p


def out(p: Path) -> bytes:
    return read_save(p.with_name("Camp__set-eminent-holy-sites.ck3")).gamestate


def run(p: Path, *values) -> int:
    return cli.main(["edit", str(p), "set-eminent-holy-sites", *values])


def test_iona_joins_jerusalem_and_rome_and_nothing_else_changes(tmp_path):
    p = save(tmp_path)
    assert run(p, "Way of Scarcity", "jerusalem rome iona") == 0
    assert out(p) == (DEFAULT_META + BODY).replace(b"eminent_holy_sites={ 0 1 }", b"eminent_holy_sites={ 0 1 15 }")


def test_sites_by_number_and_commas_and_the_faith_by_its_key(tmp_path):
    p = save(tmp_path)
    assert run(p, "dynamic_faith_103", "0,15") == 0
    assert b"\t\t\teminent_holy_sites={ 0 15 }\n" in out(p)


def test_a_faith_without_an_eminent_line_gets_one_after_its_holy_sites(tmp_path):
    p = save(tmp_path)
    assert run(p, "catholic", "jerusalem constantinople") == 0
    assert b"\t\t\tholy_sites={ 0 1 5 }\n\t\t\teminent_holy_sites={ 0 5 }\n\t\t\ttag=\"catholic\"" in out(p)


@pytest.mark.parametrize("sites, says", [
    ("jerusalem constantinople", "constantinople (5) is not among the faith's holy sites"),
    ("", "a faith has 1 to 3 eminent holy sites, not 0"),
    ("jerusalem rome kent iona", "not 4"),
    ("rome rome", "a site is named twice"),
])
def test_what_the_game_refuses_is_refused_with_its_rule(tmp_path, capsys, sites, says):
    p = save(tmp_path)
    assert run(p, "Way of Scarcity", sites) != 0
    err = capsys.readouterr().err
    assert says in err and not p.with_name("Camp__set-eminent-holy-sites.ck3").exists()


def test_dangerous_writes_a_refused_choice_and_says_it_was_forced(tmp_path, capsys):
    p = save(tmp_path)
    assert run(p, "Way of Scarcity", "jerusalem constantinople", "--dangerous") == 0
    assert b"eminent_holy_sites={ 0 5 }" in out(p) and "forced" in capsys.readouterr().out


def test_choosing_the_sites_it_already_has_writes_nothing(tmp_path, capsys):
    p = save(tmp_path)
    run(p, "Way of Scarcity", "jerusalem rome")
    assert "eminent holy sites are already jerusalem (0), rome (1)" in capsys.readouterr().err
    assert not p.with_name("Camp__set-eminent-holy-sites.ck3").exists()


def test_an_unknown_faith_is_refused_with_the_nearest_name(tmp_path, capsys):
    p = save(tmp_path)
    assert run(p, "Way of Scarsity", "jerusalem") != 0
    assert "nearest: Way of Scarcity" in capsys.readouterr().err
