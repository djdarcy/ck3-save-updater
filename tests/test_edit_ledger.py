"""The save editor's ledger (U3): ``<output stem>.edits.json`` beside each edited save, holding every edit applied in
that file's line in order, each change's bytes with its offset in the input and in the output, and the hashes."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path

import pytest

from ck3_save_migrator import cli
from ck3_save_migrator import edit as E
from ck3_save_migrator.savefile import read_save
from tests.fixtures.make_ck3 import build_ck3


def rename_plan(g: bytes, params: dict):
    """Two changes of different lengths: character 1's and character 2's first names."""
    a = re.search(rb'first_name="Beidh"', g)
    b = re.search(rb'first_name="Simin"', g)
    return ([E.Change(a.start(), a.group(0), f'first_name="{params["name"]}"'.encode()),
             E.Change(b.start(), b.group(0), b'first_name="S"')], "characters 1 and 2")


@pytest.fixture(autouse=True)
def toy(monkeypatch):
    monkeypatch.setitem(E.BUILTIN, "rename", E.EditDef("rename", "rename", (("name", "text", ""),), rename_plan))
    monkeypatch.setattr(cli, "interactive", lambda: False)


@pytest.fixture
def save(tmp_path) -> Path:
    p = tmp_path / "Camp.ck3"
    p.write_bytes(build_ck3())
    return p


def ledger(p: Path) -> dict:
    return json.loads(p.with_name(p.stem + ".edits.json").read_text(encoding="utf-8"))


def test_an_edit_writes_a_ledger_beside_its_output(save):
    assert cli.main(["edit", str(save), "rename", "Brigid"]) == 0
    out = save.with_name("Camp__rename.ck3")
    led = ledger(out)
    assert led["format"] == 1 and led["save"] == out.name and len(led["entries"]) == 1
    e = led["entries"][0]
    assert (e["edit"], e["params"], e["pack"]) == ("rename", {"name": "Brigid"}, "builtin")
    assert e["sha256"] == hashlib.sha256(out.read_bytes()).hexdigest()
    assert e["input_sha256"] == hashlib.sha256(save.read_bytes()).hexdigest()
    assert len(e["changes"]) == 2


def test_the_ledger_reproduces_the_input_from_the_output(save):
    assert cli.main(["edit", str(save), "rename", "Brigid"]) == 0
    out = save.with_name("Camp__rename.ck3")
    g_in, g_out = read_save(save).gamestate, read_save(out).gamestate
    back = g_out
    for c in sorted(ledger(out)["entries"][0]["changes"], key=lambda c: -c["offset_out"]):
        after, before = base64.b64decode(c["after"]), base64.b64decode(c["before"])
        assert back[c["offset_out"]:c["offset_out"] + len(after)] == after     # the output offset is right
        back = back[:c["offset_out"]] + before + back[c["offset_out"] + len(after):]
    assert back == g_in
    for c in ledger(out)["entries"][0]["changes"]:                            # and the input offset too
        before = base64.b64decode(c["before"])
        assert g_in[c["offset"]:c["offset"] + len(before)] == before


def test_a_second_edit_appends_after_the_first(save, monkeypatch):
    def simin_plan(g, params):
        m = re.search(rb'first_name="S"', g)
        return [E.Change(m.start(), m.group(0), f'first_name="{params["name"]}"'.encode())], "character 2"
    monkeypatch.setitem(E.BUILTIN, "rename2", E.EditDef("rename2", "rename 2", (("name", "text", ""),), simin_plan))
    assert cli.main(["edit", str(save), "rename", "Brigid"]) == 0
    first = save.with_name("Camp__rename.ck3")
    assert cli.main(["edit", str(first), "rename2", "Saoirse"]) == 0
    second = first.with_name("Camp__rename__rename2.ck3")
    led = ledger(second)
    assert [e["edit"] for e in led["entries"]] == ["rename", "rename2"]
    assert led["entries"][1]["input_sha256"] == led["entries"][0]["sha256"]


def test_a_dry_run_writes_no_ledger(save):
    assert cli.main(["edit", str(save), "rename", "Brigid", "--dry-run"]) == 0
    assert not list(save.parent.glob("*.edits.json"))


def test_a_ledger_in_a_newer_format_is_refused(save, capsys):
    save.with_name("Camp.edits.json").write_text('{"format": 2, "entries": []}', encoding="utf-8")
    assert cli.main(["edit", str(save), "rename", "Brigid"]) == 1
    assert "ledger format 2" in capsys.readouterr().err
