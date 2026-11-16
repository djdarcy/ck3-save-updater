"""acknowledge-child (design 2026-11-15__04-13-46): a man takes his wife's child as his own. The child joins his
child={ } list in birth order and loses every bastard-family trait; real_father is kept. "honest" turns the
parentage secret into the game's disputed-heritage secret; "clean" removes it and every mention of its id. The
shapes are the founding campaign's, as measured (legitimize_probe.py, legitimize_population.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ck3_save_migrator import cli
from ck3_save_migrator import edit as E
from ck3_save_migrator.savefile import read_save
from tests.fixtures.make_ck3 import DEFAULT_META, build_ck3

LOOKUP = b"traits_lookup={ just wild_oat bastard legitimized_bastard disputed_heritage curious }\n"
CHILD = (b'10={\n\tfirst_name="Gabran"\n\tbirth=976.7.13\n\tdynasty_house=7\n\ttraits={ 0 1 5 }\n'
         b"\tfamily_data={\n\t\treal_father=30\n\t}\n\talive_data={\n\t\ttargeting_secrets={ 900 }\n\t}\n}\n")
SISTER = b'11={\n\tfirst_name="Conchenn"\n\tbirth=980.8.16\n\tfemale=yes\n}\n'
FATHER = (b'20={\n\tfirst_name="Bruide"\n\tbirth=954.4.24\n\tfamily_data={\n\t\tprimary_spouse=21\n'
          b"\t\tspouse=21\n\t\tchild={ 11 }\n\t}\n}\n")
MOTHER = (b'21={\n\tfirst_name="Aelfweard"\n\tbirth=954.9.27\n\tfemale=yes\n\tfamily_data={\n\t\tprimary_spouse=20\n'
          b"\t\tspouse=20\n\t\tchild={ 10 11 }\n\t}\n\talive_data={\n\t\tsecrets={ 900 }\n\t}\n}\n")
STRANGER = b'22={\n\tfirst_name="Other"\n\tbirth=950.1.1\n\tfamily_data={\n\t\tspouse=23\n\t}\n}\n'
LONER = b'24={\n\tfirst_name="Loner"\n\tbirth=950.1.1\n}\n'
REAL = (b'30={\n\tfirst_name="Aethelwine"\n\tbirth=936.12.23\n\talive_data={\n\t\tsecrets={ 5 900 6 }\n\t}\n}\n')
SECRET = (b'900={\n\t\t\ttype="secret_unmarried_illegitimate_child"\n\t\t\ttarget={\n\t\t\t\ttype=char\n'
          b"\t\t\t\tidentity=10\n\t\t\t}\n\t\t\towner=21\n\t\t\tparticipants={ 21 30 }\n\t\t}\n")
KNOWN = (b"\tknown_secrets={ {\n\t\t\tsecret=5\n\t\t\towner=30\n\t\t}\n {\n\t\t\tsecret=900\n\t\t\towner=21\n\t\t}\n"
         b" {\n\t\t\tsecret=900\n\t\t\towner=30\n\t\t}\n }\n")


def body(child=CHILD, father=FATHER, extra=b"") -> bytes:
    return (b"date=987.10.27\n" + LOOKUP + b"living={\n" + child + SISTER + father + MOTHER + STRANGER + LONER
            + REAL + extra + b"}\nsecrets={\n\tsecrets={\n\t\t" + SECRET + b"\t}\n" + KNOWN + b"}\n")


@pytest.fixture(autouse=True)
def no_terminal(monkeypatch):
    monkeypatch.setattr(cli, "interactive", lambda: False)


def save_with(tmp_path: Path, b: bytes) -> Path:
    p = tmp_path / "Camp.ck3"
    p.write_bytes(build_ck3(body=b))
    return p


def out(p: Path) -> bytes:
    return read_save(p.with_name("Camp__acknowledge-child.ck3")).gamestate


def run(p: Path, *values) -> int:
    return cli.main(["edit", str(p), "acknowledge-child", *values])


def test_honest_makes_exactly_three_changes(tmp_path):
    p = save_with(tmp_path, body())
    assert run(p, "Gabran", "20", "honest") == 0
    want = (DEFAULT_META + body()).replace(b"\t\tchild={ 11 }", b"\t\tchild={ 10 11 }", 1) \
        .replace(b"\ttraits={ 0 1 5 }", b"\ttraits={ 0 5 }") \
        .replace(b"secret_unmarried_illegitimate_child", b"secret_disputed_heritage")
    assert out(p) == want
    assert b"\t\treal_father=30\n" in out(p)                                  # the real father is kept


def test_clean_removes_the_secret_and_every_mention_of_it(tmp_path):
    p = save_with(tmp_path, body())
    assert run(p, "10", "20", "clean") == 0
    g = out(p)
    assert b"900" not in g and b"secret_unmarried" not in g
    assert b"\t\tsecrets={ 5 6 }\n" in g                                       # the real father's other secrets stay
    assert b"targeting_secrets" not in g and b'21={\n\tfirst_name="Aelfweard"' in g
    assert b"\t\t\tsecret=5\n\t\t\towner=30\n" in g                              # the other knowledge record stays
    assert b"\t\treal_father=30\n" in g and b"\t\tchild={ 10 11 }" in g


def test_a_father_without_a_child_line_gets_one(tmp_path):
    lone = FATHER.replace(b"\t\tchild={ 11 }\n", b"")
    p = save_with(tmp_path, body(father=lone).replace(b"\t\tchild={ 10 11 }", b"\t\tchild={ 10 }"))
    assert run(p, "10", "20", "honest") == 0
    assert b"\t\tspouse=21\n\t\tchild={ 10 }\n\t}" in out(p)


def test_a_younger_child_goes_after_the_older_ones(tmp_path):
    young = CHILD.replace(b"birth=976.7.13", b"birth=985.1.1")
    p = save_with(tmp_path, body(child=young))
    assert run(p, "10", "20", "honest") == 0
    assert b"\t\tchild={ 11 10 }" in out(p)


@pytest.mark.parametrize("values, message", [
    (["10", "20", "maybe"], "the past is honest"),
    (["10", "21", "honest"], "is a woman"),
    (["10", "22", "honest"], "is not a husband or former husband"),
    (["11", "22", "honest"], "already has a legal father, 20 Bruide"),
    (["10", "30", "honest"], "is not a husband"),                            # the real father, not her husband
    (["10", "999", "honest"], "no living character has the id 999"),
])
def test_refusals_write_nothing(tmp_path, capsys, values, message):
    p = save_with(tmp_path, body())
    assert run(p, *values) == 1
    assert message in capsys.readouterr().err
    assert not p.with_name("Camp__acknowledge-child.ck3").exists()


def test_dangerous_allows_another_man_but_not_one_without_a_family_block(tmp_path, capsys):
    p = save_with(tmp_path, body())
    assert run(p, "10", "24", "honest", "--dangerous") == 1
    assert "has no family block" in capsys.readouterr().err
    assert run(p, "10", "22", "honest", "--dangerous") == 0
    assert b"\t\tspouse=23\n\t\tchild={ 10 }\n" in out(p)
    assert "not the mother's husband (--dangerous)" in E.read_ledger(
        p.with_name("Camp__acknowledge-child.ck3"))["entries"][-1]["what"]


def test_a_second_time_has_nothing_to_change(tmp_path, capsys):
    p = save_with(tmp_path, body())
    assert run(p, "10", "20", "honest") == 0
    first = p.with_name("Camp__acknowledge-child.ck3")
    capsys.readouterr()
    assert cli.main(["edit", str(first), "acknowledge-child", "10", "20", "honest"]) == 1
    assert "already Bruide's child in law" in capsys.readouterr().err


def test_clean_after_honest_still_removes_the_now_disputed_secret(tmp_path):
    p = save_with(tmp_path, body())
    assert run(p, "10", "20", "honest") == 0
    first = p.with_name("Camp__acknowledge-child.ck3")
    assert cli.main(["edit", str(first), "acknowledge-child", "10", "20", "clean"]) == 0
    assert b"900" not in read_save(first.with_name("Camp__acknowledge-child__acknowledge-child.ck3")).gamestate


def test_clean_refuses_a_secret_named_somewhere_it_does_not_know(tmp_path, capsys):
    odd = b'25={\n\tfirst_name="Spy"\n\tbirth=950.1.1\n\talive_data={\n\t\tscheme_secret=900\n\t}\n}\n'
    p = save_with(tmp_path, body(extra=odd))
    assert run(p, "10", "20", "clean") == 1
    assert "cannot be removed safely; use honest instead" in capsys.readouterr().err
    assert run(p, "10", "20", "honest") == 0


@pytest.mark.parametrize("past", ["honest", "clean"])
def test_revert_gives_the_original_back(tmp_path, past):
    p = save_with(tmp_path, body())
    assert run(p, "10", "20", past) == 0
    o = p.with_name("Camp__acknowledge-child.ck3")
    assert cli.main(["edit", str(o), "revert"]) == 0
    assert read_save(o.with_name("Camp__acknowledge-child__revert.ck3")).gamestate == read_save(p).gamestate


def test_crlf_saves(tmp_path):
    p = save_with(tmp_path, body().replace(b"\n", b"\r\n"))
    assert run(p, "10", "20", "clean") == 0
    g = out(p)
    assert b"900" not in g and b"\t\tsecrets={ 5 6 }\r\n" in g and b"\t\tchild={ 10 11 }\r\n" in g
