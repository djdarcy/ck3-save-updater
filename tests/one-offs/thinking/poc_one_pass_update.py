"""POC: would a one-pass `update` (check each step on the bytes just before its rule) give the same save?

Question (djdarcy 2026-11-06 22:10; idea note notes/ideas/2026-11-06__22-11-17__both_update-checks-and-applies-each-
step-in-one-pass.md): today every check runs on the untouched save, then every rule runs. In one pass, step N's check
sees the bytes after steps 1..N-1 edited them. Does that change which rules run, or the output?

Predictions, written before running:
  A  one pass (skip a rule whose check says "done" on its pre-rule bytes): no rule is skipped, and the output
     gamestate's sha256 starts d8fd132a (the v12 build).            Fallback: the run/skip decision keeps the
     untouched-save verdicts; one pass only reuses a check's matches.
  B  declarative patches (R1 R4 R5 R7 R11 R26): the check's engine.plan on the pre-rule bytes equals the plan that
     apply_patch computes again on the same bytes, edit for edit; the second plan costs about what the first does
     (R11 ~48 s), which is the time a splice-from-the-check would save.   Fallback: the rule keeps its own plan.
  C  control, predicted to come out "done": the same check run AFTER its rule. A detector that cannot see its own
     fix would make A's "needed" verdicts meaningless.               Fallback: method broken, no result reported.

Runs the v12 recipe through cli.main with the plan cache off, --no-ask, output to the scratch folder given as argv[1].
Writes only that folder. Run: python -I tests/one-offs/thinking/poc_one_pass_update.py <scratch dir>
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from ck3_save_migrator import cli, config, detect  # noqa: E402
from ck3_save_migrator.patches import engine  # noqa: E402

OUT = Path(sys.argv[1])
D = ROOT / "private" / "data"
ARGV = ["update", str(D / "originals/save games/Arch-Abbot_Beidh_of_Omni_Church_Council_987_10_27_husband_died.ck3"),
        "--rules", "all,R14,R15,R16", "--pack", str(D / "faces/acc/cfg/packs/play6"),
        "--vars", str(D / "faces/acc/cfg/packs/play6/vars.toml"), "--allow-run",
        "--old-game-dir", str(D / "versions/1.8.2/game"), "--portrait-mods", "2220098919,2507209632,2996881191",
        "--reference", str(D / "originals/reference-1.20/ref_1_20_987_10_27.ck3"), "--wos-shape", "faith",
        "--no-record", "--force", "--no-ask", "--no-lint", "-o", str(OUT / "poc_onepass.ck3")]

config.plan_cache_on = lambda path=None: False            # judge every step afresh, as a first `update` would

real_detect, real_plan, real_run_rules = detect.detect, engine.plan, cli.run_rules
state = {"phase": "plan", "env": None}
rec = {"plan_verdict": {}, "pre": {}, "post": {}, "skipped": [], "plans": {}, "rule_s": {}}


def detect_spy(rid, g, env):
    d = real_detect(rid, g, env)
    if state["phase"] == "plan":
        state["env"] = env
        rec["plan_verdict"][rid] = d.state
    return d


last_plan = {}                                            # (id of the bytes, patch id) -> (edits, seconds)


def plan_spy(d, patch, values):
    t = time.perf_counter()
    pl = real_plan(d, patch, values)
    s = time.perf_counter() - t
    if state["phase"] == "rules":
        k = (id(d), patch.id)
        if k in last_plan:                                # the rule's second plan on the very bytes the check read
            first, s1 = last_plan.pop(k)
            rec["plans"][patch.id] = {"same_edits": first == repr(pl.edits), "edits": len(pl.edits),
                                      "check_plan_s": round(s1, 1), "rule_plan_s": round(s, 1)}
        else:
            last_plan[k] = (repr(pl.edits), s)
    return pl


def judge(rid, g):
    env = state["env"]
    env.memo.clear()                                      # never a verdict remembered from other bytes
    return real_detect(rid, g, env).state


def run_rules_spy(save, rules, ctx):
    state["phase"] = "rules"
    out = []
    for r in rules:
        has = state["env"] is not None and detect.has_detector(r.id, state["env"])
        if has:
            pre = rec["pre"][r.id] = judge(r.id, save.gamestate)
            if pre == "done":                             # what a one-pass update would do: skip it
                rec["skipped"].append(r.id)
                continue
        t = time.perf_counter()
        out += real_run_rules(save, [r], ctx)
        rec["rule_s"][r.id] = round(time.perf_counter() - t, 1)
        if has:
            rec["post"][r.id] = judge(r.id, save.gamestate)  # the control
    return out


detect.detect, engine.plan, cli.run_rules = detect_spy, plan_spy, run_rules_spy

t0 = time.perf_counter()
code = cli.main(ARGV)
rec["exit"], rec["wall_s"] = code, round(time.perf_counter() - t0, 1)
from ck3_save_migrator.savefile import read_save  # noqa: E402
rec["gamestate_sha"] = hashlib.sha256(read_save(OUT / "poc_onepass.ck3").gamestate).hexdigest()
(OUT / "poc_onepass.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")

print("exit", code, "wall", rec["wall_s"], "s")
print("A  skipped:", rec["skipped"] or "none", "| sha", rec["gamestate_sha"][:8], "(predicted d8fd132a)")
print("   pre-rule verdicts that differ from the untouched save's:",
      {k: (rec["plan_verdict"].get(k), v) for k, v in rec["pre"].items() if rec["plan_verdict"].get(k) != v} or "none")
print("B ", rec["plans"])
print("C  post-rule verdicts not 'done':", {k: v for k, v in rec["post"].items() if v != "done"} or "none")
