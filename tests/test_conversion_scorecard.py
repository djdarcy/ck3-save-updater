"""scripts/conversion_scorecard.py: a save against the game's own re-save, each database put in one class.

The standing first step of a big game update (the Director, 2026-11-17). Synthetic gamestates, one database per
class, so a wrong classifier shows as a wrong class, not as a plausible table.
"""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def S():
    spec = importlib.util.spec_from_file_location("conversion_scorecard", ROOT / "scripts" / "conversion_scorecard.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def db(name: str, n: int, body) -> str:
    return f"{name}={{\n" + "".join(f"\t{i}={{ {body(i)} }}\n" for i in range(1, n + 1)) + "}\n"


OLD = ("meta_data={ version=\"1.20.1.2\" }\n"
       + db("same", 200, lambda i: f"a={i} b=x")       # large enough that one edited entry stays under 1%
       + db("renum", 30, lambda i: f"a={i} type={i}")
       + db("losefield", 30, lambda i: f"a={i} provisions=5")
       + db("loseids", 30, lambda i: f"a={i}")
       + db("oldonly", 25, lambda i: f"a={i}"))
NEW = ("meta_data={ version=\"1.21.0\" }\n"
       + db("same", 200, lambda i: f"a={i} b=x")
       + db("renum", 30, lambda i: f"a={i} type={i + 100}")
       + db("losefield", 30, lambda i: f"a={i}")
       + db("loseids", 20, lambda i: f"a={i}")
       + db("brandnew", 25, lambda i: f"c={i}"))


def test_each_database_gets_its_class(S):
    card = S.score(OLD.encode(), NEW.encode())
    cls = {r["path"]: r["class"] for r in card["databases"]}
    assert cls["same"] == S.KEPT
    assert cls["renum"] == S.REENCODED                 # every entry still there, a field written differently
    assert cls["losefield"] == S.DROPPED               # a field gone: the work list
    assert cls["loseids"] == S.DROPPED                 # 10 of 30 ids gone
    assert cls["brandnew"] == S.NEW
    assert cls["oldonly"] == S.DROPPED                 # the whole database gone
    assert card["sections_removed"] == ["oldonly"] and card["sections_added"] == ["brandnew"]


def test_the_row_says_what_changed(S):
    rows = {r["path"]: r for r in S.score(OLD.encode(), NEW.encode())["databases"]}
    assert rows["losefield"]["fields_dropped"] == ["provisions"]
    assert rows["loseids"]["gone"] == 10
    assert rows["renum"]["changed"][0][0] == "type" and rows["renum"]["changed"][0][1] == 1.0
    assert rows["same"]["identical"] == 200


def test_a_control_pair_shows_only_what_differs(S):
    # the control the docstring asks for: one entry edited, everything else kept
    edited = OLD.replace("\t7={ a=7 b=x }", "\t7={ a=7 b=y }")
    card = S.score(OLD.encode(), edited.encode())
    assert {r["path"]: r["class"] for r in card["databases"]} == {p: S.KEPT for p in
                                                                  ("same", "renum", "losefield", "loseids", "oldonly")}
    assert next(r for r in card["databases"] if r["path"] == "same")["identical"] == 199


def test_the_verdict_names_the_drops(S):
    line = S.verdict(S.score(OLD.encode(), NEW.encode()))
    assert "1 kept, 1 re-encoded, 3 dropping something, 1 built new" in line
    assert "losefield" in line and "loseids" in line and "oldonly" in line
    assert line.count("oldonly") == 1                  # a removed section that is also a dropped database: once
