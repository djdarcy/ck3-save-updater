"""The five declarative patches (R1, R4, R5, R7, R11) against what their Python rules wrote, byte for byte.

The Python rules were the specification; they were removed once the patches had matched them on every case here and
on a real 1.8.1 campaign (233 MB gamestate, the same sha256 with either). Their outputs on the cases in
``tests/fixtures/patches/cases.py`` are kept as files (``<case>.gamestate``) with their matched and edited counts
(``expected.json``), written by ``make_expected.py`` from v0.3.11. Each test runs the pack's rule on the same save
and compares: the gamestate byte for byte, edited, and matched. Then the patch on its own output must find nothing
more to do.

The last test checks that the two ``**`` patches (R5, R11) still give the Python rules' output on a gamestate of
more than 20 MB (by its sha256), and run within twice the time of the lookups those rules made (the same regex
searches and ``gamestate.child_at``), the best of three runs on each side.

The rules' extra report fields are not reproduced by the patches (each patch reports its per-edit counts under
``edits`` instead): R4 ``blanks_removed``, R5 ``by_parent`` and ``candidates``, R7 ``before`` and ``after``, R11
``by_kind``.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

import pytest

from ck3_save_migrator import gamestate as gs
from ck3_save_migrator import savefile as sf
from ck3_save_migrator.rules import REGISTRY, RuleContext
from tests.fixtures.make_ck3 import build_ck3
from tests.fixtures.patches.cases import BIG, CASES, META, big_gamestate

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "patches"
EXPECTED = json.loads((FIXTURES / "expected.json").read_text(encoding="utf-8"))
RULE = {r.id: r for r in REGISTRY}


def run_case(name: str):
    rid, meta, body, ctx_kw = CASES[name]
    save = sf.parse_save(build_ck3(meta=meta, body=body))
    res = RULE[rid].run(save, RuleContext(**ctx_kw))
    return save, res


def test_the_registry_rules_are_the_declarative_patches():
    for rid in ("R1", "R4", "R5", "R7", "R11"):
        assert RULE[rid].apply.patch.kind == "declarative", rid


def test_every_case_has_its_expected_output():
    assert set(CASES) == {k for k in EXPECTED if not k.startswith("big-")}
    assert {f"big-{rid}" for rid in BIG} <= set(EXPECTED)
    for name in CASES:
        data = (FIXTURES / f"{name}.gamestate").read_bytes()
        assert hashlib.sha256(data).hexdigest() == EXPECTED[name]["sha256"], name


@pytest.mark.parametrize("name", sorted(CASES))
def test_the_patch_writes_what_the_python_rule_wrote(name):
    rid, meta, _, ctx_kw = CASES[name]
    save, res = run_case(name)
    exp = EXPECTED[name]
    assert exp["rule"] == rid
    assert save.gamestate == (FIXTURES / f"{name}.gamestate").read_bytes()
    assert (res.edited, res.matched) == (exp["edited"], exp["matched"])
    assert "failed" not in res.extra
    # and the patch on its own output: nothing more to do
    again = sf.parse_save(build_ck3(meta=save.gamestate[:len(meta)], body=save.gamestate[len(meta):]))
    assert RULE[rid].run(again, RuleContext(**ctx_kw)).edited == 0


# --------------------------------------------------------------------------- what each case is for
def test_r1_leaves_its_near_misses():
    save, res = run_case("R1")
    assert res.edited == 5 and save.gamestate.count(b"converging") == 3


def test_r4_leaves_its_near_misses():
    save, res = run_case("R4")
    out = save.gamestate
    assert res.edited == 8               # meta_data: 3 + 1; top level: 2 + 1, and 1 in the second copy
    assert b'list={ "" }' in out and b'other={ "" }' in out and b'setting=""' in out
    assert b'misc={\n\tsettings={ "" }' in out


def test_r5_leaves_its_near_misses():
    save, res = run_case("R5")
    assert res.edited == 4 and b"k={ =2 }" in save.gamestate and b'"first\n=second"' in save.gamestate


# R7-portraits-5 and -3 are gone: R7 no longer sets portraits_version, R19 stamps the target's (S4 i)
@pytest.mark.parametrize("name, edits", [("R7-no-portraits", 2), ("R7-at-target", 0), ("R7-another-target", 2)])
def test_r7_edits(name, edits):
    save, res = run_case(name)
    assert res.edited == edits
    if name == "R7-another-target":
        assert b'version="1.21.0"' in save.gamestate and b"save_game_version=19" in save.gamestate


def test_r11_leaves_its_near_misses():
    save, res = run_case("R11")
    assert res.edited == 6
    for near in (b'modifier="good"', b'other={\n\t\tmodifier=""', b'inline={ modifier={ modifier="" } }',
                 b'xmodifiers={ "" }', b'list={ "" }', b'kind={ type="" }', b'type="real"'):
        assert near in save.gamestate, near


# --------------------------------------------------------------------------- speed
def _lookup_r5(d: bytes) -> int:
    """What the Python R5 searched with: every '=' that begins a line, resolved with child_at."""
    return len(gs.child_at(d, [m.end() - 1 for m in re.finditer(rb"(?m)^[ \t]*=", d)]))


def _lookup_r11(d: bytes) -> int:
    """What the Python R11 searched with: its three regexes, each resolved with child_at."""
    n = len(gs.child_at(d, [m.start(1) for m in re.finditer(rb'(?m)^\t*(modifier)=""', d)]))
    n += len(gs.child_at(d, [m.start() for m in re.finditer(rb"(?<![\w.])modifiers=\{", d)]))
    return n + len(gs.child_at(d, [m.start(1) for m in re.finditer(rb'(?m)^\t*(type)=""', d)]))


def test_the_globstar_patches_on_a_big_gamestate_match_and_keep_their_speed(capsys):
    body = big_gamestate()
    assert len(body) > 20 * 1024 * 1024
    times = {}

    def best_of_three(fn):
        """The fastest of three runs: one slow run (another process, a cold cache) is noise."""
        best, last = None, None
        for _ in range(3):
            arg = fn.prepare()
            t = time.perf_counter()
            out = fn(arg)
            took = time.perf_counter() - t
            best = took if best is None else min(best, took)
            last = (arg, out)
        return best, last

    for rid, lookup in (("R5", _lookup_r5), ("R11", _lookup_r11)):
        def patch(save, rid=rid):
            return RULE[rid].run(save, RuleContext())
        patch.prepare = lambda: sf.parse_save(build_ck3(meta=META, body=body))
        lookup.prepare = lambda: sf.parse_save(build_ck3(meta=META, body=body)).gamestate
        tl, (_, found) = best_of_three(lookup)
        tk, (save, res) = best_of_three(patch)
        exp = EXPECTED[f"big-{rid}"]
        assert hashlib.sha256(save.gamestate).hexdigest() == exp["sha256"]
        assert (res.edited, res.matched) == (exp["edited"], exp["matched"]) and res.edited > 1000 and found > 1000
        times[rid] = (tl, tk)
        assert tk <= 2 * tl + 0.25, f"{rid}: the Python rule's lookup {tl:.2f}s, patch {tk:.2f}s"
    with capsys.disabled():
        print("\n" + "; ".join(f"{rid}: lookup {tl:.2f}s, patch {tk:.2f}s" for rid, (tl, tk) in times.items())
              + f" on {len(body) / 1024 / 1024:.1f} MB")
