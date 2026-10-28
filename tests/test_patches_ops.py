"""The six operations of a declarative patch, one behaviour per test, on small synthetic saves."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ck3_save_migrator import savefile as sf
from ck3_save_migrator.patches import engine, load_patch, status
from ck3_save_migrator.patches.pack import CONTEXT_FIELDS
from ck3_save_migrator.patches.run import context_values
from ck3_save_migrator.rules import RuleContext
from tests.fixtures.make_ck3 import build_ck3

META = b'meta_data={\n\tsave_game_version=8\n\tversion="1.8.1"\n}\n'
HEAD = 'format = 1\nid = "T"\nname = "toy"\ntitle = "toy"\nsince = "1.20"\n'


def save_of(body: str):
    return sf.parse_save(build_ck3(meta=META, body=body.encode()))


def patch_of(tmp_path: Path, edits: str, extra: str = ""):
    d = tmp_path / "T-toy"
    d.mkdir(exist_ok=True)
    (d / "patch.toml").write_text(HEAD + extra + "\n" + edits, encoding="utf-8")
    return load_patch(d, from_disk=True, context_fields=CONTEXT_FIELDS)


def run(tmp_path, body: str, edits: str, extra: str = "", ctx=None):
    s = save_of(body)
    pl = engine.apply_patch(s, patch_of(tmp_path, edits, extra), context_values(ctx or RuleContext()))
    return s.gamestate[len(META):].decode(), pl


class Raw(str):
    """TOML written as is (a table, a number)."""


def edit(path, op: str, **fields) -> str:
    """One [[edit]] table; strings are written as TOML basic strings, Raw values as they are."""
    def val(v):
        if isinstance(v, Raw):
            return str(v)
        if isinstance(v, str):
            return json.dumps(v)
        if isinstance(v, list):
            return "[" + ", ".join(val(x) for x in v) + "]"
        return str(v)
    body = "".join(f"{k} = {val(v)}\n" for k, v in fields.items())
    return f"[[edit]]\npath = {val(path)}\nop = \"{op}\"\n{body}"


# --------------------------------------------------------------------------- delete_key
def test_delete_key_deletes_a_block_with_a_nested_brace_and_leaves_no_blank_line(tmp_path):
    body = "opinions={\n\ta={\n\t\tgone={\n\t\t\tinner={ 1 2 }\n\t\t}\n\t\tkeep=1\n\t}\n}\n"
    out, pl = run(tmp_path, body, edit("opinions/a", "delete_key", key="gone"))
    assert out == "opinions={\n\ta={\n\t\tkeep=1\n\t}\n}\n" and len(pl.edits) == 1


def test_delete_key_deletes_every_repeat_of_a_key_in_one_block(tmp_path):
    out, pl = run(tmp_path, "s={\n\tx=1\n\ty=2\n\tx=3\n}\n", edit("s", "delete_key", key="x"))
    assert out == "s={\n\ty=2\n}\n" and pl.stats[0]["found"] == 2


def test_delete_key_reaches_a_top_level_section_written_twice(tmp_path):
    out, _ = run(tmp_path, "s={\n\tx=1\n}\nt={\n}\ns={\n\tx=2\n}\n", edit("s", "delete_key", key="x"))
    assert out == "s={\n}\nt={\n}\ns={\n}\n"


def test_delete_key_where_value_compares_the_saves_own_bytes(tmp_path):
    body = 's={\n\tk=""\n\tk="a"\n\tk=a\n}\n'
    out, _ = run(tmp_path, body, edit("s", "delete_key", key="k", where=Raw('{ value = "a" }')))
    assert out == 's={\n\tk=""\n\tk="a"\n}\n'                    # the bare a, not the quoted "a"
    out, _ = run(tmp_path, body, edit("s", "delete_key", key="k", where=Raw("{ value = '\"a\"' }")))
    assert out == 's={\n\tk=""\n\tk=a\n}\n'                      # the quoted "a", not the bare a


def test_delete_key_inline_is_tidy(tmp_path):
    out, _ = run(tmp_path, "s={ a=1 b=2 c=3 }\n", edit("s", "delete_key", key="b"))
    assert out == "s={ a=1 c=3 }\n"


def test_a_path_that_does_not_exist_is_not_needed_not_an_error(tmp_path):
    out, pl = run(tmp_path, "s={\n\tx=1\n}\n", edit("nope/deeper", "delete_key", key="x"))
    assert out == "s={\n\tx=1\n}\n" and pl.failure is None and not pl.needed


def test_star_matches_keyed_and_anonymous_blocks(tmp_path):
    body = "s={\n\t1={\n\t\tx=1\n\t}\n\t{\n\t\tx=2\n\t}\n\tx=3\n}\n"
    out, _ = run(tmp_path, body, edit("s/*", "delete_key", key="x"))
    assert out == "s={\n\t1={\n\t}\n\t{\n\t}\n\tx=3\n}\n"


def test_globstar_with_a_named_last_segment_finds_it_at_any_depth(tmp_path):
    body = "a={\n\tm={ x=1 }\n\tb={\n\t\tm={ x=2 }\n\t}\n}\nm={ x=3 }\n"
    out, _ = run(tmp_path, body, edit("**/m", "delete_key", key="x"))
    assert out == "a={\n\tm={ }\n\tb={\n\t\tm={ }\n\t}\n}\nm={ }\n"


def test_globstar_under_a_section_stays_in_that_section(tmp_path):
    body = "a={\n\tb={\n\t\tx=1\n\t}\n}\nz={\n\tx=2\n}\n"
    out, _ = run(tmp_path, body, edit("a/**", "delete_key", key="x"))
    assert out == "a={\n\tb={\n\t}\n}\nz={\n\tx=2\n}\n"


def test_at_line_start_skips_a_key_that_does_not_begin_its_line(tmp_path):
    body = "s={\n\t=1\n\tk={ =2 }\n}\n"
    out, _ = run(tmp_path, body, edit("**", "delete_key", key="", at="line-start"))
    assert out == "s={\n\tk={ =2 }\n}\n"
    out, _ = run(tmp_path, body, edit("**", "delete_key", key=""))
    assert out == "s={\n\tk={ }\n}\n"


# --------------------------------------------------------------------------- delete_value
def test_delete_value_deletes_matching_bare_values_only(tmp_path):
    body = 's={\n\tl={ "" a "" "b" }\n\tk=""\n}\n'
    out, pl = run(tmp_path, body, edit("s/l", "delete_value", value='""'))
    assert out == 's={\n\tl={ a "b" }\n\tk=""\n}\n' and len(pl.edits) == 2


def test_delete_value_on_its_own_lines(tmp_path):
    out, _ = run(tmp_path, 's={\n\t""\n\tnormal\n\t""\n}\n', edit("s", "delete_value", value='""'))
    assert out == "s={\n\tnormal\n}\n"


# --------------------------------------------------------------------------- delete_entry
def test_delete_entry_by_its_own_key(tmp_path):
    body = "s={\n\tmodifier={\n\t\tmodifier=\"\"\n\t}\n\tother={\n\t}\n}\n"
    out, _ = run(tmp_path, body, edit("s", "delete_entry", where=Raw('{ key = ["modifier", "timed_modifier"] }')))
    assert out == "s={\n\tother={\n\t}\n}\n"


def test_delete_entry_by_a_depth_one_field(tmp_path):
    body = 's={\n\tm={\n\t\tname=""\n\t}\n\tm={\n\t\tname="a"\n\t}\n\tm={\n\t\tx={ name="" }\n\t}\n}\n'
    out, pl = run(tmp_path, body, edit("s", "delete_entry", where=Raw("{ field = { name = '\"\"' } }")))
    assert out == 's={\n\tm={\n\t\tname="a"\n\t}\n\tm={\n\t\tx={ name="" }\n\t}\n}\n' and len(pl.edits) == 1


# --------------------------------------------------------------------------- rename_key
def test_rename_key_renames_every_child_key(tmp_path):
    out, pl = run(tmp_path, "s={\n\told=1\n\told={ a=1 }\n\tkeep=2\n}\n",
                  edit("s", "rename_key", key="old", to="new"))
    assert out == "s={\n\tnew=1\n\tnew={ a=1 }\n\tkeep=2\n}\n" and len(pl.edits) == 2


# --------------------------------------------------------------------------- set
def test_set_replaces_a_value_and_makes_no_edit_when_it_already_equals(tmp_path):
    out, pl = run(tmp_path, 's={\n\tv="1.8.1"\n}\n', edit("s", "set", key="v", value='"1.20.1.2"'))
    assert out == 's={\n\tv="1.20.1.2"\n}\n' and len(pl.edits) == 1
    out, pl = run(tmp_path, out, edit("s", "set", key="v", value='"1.20.1.2"'))
    assert len(pl.edits) == 0 and pl.stats[0]["found"] == 1


def test_set_fills_templates_and_skips_an_edit_whose_value_is_missing(tmp_path):
    out, pl = run(tmp_path, "s={\n\tp=3\n}\n", edit("s", "set", key="p", value="@@portraits_version@@"))
    assert out == "s={\n\tp=3\n}\n" and "skipped" in pl.stats[0]
    out, pl = run(tmp_path, "s={\n\tp=3\n}\n", edit("s", "set", key="p", value="@@portraits_version@@"),
                  ctx=RuleContext(portraits_version=5))
    assert out == "s={\n\tp=5\n}\n"


# --------------------------------------------------------------------------- insert
INSERT = edit("s", "insert", position="end", payload="\tadded=yes\n")
DONE = 'done = { path = "s", key = "added" }\n'


def test_insert_at_the_end_then_done(tmp_path):
    out, pl = run(tmp_path, "s={\n\tx=1\n}\n", INSERT, DONE)
    assert out == "s={\n\tx=1\n\tadded=yes\n}\n" and len(pl.edits) == 1
    out2, pl2 = run(tmp_path, out, INSERT, DONE)
    assert out2 == out and pl2.done and not pl2.needed


def test_insert_at_the_start(tmp_path):
    out, _ = run(tmp_path, "s={\n\tx=1\n}\n", edit("s", "insert", position="start", payload="\n\tfirst=1"), DONE)
    assert out == "s={\n\tfirst=1\n\tx=1\n}\n"


# --------------------------------------------------------------------------- idempotence and expect
@pytest.mark.parametrize("edits,body", [
    (edit("s", "delete_key", key="x"), "s={\n\tx=1\n\ty=2\n}\n"),
    (edit("s/l", "delete_value", value='""'), 's={\n\tl={ "" a }\n}\n'),
    (edit("s", "rename_key", key="x", to="z"), "s={\n\tx=1\n}\n"),
    (edit("s", "set", key="x", value="2"), "s={\n\tx=1\n}\n"),
    (edit("s", "delete_entry", where=Raw('{ key = "x" }')), "s={\n\tx={ }\n}\n"),
])
def test_a_patch_on_its_own_output_makes_no_edit_and_reports_done(tmp_path, edits, body):
    out, pl = run(tmp_path, body, edits)
    assert pl.needed
    p = patch_of(tmp_path, edits)
    again = save_of(out)
    assert status(again.gamestate, p) == "done"
    out2, pl2 = run(tmp_path, out, edits)
    assert out2 == out and not pl2.edits


def test_expect_fails_closed_naming_the_edit_the_path_and_the_count(tmp_path):
    body = "s={\n\tx=1\n}\n"
    edits = edit("s", "delete_key", key="x") + edit("s", "delete_key", key="y", expect=Raw("{ min = 1 }"))
    out, pl = run(tmp_path, body, edits)
    assert out == body and pl.edits == []                       # the first edit is not applied either
    assert pl.failure.endswith("[[edit]] #2 (delete_key at s): expected at least 1, found 0")
    assert "T-toy/patch.toml" in pl.failure


def test_expect_an_exact_count(tmp_path):
    edits = edit("s", "delete_key", key="x", expect=Raw("2"))
    out, pl = run(tmp_path, "s={\n\tx=1\n}\n", edits)
    assert pl.failure and "expected 2, found 1" in pl.failure and out == "s={\n\tx=1\n}\n"
    out, pl = run(tmp_path, "s={\n\tx=1\n\tx=2\n}\n", edits)
    assert pl.failure is None and out == "s={\n}\n"
