"""The top-level index carried through an edit pass (0.5.0, the speed release; DWP
2026-11-07__01-37-15__dev-workflow-process__update-speed-and-the-step-interface.md, build step 2). Every edit pass
makes a new gamestate, and the index of its top-level sections used to be walked again from scratch (~6 s on a
220 MB save, ~30 times per update). Now an edit pass shifts the cached index instead, when every edit lies inside a
section and is well nested; anything else is left to a fresh walk."""

from __future__ import annotations

import random

import pytest

from ck3_save_migrator import gamestate as gs

SECTION = (b'%s={\n\tname="%s"\n\tinner={\n\t\ta=1\n\t\tb={ 1 2 3 }\n\t}\n\tlist={ { x=1 } { y=2 } }\n\t'
           b'quote="a { brace } in text"\n}\n')


def gamestate(n: int = 12) -> bytes:
    return b"meta_data={\n\tversion=\"1.20.1.2\"\n}\n" + b"".join(
        SECTION % (f"sec{i}".encode(), f"S{i}".encode()) for i in range(n)) + b"tail=yes\n"


class Save:
    """What EditPass.apply_to needs of a save."""
    def __init__(self, data: bytes):
        self.gamestate, self.edits = data, []

    def set_gamestate(self, data: bytes) -> None:
        self.gamestate = data


def carried(new: bytes) -> bool:
    return any(d is new for d, _ in gs._TOP_INDEX)


def flat(idx):
    return {k: [(b.start, b.open, b.close) for b in v] for k, v in idx.items()}


def walk(data: bytes):
    """A fresh walk, never the cache: a copy of the bytes is a new object."""
    return gs._top_index(bytes(bytearray(data)))


def run_pass(data: bytes, edits) -> Save:
    s = Save(data)
    gs._top_index(data)                                      # the old gamestate's index is cached, as in a run
    p = gs.EditPass()
    for e in edits:
        p.add(e)
    p.apply_to(s)
    return s


WELL_NESTED = [b"", b"x=1", b"c={ 1 2 }", b"d={\n\te={ f=1 }\n}\n", b'n="{"', b'q="}} {"', b"\n\t\tz=yes"]


def inside_positions(data: bytes):
    """Offsets just after a newline inside some section's interior (never at depth 0)."""
    idx = gs._top_index(data)
    out = []
    for bs in idx.values():
        for b in bs:
            out += [i + 1 for i in range(b.open, b.close) if data[i:i + 1] == b"\n"]
    return out


def test_the_shift_equals_a_fresh_walk_on_random_passes():
    rng = random.Random(20261107)
    applied = 0
    for _ in range(300):
        data = gamestate(rng.randint(2, 15))
        spots = sorted(rng.sample(inside_positions(data), rng.randint(1, 6)))
        edits = [gs.Edit(p, p, rng.choice(WELL_NESTED), "t") for p in spots]
        s = run_pass(data, edits)
        if carried(s.gamestate):
            applied += 1
            assert flat(gs._top_index(s.gamestate)) == flat(walk(s.gamestate))
    assert applied == 300                                     # every one of these passes is shiftable


def test_deleting_a_nested_block_shifts_too():
    data = gamestate(4)
    blk = gs.locate(data, "sec1/inner")
    s = run_pass(data, [gs.Edit(*gs.removal_span(data, blk.start, blk.end), b"", "t")])
    assert carried(s.gamestate)
    assert flat(gs._top_index(s.gamestate)) == flat(walk(s.gamestate))


def test_an_insert_just_before_a_sections_closing_brace_moves_that_brace():
    data = gamestate(3)
    sec = next(gs.find_sections(data, "sec0"))
    s = run_pass(data, [gs.Edit(sec.close, sec.close, b"\tlast=1\n", "t")])
    assert carried(s.gamestate)
    idx = gs._top_index(s.gamestate)
    assert idx[b"sec0"][0].close == sec.close + len(b"\tlast=1\n")
    assert flat(idx) == flat(walk(s.gamestate))


