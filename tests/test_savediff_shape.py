"""savediff's reader and shape layer (ck3_save_migrator/_vendor/savediff: text.py, shape.py), edge case by edge case.

Each case comes from the real saves, where it once cost a defect or a wrong count. The gamestates are written in
the game's own layout: tabs for indentation, closing braces on their own lines, ``12=none`` freed slots, 1.8-style
quoted scalars beside 1.20-style bare ones.
"""

from __future__ import annotations

import pytest

from ck3_save_migrator._vendor.savediff import shape as S
from ck3_save_migrator._vendor.savediff import text as T


def db(name: str, ids, extra: str = "") -> str:
    """A top-level database ``name`` with one small entry per id, then ``extra`` lines."""
    body = "".join(f"{i}={{\n\tflag=yes\n}}\n" for i in ids)
    return f"{name}={{\n{body}{extra}}}\n"


# --------------------------------------------------------------------------- counting entries
def test_a_freed_slot_is_counted_as_free_not_as_an_entry():
    g = db("living", [1, 2], "12=none\n").encode()
    s = S.shape(g)["living"]
    assert s.kinds["free"] == 1 and s.kinds["num"] == 2
    assert s.count == 2 and s.keys == {"1", "2"}
    assert "scalar:num" not in s.kinds


def test_a_numeric_scalar_that_is_not_none_is_a_scalar_entry():
    s = S.shape(b"lookup={\n12=5\n13=none\n}\n")["lookup"]
    assert s.kinds == {"scalar:num": 1, "free": 1} and s.keys == {"12"} and s.count == 1


def test_a_keyed_section_counts_its_distinct_keys_not_its_list_items():
    s = S.shape(db("living", [1, 2, 3], "\t{\n\t\tx=1\n\t}\n").encode())["living"]
    assert s.kinds["anon"] == 1 and s.count == 3


def test_an_unkeyed_section_counts_its_anonymous_items_and_bare_values():
    s = S.shape(b"list={\n\t{\n\t\tx=1\n\t}\n\t{\n\t}\n\t4 5 6\n}\n")["list"]
    assert s.kinds == {"anon": 2, "bare": 3} and s.keys == set() and s.count == 5


def test_entry_kinds_numeric_title_key_other_and_scalar():
    g = b"m={\n\t7={\n\t}\n\tk_france={\n\t}\n\tfoo={\n\t}\n\tb_paris=3\n\tbar=\"x\"\n}\n"
    s = S.shape(g)["m"]
    assert s.kinds == {"num": 1, "tkey": 1, "other": 1, "scalar:tkey": 1, "scalar:other": 1}
    assert s.keys == {"7", "k_france", "foo", "b_paris", "bar"}


def test_the_kind_of_a_section_is_its_most_common_entry_kind_or_empty():
    sh = S.shape(db("living", [1, 2], "\tname=\"x\"\n").encode() + b"empty={\n}\n")
    assert sh["living"].kind == "num" and sh["empty"].kind == "empty" and sh["empty"].count == 0


def test_quoted_and_bare_scalars_are_both_scalars():
    s = S.shape(b"meta={\n\tversion=\"1.8.1\"\n\tsave_game_version=8\n}\n")["meta"]
    assert s.kinds == {"scalar:other": 2} and s.keys == {"version", "save_game_version"}


# --------------------------------------------------------------------------- repeats and broken input
def test_a_top_level_section_written_twice_has_repeats_2_and_counts_distinct_keys():
    part = db("dead_unprunable", [5, 6, 7])
    s = S.shape((part + db("living", [1]) + part).encode())["dead_unprunable"]
    assert s.repeats == 2 and s.count == 3 and s.keys == {"5", "6", "7"}


def test_a_repeated_section_is_shaped_from_its_first_block():
    """The probe's behaviour, kept: keys only the second copy has are not read (the game's two copies of
    dead_unprunable are byte-identical, so nothing is lost there)."""
    s = S.shape((db("dead_unprunable", [5]) + db("dead_unprunable", [5, 9])).encode())["dead_unprunable"]
    assert s.repeats == 2 and s.keys == {"5"}


def test_an_unclosed_section_keeps_the_sections_before_it_and_does_not_raise():
    g = (db("living", [1]) + db("units", [2]) + "broken={\n\t1={\n}\n" + db("after", [3])).encode()
    idx = T.SectionIndex(g)
    assert list(idx.top) == ["living", "units"]
    sh = S.shape(g)
    assert set(sh) == {"living", "units"} and sh["living"].count == 1


def test_braces_inside_quoted_strings_do_not_unbalance_anything():
    g = b"living={\n1={\n\tname=\"a { b\"\n\tnick=\"} c\"\n}\n2={\n}\n}\nnext={\n3={\n}\n}\n"
    sh = S.shape(g)
    assert sh["living"].count == 2 and sh["next"].count == 1
    assert list(T.SectionIndex(g).top) == ["living", "next"]


