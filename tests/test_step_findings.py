"""A step's check hands its findings to its rule (0.5.0, the speed release; DWP
2026-11-07__01-37-15__dev-workflow-process__update-speed-and-the-step-interface.md, build step 4 unit a). A
declarative patch's check plans the patch on the gamestate; when its rule runs next on those very bytes, it applies
that plan instead of planning again (R11's rule: 61 s -> 0.1 s on the founding save). The plan is taken only for the
same bytes object and the same values; anything else plans again."""

from __future__ import annotations

import pytest

from ck3_save_migrator import savefile as sf
from ck3_save_migrator.patches import engine
from ck3_save_migrator.patches.run import context_values
from ck3_save_migrator.rules import REGISTRY, RuleContext
from tests.fixtures.make_ck3 import build_ck3
from tests.fixtures.patches.cases import CASES

RULE = {r.id: r for r in REGISTRY}


def r11_save():
    rid, meta, body, _ = CASES["R11"]
    return sf.parse_save(build_ck3(meta=meta, body=body))


def checked(save, ctx):
    """What the check would leave: its plan, made on these bytes with these values."""
    values = context_values(ctx)
    return values, engine.plan(save.gamestate, RULE["R11"].apply.patch, values)


def test_the_rule_applies_the_plan_its_check_left_without_planning_again(monkeypatch):
    expected = r11_save()
    RULE["R11"].run(expected, RuleContext())
    save, ctx = r11_save(), RuleContext()
    values, pl = checked(save, ctx)
    assert pl.edits
    ctx.state["findings"] = {"R11": (save.gamestate, values, pl)}

    def no_second_plan(*a, **k):
        raise AssertionError("the rule planned again")
    monkeypatch.setattr(engine, "plan", no_second_plan)
    res = RULE["R11"].run(save, ctx)
    assert res.edited == len(pl.edits)
    assert save.gamestate == expected.gamestate


# --------------------------------------------------------------------------- U2: a check sees its rule's inputs
from pathlib import Path  # noqa: E402

from ck3_save_migrator import detect  # noqa: E402


def test_r25s_check_passes_the_old_game_folder_as_its_rule_does(monkeypatch, tmp_path):
    from ck3_save_migrator.rules import to_1_20
    seen = {}

    def spy(d, game_dir, mod_dirs=(), old_game_dir=None):
        seen["old"] = old_game_dir
        from collections import Counter
        return [], Counter()
    monkeypatch.setattr(to_1_20, "r25_found", spy)
    detect._r25(b"x", detect.Env(game_dir=tmp_path, old_game_dir=Path("C:/old/game")))
    assert seen["old"] == Path("C:/old/game")


def test_a_declarative_check_plans_with_the_rules_context_when_given(monkeypatch):
    save = r11_save()
    rule_ctx = RuleContext(target_version="9.9")
    seen = []
    from ck3_save_migrator.patches import pack
    real = pack.verdict
    monkeypatch.setattr(pack, "verdict", lambda g, p, ctx=None: seen.append(ctx) or real(g, p, ctx))
    env = detect.Env(patches={"R11": RULE["R11"].apply.patch}, rule_ctx=rule_ctx)
    detect.detect("R11", save.gamestate, env)
    assert seen and seen[0] is rule_ctx                             # not a bare RuleContext(game_dir=...)


def test_r19s_check_passes_the_transplanted_characters_as_its_rule_does(monkeypatch):
    from types import SimpleNamespace
    from ck3_save_migrator import dna
    layout = SimpleNamespace(places=[1], name="x")

    class Seen(Exception):
        pass

    def spy(g, st, transplanted=None):
        raise Seen(transplanted)
    monkeypatch.setattr(dna, "plan_save", spy)
    ctx = RuleContext()
    ctx.state["transplanted_characters"] = {"42"}
    env = detect.Env(dna=SimpleNamespace(source=layout, target=layout), rule_ctx=ctx)
    with pytest.raises(Seen) as got:
        detect._r19(b"x", env)
    assert got.value.args[0] == {"42"}


@pytest.mark.parametrize("change", ["other bytes", "other values"])
def test_a_plan_for_other_bytes_or_values_is_planned_again(monkeypatch, change):
    save, ctx = r11_save(), RuleContext()
    values, pl = checked(save, ctx)
    if change == "other bytes":
        hit = (bytes(bytearray(save.gamestate)), values, pl)        # equal content, another object
    else:
        hit = (save.gamestate, {**values, "target_version": "9.9"}, pl)
    ctx.state["findings"] = {"R11": hit}
    calls = []
    real = engine.plan
    monkeypatch.setattr(engine, "plan", lambda *a, **k: calls.append(1) or real(*a, **k))
    RULE["R11"].run(save, ctx)
    assert calls                                                    # planned again
