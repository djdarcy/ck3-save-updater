"""The five declarative patches against their Python rules: byte-identical output, the same number of edits.

The Python rule is the specification. Each test builds a synthetic gamestate with every shape the rule's docstring
and code handle, plus near misses it must leave alone, runs the Python rule and the patch on two copies of the same
save, and compares the gamestates byte for byte. The last test checks the two ``**`` patches (R5, R11) run within
twice the time of their Python rules on a gamestate of more than 20 MB.
"""

from __future__ import annotations

import time

import pytest

from ck3_save_migrator import savefile as sf
from ck3_save_migrator.patches import rules_from_pack
from ck3_save_migrator.rules import REGISTRY, RuleContext
from tests.fixtures.make_ck3 import build_ck3

META = (b'meta_data={\n\tsave_game_version=8\n\tversion="1.8.1"\n\tportraits_version=3\n\tgame_rules={\n'
        b'\t\tsettings={ "" "" normal_difficulty "" }\n\t\tsetting={ "" a }\n\t\tother={ "" }\n\t}\n}\n')

PACK = {r.id: r for r in rules_from_pack()}
PYTHON = {r.id: r for r in REGISTRY}


def both(rid: str, body: bytes, ctx: RuleContext | None = None, meta: bytes = META):
    a = sf.parse_save(build_ck3(meta=meta, body=body))
    b = sf.parse_save(build_ck3(meta=meta, body=body))
    ra = PYTHON[rid].run(a, ctx or RuleContext())
    rb = PACK[rid].run(b, ctx or RuleContext())
    return a, b, ra, rb


def assert_same(rid: str, body: bytes, ctx=None, meta: bytes = META, *, edits: int):
    a, b, ra, rb = both(rid, body, ctx, meta)
    assert b.gamestate == a.gamestate
    assert rb.edited == ra.edited == edits
    assert "failed" not in rb.extra
    # and the patch on its own output: nothing more to do
    c = sf.parse_save(build_ck3(meta=b.gamestate[:len(meta)], body=b.gamestate[len(meta):]))
    assert PACK[rid].run(c, ctx or RuleContext()).edited == 0
    return a.gamestate


# --------------------------------------------------------------------------- R1
R1_BODY = (
    b"opinions={\n\tactive_opinions={\n"
    b"\t\t1={\n\t\t\ttemporary_opinion={\n\t\t\t\tvalue=5\n\t\t\t\tconverging={\n\t\t\t\t\ta={ 1 2 }\n\t\t\t\t}\n"
    b"\t\t\t\tdays=3\n\t\t\t}\n"
    b"\t\t\tconverging={ x=1 }\n"                                     # near miss: not inside temporary_opinion
    b"\t\t}\n"
    b"\t\t2={\n\t\t\ttemporary_opinion={ converging=yes value=1 }\n"
    b"\t\t\ttemporary_opinion={\n\t\t\t\tconverging={ }\n\t\t\t\tconverging={ y=2 }\n\t\t\t}\n\t\t}\n"
    b"\t\t{\n\t\t\ttemporary_opinion={\n\t\t\t\tconverging={ z={ w=1 } }\n\t\t\t}\n\t\t}\n"
    b"\t}\n\ttemporary_opinion={ converging={ } }\n}\n"              # near miss: not in active_opinions
    b"misc={\n\ttemporary_opinion={\n\t\tconverging={ }\n\t}\n}\n"   # near miss: not in opinions
)


def test_r1_matches_its_python_rule():
    out = assert_same("R1", R1_BODY, edits=5)
    assert out.count(b"converging") == 3                             # the three near misses


# --------------------------------------------------------------------------- R4
R4_BODY = (
    b'game_rules={\n\tsetting={ "" "" a }\n\tsettings={\n\t\t""\n\t\tb\n\t}\n\tlist={ "" }\n\tsetting=""\n}\n'
    b'misc={\n\tsettings={ "" }\n}\n'                                 # near miss: not under game_rules
    b'game_rules={\n\tsetting={ "" }\n}\n'                            # the top-level section a second time
)


def test_r4_matches_its_python_rule():
    out = assert_same("R4", R4_BODY, edits=8)        # meta_data: 3 + 1; top level: 2 + 1, and 1 in the second copy
    assert b'list={ "" }' in out and b'other={ "" }' in out and b'setting=""' in out and b'misc={\n\tsettings={ "" }' in out


# --------------------------------------------------------------------------- R5
R5_BODY = (
    b"decision_cooldowns={\n\t=-5000.1.1\n\ta=987.1.1\n\t=-5000.1.1\n}\n"
    b"interaction_cooldowns={\n\tx={\n\t\t\t=-5000.1.1\n\t\t\tb=1\n\t}\n}\n"
    b"deep={\n\ta={\n\t\tb={\n  =1\n\t\t}\n\t}\n}\n"
    b"inline={\n\tk={ =2 }\n}\n"                                        # near miss: not at line start
    b'strings={\n\tname="first\n=second"\n}\n'                        # near miss: an = at line start in a string
)


