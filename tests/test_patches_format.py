"""Loading and validating patch.toml and pack.toml: every refusal names the file and the field."""

from __future__ import annotations

from pathlib import Path

import pytest

from ck3_save_migrator.patches import PatchError, load_pack, load_patch
from ck3_save_migrator.patches.pack import CONTEXT_FIELDS

GOOD = """format = 1
id = "X1"
name = "toy"
title = "a toy patch"
since = "1.20"

[[edit]]
path = "meta_data"
op = "delete_key"
key = "ironman"
"""


def write_patch(root: Path, text: str, folder: str = "X1-toy") -> Path:
    d = root / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / "patch.toml").write_text(text, encoding="utf-8")
    return d


def load(root: Path, text: str):
    return load_patch(write_patch(root, text), from_disk=True, context_fields=CONTEXT_FIELDS)


def refused(root: Path, text: str) -> str:
    with pytest.raises(PatchError) as e:
        load(root, text)
    return str(e.value)


def test_a_good_patch_loads(tmp_path):
    p = load(tmp_path, GOOD)
    assert (p.id, p.name, p.kind, p.default, p.requires) == ("X1", "toy", "declarative", True, ())
    assert p.edits[0].paths == ("meta_data",) and p.edits[0].expect == "any"


@pytest.mark.parametrize("field", ["id", "name", "title", "since", "format"])
def test_a_missing_field_names_the_file_and_the_field(tmp_path, field):
    text = "\n".join(ln for ln in GOOD.splitlines() if not ln.startswith(f"{field} ="))
    msg = refused(tmp_path, text)
    assert "X1-toy/patch.toml" in msg and f"missing field '{field}'" in msg


def test_an_unknown_op_is_refused_naming_it(tmp_path):
    msg = refused(tmp_path, GOOD.replace('"delete_key"', '"delete_everything"'))
    assert "X1-toy/patch.toml [[edit]] #1" in msg and "field 'op'" in msg and "delete_everything" in msg


def test_a_bad_format_is_refused(tmp_path):
    msg = refused(tmp_path, GOOD.replace("format = 1", "format = 2"))
    assert "X1-toy/patch.toml" in msg and "field 'format' is 2" in msg


def test_an_insert_without_done_is_refused(tmp_path):
    text = GOOD.replace('op = "delete_key"\nkey = "ironman"', 'op = "insert"\nposition = "end"\npayload = "x=1\\n"')
    msg = refused(tmp_path, text)
    assert "X1-toy/patch.toml" in msg and "field 'done'" in msg


def test_an_insert_with_done_loads(tmp_path):
    text = GOOD.replace('op = "delete_key"\nkey = "ironman"', 'op = "insert"\nposition = "end"\npayload = "x=1\\n"')
    p = load(tmp_path, text.replace("[[edit]]", 'done = { path = "meta_data", key = "x" }\n\n[[edit]]'))
    assert p.done == {"path": "meta_data", "key": "x"}


def test_an_op_without_its_fields_is_refused(tmp_path):
    msg = refused(tmp_path, GOOD.replace('key = "ironman"', ""))
    assert "[[edit]] #1" in msg and "needs field 'key'" in msg


def test_an_unknown_edit_field_is_refused(tmp_path):
    msg = refused(tmp_path, GOOD + 'regex = "x"\n')
    assert "[[edit]] #1" in msg and "unknown field 'regex'" in msg


def test_where_cannot_grow_into_a_query_language(tmp_path):
    msg = refused(tmp_path, GOOD + 'where = { value = "1", matches = "^a" }\n')
    assert "where.matches" in msg and "script =" in msg


def test_an_unknown_template_is_refused(tmp_path):
    msg = refused(tmp_path, GOOD.replace('op = "delete_key"\nkey = "ironman"', 'op = "set"\nkey = "v"\n'
                                         'value = "@@nonsense@@"'))
    assert "@@nonsense@@" in msg and "target_version" in msg


def test_a_globstar_path_that_names_nothing_to_look_for_is_refused(tmp_path):
    text = GOOD.replace('path = "meta_data"', 'path = "**"').replace(
        'op = "delete_key"\nkey = "ironman"', 'op = "insert"\nposition = "end"\npayload = "x"')
    msg = refused(tmp_path, text.replace("[[edit]]", 'done = { path = "meta_data", key = "x" }\n\n[[edit]]'))
    assert "'**'" in msg


