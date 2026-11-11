"""Patch format 2 (0.5.x, the save editor): kind = "edit" and typed [params]; format 1 unchanged; update never runs an
edit (the ruling of 2026-11-08: one engine, two front doors)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ck3_save_migrator.patches import PatchError, load_pack, load_patch
from ck3_save_migrator.patches.pack import CONTEXT_FIELDS, rules_from_pack

FIX = """format = 1
id = "F1"
name = "a-fix"
title = "a fix"
since = "1.20"

[[edit]]
path = "meta_data"
op = "delete_key"
key = "ironman"
"""

EDIT = """format = 2
id = "E1"
name = "give-gold"
title = "give a character gold"
since = "1.20"
kind = "edit"

[params.who]
type = "character"
help = "the character to give it to"

[params.amount]
type = "number"

[[edit]]
path = "living/@@who@@"
op = "set"
key = "gold"
value = "@@amount@@"
"""


def write(root: Path, folder: str, text: str) -> Path:
    d = root / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / "patch.toml").write_text(text, encoding="utf-8")
    return d


def load(root: Path, text: str, folder: str = "X-x"):
    return load_patch(write(root, folder, text), from_disk=True, context_fields=CONTEXT_FIELDS)


def refused(root: Path, text: str) -> str:
    with pytest.raises(PatchError) as e:
        load(root, text)
    return str(e.value)


def test_an_edit_in_format_2_loads_with_its_role_and_typed_params(tmp_path):
    p = load(tmp_path, EDIT)
    assert p.role == "edit" and p.kind == "declarative"
    assert p.params == (("who", "character", "the character to give it to"), ("amount", "number", ""))


def test_a_format_1_patch_is_a_fix_as_before(tmp_path):
    p = load(tmp_path, FIX)
    assert (p.role, p.params) == ("fix", ())


def test_a_format_2_patch_without_kind_is_a_fix(tmp_path):
    assert load(tmp_path, FIX.replace("format = 1", "format = 2")).role == "fix"


@pytest.mark.parametrize("field, text", [("kind", 'kind = "edit"'), ("params", '[params.who]\ntype = "character"')])
def test_kind_and_params_need_format_2(tmp_path, field, text):
    body = FIX.replace("[[edit]]", text + "\n\n[[edit]]")
    assert f"field '{field}' needs format = 2" in refused(tmp_path, body)


def test_a_format_3_patch_asks_for_a_newer_tool(tmp_path):
    msg = refused(tmp_path, EDIT.replace("format = 2", "format = 3"))
    assert "field 'format' is 3" in msg and "reads format 1 or 2" in msg and "update the tool" in msg


def test_an_unknown_kind_is_refused(tmp_path):
    assert "field 'kind' is \"fix\"" in refused(tmp_path, EDIT.replace('kind = "edit"', 'kind = "cheat"'))


def test_params_are_for_edits_only(tmp_path):
    assert "[params] are for edits" in refused(tmp_path, EDIT.replace('kind = "edit"', 'kind = "fix"'))


def test_an_unknown_param_type_is_refused(tmp_path):
    msg = refused(tmp_path, EDIT.replace('type = "number"', 'type = "artifact"'))
    assert "[params.amount] type must be one of character, number, text" in msg


def test_a_param_name_becomes_a_template_value_only_in_its_own_patch(tmp_path):
    # @@who@@ is known inside the edit that declares it; a fix using it is refused as an unknown template
    load(tmp_path / "a", EDIT)
    msg = refused(tmp_path / "b", FIX.replace('key = "ironman"', 'key = "@@who@@"'))
    assert "template @@who@@ is not a known value" in msg


def test_a_pack_holds_fixes_and_edits_and_update_runs_only_the_fixes(tmp_path):
    root = tmp_path / "pack"
    write(root, "F1-a-fix", FIX)
    write(root, "E1-give-gold", EDIT)
    (root / "pack.toml").write_text('format = 1\nid = "mine"\ntitle = "mine"\norder = ["F1", "E1"]\n',
                                    encoding="utf-8")
    pack = load_pack(root, from_disk=True, context_fields=CONTEXT_FIELDS)
    assert [p.id for p in pack.ordered()] == ["F1"] and [p.id for p in pack.edits()] == ["E1"]
    assert [r.id for r in rules_from_pack(pack)] == ["F1"]         # what update and migrate run
