"""``--dangerous`` (U6; the director's ruling 2026-11-13 02:32): on update/status a pack whose version span leaves the
save out runs anyway and the plan says so; on edit it is record-only (the ledger marks the run) until edits declare a
span."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from ck3_save_migrator import cli
from ck3_save_migrator import edit as E
from ck3_save_migrator import plan as PL
from tests import test_update as TU
from tests.fixtures.make_ck3 import build_ck3
from tests.test_update import game, old_save

saves = TU.saves

PATCH = """format = 1
id = "D1"
name = "far-future"
title = "a patch for saves from 9.0 on"
since = "9.0"

[[edit]]
path = "meta_data"
op = "delete_key"
key = "no_such_key"
"""


def future_pack(root: Path) -> Path:
    p = root / "future"
    (p / "D1-far").mkdir(parents=True)
    (p / "D1-far" / "patch.toml").write_text(PATCH, encoding="utf-8")
    (p / "pack.toml").write_text('format = 1\nid = "future"\ntitle = "f"\norder = ["D1"]\n\n[applies]\n'
                                 'save = ">=9.0"\n', encoding="utf-8")
    return p


def test_a_pack_outside_its_span_does_not_run_without_the_flag(tmp_path, saves):
    p = PL.plan_update(old_save(saves), game_dir=str(game(tmp_path)), packs=[str(future_pack(tmp_path))])
    assert "D1" not in p.running() and not any("--dangerous" in n for n in p.notes)


def test_dangerous_runs_it_and_says_so(tmp_path, saves):
    p = PL.plan_update(old_save(saves), game_dir=str(game(tmp_path)), packs=[str(future_pack(tmp_path))],
                       dangerous=True)
    assert "D1" in p.running()
    assert any(n.startswith("--dangerous: --pack future runs outside its version span") for n in p.notes)
    assert p.inputs.get("dangerous") is True                         # what the record stores


def rename_plan(g: bytes, params: dict):
    m = re.search(rb'first_name="Beidh"', g)
    return [E.Change(m.start(), m.group(0), b'first_name="B"')], "character 1"


@pytest.fixture
def toy(monkeypatch, tmp_path):
    monkeypatch.setitem(E.BUILTIN, "rename", E.EditDef("rename", "rename", (), rename_plan))
    monkeypatch.setattr(cli, "interactive", lambda: False)
    p = tmp_path / "Camp.ck3"
    p.write_bytes(build_ck3())
    return p


def ledger(p: Path) -> dict:
    return json.loads(p.with_name(p.stem + ".edits.json").read_text(encoding="utf-8"))


def test_edit_dangerous_is_recorded_in_the_ledger(toy, capsys):
    assert cli.main(["edit", str(toy), "rename", "--dangerous"]) == 0
    assert ledger(toy.with_name("Camp__rename.ck3"))["entries"][-1].get("dangerous") is True
    assert "edits declare no version span yet" in capsys.readouterr().out


def test_an_edit_without_the_flag_is_not_marked(toy):
    assert cli.main(["edit", str(toy), "rename"]) == 0
    assert "dangerous" not in ledger(toy.with_name("Camp__rename.ck3"))["entries"][-1]