def module_pack(tmp_path: Path, script: str):
    """A pack read as the shipped pack is (not from a folder on disk): the only kind that may name a module."""
    root = tmp_path / "pack"
    write_patch(root, GOOD.split("\n[[edit]]")[0] + f'\nscript = "{script}"\n')
    (root / "pack.toml").write_text('format = 1\nid = "p"\ntitle = "p"\norder = ["X1"]\n', encoding="utf-8")
    return load_pack(root, from_disk=False, context_fields=CONTEXT_FIELDS)


def test_a_script_that_does_not_resolve_is_refused_when_the_pack_is_read(tmp_path):
    from ck3_save_migrator.patches import rules_from_pack
    with pytest.raises(PatchError) as e:
        rules_from_pack(module_pack(tmp_path, "ck3_save_migrator.rules.to_1_20:no_such_rule"))
    msg = str(e.value)
    assert "X1-toy/patch.toml" in msg and "field 'script' names 'no_such_rule'" in msg


def test_a_script_module_that_does_not_exist_is_refused(tmp_path):
    from ck3_save_migrator.patches import rules_from_pack
    with pytest.raises(PatchError, match="field 'script' names module 'no_such_module_here'"):
        rules_from_pack(module_pack(tmp_path, "no_such_module_here:f"))


def test_a_badly_formed_script_is_refused(tmp_path):
    msg = refused(tmp_path, GOOD.split("\n[[edit]]")[0] + '\nscript = "not a script"\n')
    assert "field 'script'" in msg


def test_a_patch_with_edits_and_a_script_is_refused(tmp_path):
    msg = refused(tmp_path, GOOD.replace("[[edit]]", 'script = "m:f"\n\n[[edit]]'))
    assert "exactly one of" in msg


def test_a_pack_order_must_name_every_patch_and_only_those(tmp_path):
    root = tmp_path / "pack"
    write_patch(root, GOOD)
    (root / "pack.toml").write_text('format = 1\nid = "p"\ntitle = "p"\norder = ["X1", "X2"]\n', encoding="utf-8")
    with pytest.raises(PatchError, match=r"pack/pack.toml: field 'order' names X2"):
        load_pack(root, from_disk=True, context_fields=CONTEXT_FIELDS)
    (root / "pack.toml").write_text('format = 1\nid = "p"\ntitle = "p"\norder = ["X0"]\n', encoding="utf-8")
    with pytest.raises(PatchError, match="field 'order' names X0"):
        load_pack(root, from_disk=True, context_fields=CONTEXT_FIELDS)


@pytest.mark.parametrize("value", ["blocks", "blocks-hit"])
def test_matched_loads_and_is_refused_with_a_globstar_path(tmp_path, value):
    text = GOOD.replace("[[edit]]", f'matched = "{value}"\n\n[[edit]]')
    assert load(tmp_path / "a", text).matched == value
    msg = refused(tmp_path / "b", text.replace('path = "meta_data"', 'path = "**/meta_data"'))
    assert f"field 'matched' = '{value}' is for paths without '**'" in msg


def test_an_unknown_matched_is_refused(tmp_path):
    msg = refused(tmp_path, GOOD.replace("[[edit]]", 'matched = "edits"\n\n[[edit]]'))
    assert "field 'matched' must be" in msg and "'edits'" in msg


def test_matched_is_for_declarative_patches(tmp_path):
    msg = refused(tmp_path, GOOD.split("\n[[edit]]")[0] + '\nmatched = "blocks"\nscript = "fix.py:f"\n')
    assert "field 'matched' is for declarative patches" in msg


def test_need_path_loads_and_is_refused_with_a_globstar_path(tmp_path):
    assert load(tmp_path / "a", GOOD + "need_path = true\n").edits[0].need_path is True
    msg = refused(tmp_path / "b", GOOD.replace('path = "meta_data"', 'path = "**/meta_data"') + "need_path = true\n")
    assert "field 'need_path' is for paths without '**'" in msg
    assert "field 'need_path' must be bool" in refused(tmp_path / "c", GOOD + 'need_path = "yes"\n')


def test_not_toml_is_refused_naming_the_file(tmp_path):
    msg = refused(tmp_path, "format = = 1\n")
    assert "X1-toy/patch.toml: not valid TOML" in msg