# --------------------------------------------------------------------------- the probe's constants
def test_a_section_with_more_than_db_threshold_numeric_entries_is_not_descended_into():
    above = db("provinces", [1, 2, 3, 4], "\tsub={\n\t\tx=1\n\t}\n")
    at = db("titles", [1, 2, 3], "\tsub={\n\t\tx=1\n\t}\n")
    sh = S.shape((above + at).encode(), db_threshold=3)
    assert "provinces/sub" not in sh and "titles/sub" in sh
    assert sh["titles/sub"].keys == {"x"}


def test_the_default_db_threshold_is_50():
    sh = S.shape(db("big", range(51), "\tsub={\n\t}\n").encode() + db("small", range(50), "\tsub={\n\t}\n").encode())
    assert "big/sub" not in sh and "small/sub" in sh


def test_a_body_over_scalar_limit_has_no_scalar_kinds():
    g = b"meta={\n\tversion=\"1.8.1\"\n\tsave_game_version=8\n\t1={\n\t}\n\t5=none\n}\n"
    small = S.shape(g, scalar_limit=10)["meta"]
    assert small.kinds == {"num": 1} and small.keys == {"1"}
    assert S.shape(g)["meta"].kinds["scalar:other"] == 2


def test_only_the_first_child_sample_named_children_are_shaped():
    g = b"s={\n\ta={\n\t}\n\tb={\n\t}\n\ta={\n\t}\n\tc={\n\t}\n}\n"
    assert {p for p in S.shape(g, child_sample=3) if "/" in p} == {"s/a", "s/b"}
    assert {p for p in S.shape(g) if "/" in p} == {"s/a", "s/b", "s/c"}


def test_named_children_one_level_down_only():
    g = b"landed_titles={\n\tlanded_titles={\n\t\tdeep={\n\t\t}\n0={\n}\n\t}\n\tindex=4\n}\n"
    sh = S.shape(g)
    assert set(sh) == {"landed_titles", "landed_titles/landed_titles"}
    assert sh["landed_titles/landed_titles"].count == 2 and sh["landed_titles"].keys == {"landed_titles", "index"}


# --------------------------------------------------------------------------- shape_rows
def test_shape_rows_of_a_save_against_itself_has_equal_counts_and_counts_every_section():
    g = (db("living", [1, 2], "5=none\n") + "landed_titles={\n\tlanded_titles={\n0={\n}\n\t}\n}\n").encode()
    sh = S.shape(g)
    out = S.shape_rows({"left": sh, "right": sh})
    assert set(out["sections_counted"]) == set(sh) == {r["path"] for r in out["rows"]}
    assert all(r["counts"]["left"] == r["counts"]["right"] for r in out["rows"])
    assert out["sections_counted"] == {p: 2 * s.count for p, s in sh.items()}


def test_shape_rows_reports_a_path_only_one_witness_has_as_none_for_the_others():
    a = S.shape(db("living", [1]).encode() + db("units", []).encode())
    b = S.shape(db("living", [1, 2]).encode())
    rows = {r["path"]: r for r in S.shape_rows({"a": a, "b": b, "c": {}})["rows"]}
    assert rows["units"]["counts"] == {"a": 0, "b": None, "c": None}
    assert rows["living"]["counts"] == {"a": 1, "b": 2, "c": None}


def test_shape_rows_names_any_witnesses_and_reports_repeats():
    part = db("dead_unprunable", [5])
    out = S.shape_rows({"base": S.shape((part + part).encode()), "x": S.shape(part.encode())})
    (row,) = out["rows"]
    assert row["repeats"] == {"base": 2} and row["kind"] == "num"


def test_shape_rows_of_nothing_still_has_sections_counted():
    assert S.shape_rows({}) == {"sections_counted": {}, "rows": []}


# --------------------------------------------------------------------------- the text header
def test_strip_text_header_returns_the_body_of_a_plain_text_save():
    assert T.strip_text_header(b"SAV0100abcd00000000\nmeta_data={\n}\n") == b"meta_data={\n}\n"


@pytest.mark.parametrize("kind", ["01", "02", "03"])
def test_strip_text_header_refuses_any_other_kind_naming_it(kind):
    with pytest.raises(T.SaveTextError, match=f"'{kind}'"):
        T.strip_text_header(f"SAV01{kind}7d3b00370000006a\nPK...".encode())


def test_strip_text_header_leaves_a_bare_gamestate_alone():
    assert T.strip_text_header(b"meta_data={\n}\n") == b"meta_data={\n}\n"


# --------------------------------------------------------------------------- locate
def test_locate_walks_a_path_and_returns_none_when_a_step_is_absent():
    g = b"a={\n\tb={\n\t\tc={\n\t\t\tx=1\n\t\t}\n\t}\n}\n"
    idx = T.SectionIndex(g)
    c = T.locate(idx, "a/b/c")
    assert c is not None and g[c.open:c.close + 1] == b"{\n\t\t\tx=1\n\t\t}"
    assert T.locate(idx, "a/z") is None and T.locate(idx, "nope") is None and T.locate(idx, "a/b/c/d") is None
    assert idx.block("a/b") == T.locate(idx, "a/b")
