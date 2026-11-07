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