def test_r5_matches_its_python_rule():
    out = assert_same("R5", R5_BODY, edits=4)
    assert b"k={ =2 }" in out and b'"first\n=second"' in out


# --------------------------------------------------------------------------- R7
@pytest.mark.parametrize("portraits,edits", [(None, 2), (5, 3), (3, 2)])
def test_r7_matches_its_python_rule(portraits, edits):
    assert_same("R7", b"date=987.10.27\n", RuleContext(portraits_version=portraits), edits=edits)


def test_r7_makes_no_edit_on_a_save_already_at_the_target():
    meta = b'meta_data={\n\tsave_game_version=18\n\tversion="1.20.1.2"\n}\n'
    assert_same("R7", b"x={\n}\n", meta=meta, edits=0)


def test_r7_with_another_target():
    ctx = RuleContext(target_version="1.21.0", target_save_game_version=19)
    out = assert_same("R7", b"x={\n}\n", ctx, edits=2)
    assert b'version="1.21.0"' in out and b"save_game_version=19" in out


# --------------------------------------------------------------------------- R11
R11_BODY = (
    b"living={\n"
    b'1={\n\tmodifier={\n\t\tmodifier=""\n\t\tdays=5\n\t\tnested={ a=1 }\n\t}\n'
    b'\ttimed_modifier={\n\t\tmodifier=""\n\t}\n'
    b'\tmodifier={\n\t\tmodifier="good"\n\t}\n'                       # near miss: a named modifier
    b'\tother={\n\t\tmodifier=""\n\t}\n'                              # near miss: the parent is not a modifier
    b'\tinline={ modifier={ modifier="" } }\n'                        # near miss: not at line start
    b"}\n}\n"
    b'artifacts={\n\tartifacts={\n2={\n\t\tmodifiers={ "" a "" }\n\t\txmodifiers={ "" }\n'   # near miss: xmodifiers
    b'\t\tmodifiers={\n\t\t\t""\n\t\t}\n\t\tlist={ "" }\n\t}\n\t}\n}\n'                     # near miss: another list
    b'events={\n\tx={\n\t\ttype=""\n\t\tkind={ type="" }\n\t}\n\ttype="real"\n}\n'          # near misses: inline, named
)


def test_r11_matches_its_python_rule():
    out = assert_same("R11", R11_BODY, edits=6)
    for near in (b'modifier="good"', b'other={\n\t\tmodifier=""', b'inline={ modifier={ modifier="" } }',
                 b'xmodifiers={ "" }', b'list={ "" }', b'kind={ type="" }', b'type="real"'):
        assert near in out, near


# --------------------------------------------------------------------------- the real fixtures too
def test_all_five_match_on_the_projects_own_rule_fixtures():
    from tests.fixtures.make_ck3 import RULES_BODY, RULES_META
    from tests.fixtures.religion import OLD_BODY, OLD_META
    for meta, body in ((RULES_META, RULES_BODY), (OLD_META, OLD_BODY)):
        for rid in ("R1", "R4", "R5", "R7", "R11"):
            a, b, ra, rb = both(rid, body, meta=meta)
            assert (rid, b.gamestate == a.gamestate, rb.edited) == (rid, True, ra.edited)


# --------------------------------------------------------------------------- speed
def big_gamestate(target: int = 21 * 1024 * 1024) -> bytes:
    chunk = (b"\t{\n\t\tname=\"filler entry with some text\"\n\t\tdata={ 1 2 3 4 5 6 7 8 9 10 }\n"
             b"\t\tvalue=12.5\n\t}\n") * 40
    shapes = (b'\tx={\n\t\tmodifier={\n\t\t\tmodifier=""\n\t\t}\n\t\tmodifiers={ "" a }\n\t\ttype=""\n'
              b"\t\t=-5000.1.1\n\t}\n")
    parts, size, i = [], 0, 0
    while size < target:
        part = b"sec" + str(i).encode() + b"={\n" + chunk + shapes + b"}\n"
        parts.append(part)
        size += len(part)
        i += 1
    return b"".join(parts)


def test_the_globstar_patches_run_within_twice_the_time_of_their_python_rules(capsys):
    body = big_gamestate()
    assert len(body) > 20 * 1024 * 1024
    times = {}
    for rid in ("R5", "R11"):
        a = sf.parse_save(build_ck3(meta=META, body=body))
        b = sf.parse_save(build_ck3(meta=META, body=body))
        t = time.perf_counter()
        ra = PYTHON[rid].run(a, RuleContext())
        tp = time.perf_counter() - t
        t = time.perf_counter()
        rb = PACK[rid].run(b, RuleContext())
        tk = time.perf_counter() - t
        assert b.gamestate == a.gamestate and rb.edited == ra.edited > 1000
        times[rid] = (tp, tk)
        assert tk <= 2 * tp + 0.25, f"{rid}: python {tp:.2f}s, patch {tk:.2f}s"
    with capsys.disabled():
        print("\n" + "; ".join(f"{rid}: python {tp:.2f}s, patch {tk:.2f}s" for rid, (tp, tk) in times.items())
              + f" on {len(body) / 1024 / 1024:.1f} MB")
