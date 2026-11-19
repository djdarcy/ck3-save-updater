"""Every shared reader against every shape the game writes (the cleanup's grids G1 and G2, 2026-11-18).

CONSEQUENCE: 6 (behaviour) -- a reader that misses a shape silently drops or duplicates titles.

Two of the K7 arc's errors came from readers pinned one module at a time: S10 (ten title-key patterns, none reading
1.21's `type=...\tkey=...` line, so the transplant duplicated 12,086 titles and lint's own check missed it) and the
F7 audit (14 baronies with a block before `province =`, 2 keys with an apostrophe). Here each reader is one row and
each shape one column, so a new reader or a new shape is one line, and a reader left behind fails at once. The
shapes are the ones the game has been seen to write; the readers are those importable at module level (five more
are inline in function bodies, which is the refactor-advisor's case for one shared title-key helper).
"""
from pathlib import Path

import pytest

from ck3_save_migrator import carry_1_21 as C
from ck3_save_migrator import deadtitles as DT
from ck3_save_migrator import lint as L
from ck3_save_migrator import mapdata as M
from ck3_save_migrator import translate as T
from ck3_save_migrator.rules import to_1_20 as R

# --- G1: a title key is read in every layout and spelling -----------------------------------------------------------

SHAPES = {                                      # the key line as the game writes it -> the key it holds
    "1.20 bare": (b"key=c_dublin", "c_dublin"),
    "1.20 quoted": (b'key="c_dublin"', "c_dublin"),
    "1.21 type line": (b"type=title_type_default_static\tkey=c_dublin", "c_dublin"),
    "apostrophe": (b"key=b_ka'abir", "b_ka'abir"),
    "1.21 type line with apostrophe": (b"type=title_type_default_static\tkey=b_mansa'l-kharaz", "b_mansa'l-kharaz"),
}


def entry(line: bytes) -> bytes:
    return b"5={\n\t" + line + b"\n\tholder=7\n}\n"


def via_translate(e):
    m = T._KEY.search(b"\n" + e)
    return m.group(1).decode() if m else None


def via_lint(e):
    m = L._T_FIELD[b"key"].search(b"\n" + e)
    return m.group(1).decode() if m else None


def via_to_1_20(e):
    m = R._TITLE_KEY_LINE.search(e)
    return m.group(2).decode() if m else None


def via_carry_1_21(e):
    g = b"landed_titles={\n\tlanded_titles={\n" + e.replace(b"\n", b"\n\t\t").rstrip(b"\t") + b"\t}\n}\nliving={\n}\n"
    rows = list(C._title_rows(g))
    return rows[0][1] or None if rows else None


READERS = {"translate._KEY": via_translate, "lint key field": via_lint, "to_1_20 key line": via_to_1_20,
           "carry_1_21._title_rows": via_carry_1_21}


@pytest.mark.parametrize("reader", READERS, ids=list(READERS))
@pytest.mark.parametrize("shape", SHAPES, ids=list(SHAPES))
def test_every_title_key_reader_reads_every_shape_whole(reader, shape):
    line, key = SHAPES[shape]
    assert READERS[reader](entry(line)) == key


# --- G2: every landed_titles reader gives the tokenizer's answer ----------------------------------------------------

HARD = (                                        # the shapes that broke a reader: a block before `province =`, an
    "﻿# a comment { with a brace\n"        # apostrophe key, a comment holding a brace, a byte-order mark
    "k_realm = {\n"
    "\td_duchy = {\n"
    "\t\tc_county = {\n"
    "\t\t\tb_asmat = {\n\t\t\t\tcolor = { 1 2 3 }\n\t\t\t\tprovince = 77\n\t\t\t}\n"
    "\t\t\tb_ka'abir = {\n\t\t\t\tprovince = 78\n\t\t\t}\n"
    "\t\t}\n"
    "\t\tc_other = {\n\t\t\tb_plain = {\n\t\t\t\tprovince = 79 # a trailing comment\n\t\t\t}\n\t\t}\n"
    "\t}\n"
    "}\n")


@pytest.fixture
def game(tmp_path):
    d = tmp_path / "game" / "common" / "landed_titles"
    d.mkdir(parents=True)
    (d / "00_titles.txt").write_text(HARD, encoding="utf-8")
    M.barony_provinces.cache_clear()
    return tmp_path / "game"


def test_every_landed_titles_reader_gives_the_tokenizers_answer(game):
    parent, provinces = DT.title_tree(Path(game) / "common" / "landed_titles")
    assert provinces == {"b_asmat": 77, "b_ka'abir": 78, "b_plain": 79}
    assert M.barony_provinces(Path(game)) == provinces
    assert C.barony_counties(game) == {b: parent[b] for b in provinces}
    defined, _ = R.defined_title_keys(Path(game))
    assert set(parent) <= defined, sorted(set(parent) - defined)