def test_an_edit_between_sections_is_left_to_a_fresh_walk():
    data = gamestate(3)
    at = next(gs.find_sections(data, "sec1")).start            # depth 0: a new top-level section goes here
    s = run_pass(data, [gs.Edit(at, at, b"added={ a=1 }\n", "t")])
    assert not carried(s.gamestate)
    assert b"added" in gs._top_index(s.gamestate)


def test_text_that_would_close_a_section_is_left_to_a_fresh_walk():
    data = gamestate(3)
    p = inside_positions(data)[0]
    s = run_pass(data, [gs.Edit(p, p, b"}\nsneaky={\n", "t")])     # balanced in count, but closes the section
    assert not carried(s.gamestate)


def test_braces_inside_quoted_text_do_not_count():
    data = gamestate(3)
    p = inside_positions(data)[0]
    s = run_pass(data, [gs.Edit(p, p, b'\tnote="} {{ }"\n', "t")])
    assert carried(s.gamestate)
    assert flat(gs._top_index(s.gamestate)) == flat(walk(s.gamestate))


def test_an_index_not_yet_built_stays_lazy():
    data = gamestate(3)
    p = inside_positions(data)[0]
    other = bytes(bytearray(data))                             # never indexed
    s = Save(other)
    gs._TOP_INDEX[:] = [(d, i) for d, i in gs._TOP_INDEX if d is not other]
    ep = gs.EditPass()
    ep.add(gs.Edit(p, p, b"x=1\n", "t"))
    ep.apply_to(s)
    assert not carried(s.gamestate)


def test_the_check_mode_raises_on_a_wrong_shift(monkeypatch):
    data = gamestate(3)
    p = inside_positions(data)[0]
    monkeypatch.setenv("CK3UPDATE_CHECK_INDEX", "1")
    monkeypatch.setattr(gs, "_shifted_top_index", lambda idx, edits, old: {k: v for k, v in idx.items()})  # no shift
    with pytest.raises(gs.GamestateError, match="differs from a fresh walk"):
        run_pass(data, [gs.Edit(p, p, b"grow=1\n", "t")])


# --------------------------------------------------------------------------- lint's SectionIndex shares the index
from ck3_save_migrator import lint  # noqa: E402

REPEATED = gamestate(3) + b"sec1={\n\tsecond=yes\n}\n"           # a top-level key twice: the first block is kept


def test_section_index_takes_the_shared_index_without_walking(monkeypatch):
    g = REPEATED
    gs._top_index(g)                                            # cached, as after a plan's first lookup

    def no_walk(*a, **k):
        raise AssertionError("SectionIndex walked the gamestate again")
    monkeypatch.setattr(gs, "match_brace", no_walk)
    top = lint.SectionIndex(g).top
    assert list(top) == ["meta_data", "sec0", "sec1", "sec2"]
    assert top["sec1"].start == next(gs.find_sections(g, "sec1")).start   # the first of the two sec1 blocks


def test_section_index_equals_its_own_walk(monkeypatch):
    g = REPEATED
    shared = {k: (b.start, b.open, b.close) for k, b in lint.SectionIndex(g).top.items()}
    monkeypatch.setattr(gs, "_top_index", lambda data: None)     # force the old walk
    walked = {k: (b.start, b.open, b.close) for k, b in lint.SectionIndex(g).top.items()}
    assert shared == walked


def test_an_unclosed_section_still_indexes_what_comes_before():
    g = gamestate(3) + b"broken={\n\ta=1\n"
    assert gs._top_index(g) is None
    top = lint.SectionIndex(g).top
    assert {"sec0", "sec1", "sec2"} <= set(top) and "broken" not in top


def test_the_check_mode_passes_on_a_right_shift(monkeypatch):
    data = gamestate(5)
    p = inside_positions(data)[3]
    monkeypatch.setenv("CK3UPDATE_CHECK_INDEX", "1")
    run_pass(data, [gs.Edit(p, p, b"grow={ 1 }\n", "t")])     # no error
