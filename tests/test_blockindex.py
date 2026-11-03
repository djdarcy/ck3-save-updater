"""The block index behind paths.resolve (S1, 2026-11-02): equal to the descent it replaced, object for object, and
never answering for a gamestate it was not built from.

The founding save's equivalence (0 mismatches over all 1,297,345 positions R5 and R11 hand to resolve) was measured
by tests/one-offs/thinking/poc-block-index/run_poc.py; these tests hold the same contract on the fixtures."""

from __future__ import annotations

import re

import pytest

from ck3_save_migrator.patches import blockindex as BI
from ck3_save_migrator.patches import paths as P
from tests.fixtures.make_ck3 import RULES_BODY
from tests.fixtures.religion import OLD_BODY, REF_BODY

ANY_KEY = re.compile(rb"(?<![^\s{}])([A-Za-z_][\w.]*)[ \t]*=")       # every keyed child's start
ANY_VALUE = re.compile(rb"(?<![^\s{}])([\w.\"-]+)(?=[\s}])")           # every bare token (values included)


def every_position(d: bytes) -> list[int]:
    return sorted({m.start(1) for m in ANY_KEY.finditer(d)} | {m.start(1) for m in ANY_VALUE.finditer(d)})


def same(d: bytes, positions: list[int]):
    BI.forget()
    new, old = P.resolve(d, positions), P.resolve_by_descent(d, positions)
    assert new.keys() == old.keys()
    for p in old:
        assert new[p][0] == old[p][0], p                # the same ancestor Blocks, in order
        assert new[p][1] == old[p][1], p                # the same Child
    return new


@pytest.mark.parametrize("body", [RULES_BODY, OLD_BODY, REF_BODY], ids=["rules", "old", "ref"])
def test_resolve_equals_the_descent_on_every_position_of_a_fixture(body):
    got = same(body, every_position(body))
    assert len(got) > 50                                # the fixture exercises it


def test_a_brace_inside_a_quoted_string_is_not_a_block():
    d = b'x={\n\tname="a{b}c{"\n\ty={\n\t\tz=1\n\t}\n}\nw={ q=2 }\n'
    got = same(d, [d.index(b"z="), d.index(b"q="), d.index(b"y=")])
    assert [b.key for b in got[d.index(b"z=")][0]] == [b"x", b"y"]
    assert [b.key for b in got[d.index(b"q=")][0]] == [b"w"]


def test_a_section_larger_than_the_small_block_limit():
    filler = b"".join(b"\tf%d=%d\n" % (i, i) for i in range(60_000))      # > 256 KB of scalars at depth 1
    d = b"big={\n" + filler + b"\tinner={\n\t\ttype=\"\"\n\t}\n\tother={ type=x }\n}\nsmall={ type=y }\n"
    assert d.index(b"\tinner") > P._SMALL_BLOCK
    same(d, every_position(d))


def test_the_index_belongs_to_one_gamestate_object():
    d = RULES_BODY
    BI.forget()
    a = BI.index_for(d)
    assert BI.index_for(d) is a                         # reused for the same object
    twin = bytes(bytearray(d))
    assert BI.index_for(twin) is not a                  # another object, even with equal bytes, gets its own
    BI.forget()


def test_an_edited_gamestate_is_never_answered_from_the_old_index():
    d = OLD_BODY
    BI.forget()
    P.resolve(d, every_position(d))                     # builds and keeps d's index
    spliced = d[:40] + b"\n\tadded={ a=1 }\n" + d[40:]
    same_after = P.resolve(spliced, every_position(spliced))
    assert same_after == P.resolve_by_descent(spliced, every_position(spliced))
    BI.forget()


def test_unbalanced_text_still_raises_as_before():
    d = b"x={\n\ty={\n\t\tz=1\n}\n"                     # one "}" missing
    from ck3_save_migrator import gamestate as gs
    with pytest.raises(gs.GamestateError):
        P.resolve_by_descent(d, [d.index(b"z=")])
    BI.forget()
    try:
        r = P.resolve(d, [d.index(b"z=")])
    except gs.GamestateError:
        return                                          # raising is the old behaviour too
    pytest.fail(f"the index answered an unbalanced gamestate: {r}")
