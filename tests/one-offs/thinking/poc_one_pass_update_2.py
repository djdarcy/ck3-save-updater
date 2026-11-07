"""POC 2: one pass with group verdicts and the declarative splice, against today, both from a cold cache.

Follows poc_one_pass_update.py (refuted the per-member one pass: R8/R9/R10/R12 share one check) and the /rethink of
2026-11-06 23:5x: that poc's timing compared a cold check (122 s for R11) with a warm rule (49.9 s, index for the same
bytes left on disk by an earlier identical run). Here each arm gets its own empty cache folder.

  today    : the plan judges every step on the untouched save; the rules run.          time = plan checks + rules
  onepass  : before each rule, its check runs on the bytes as they stand, once per check function (a group shares
             the verdict taken before its first member); a "done" skips the rule; a declarative rule takes the
             check's own engine.plan result instead of searching again.            time = per-step checks + rules
             (the plan's own checks still run, to build the Env; their time is excluded)

Predictions, before running:
  1  onepass output sha == today's == d8fd132a; nothing skipped.     Fallback: decision stays on the untouched save.
  2  onepass time < today's, by roughly the declarative rules' second search (R11 ~58 s) plus the checks of steps
     whose decision is the same either way.                          Fallback: one pass for the display only.
  Control: today's arm must reproduce d8fd132a, or the harness is broken and nothing is reported.

Run: python -I tests/one-offs/thinking/poc_one_pass_update_2.py <today|onepass> <scratch dir>
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

MODE, OUT = sys.argv[1], Path(sys.argv[2])
os.environ["CK3UPDATE_CACHE_DIR"] = tempfile.mkdtemp(prefix=f"poc2_{MODE}_", dir=OUT)   # cold, and not the player's

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator import cli, config, detect  # noqa: E402
from ck3_save_migrator.patches import engine  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

D = ROOT / "private" / "data"
target = OUT / f"poc2_{MODE}.ck3"
ARGV = ["update", str(D / "originals/save games/Arch-Abbot_Beidh_of_Omni_Church_Council_987_10_27_husband_died.ck3"),
        "--rules", "all,R14,R15,R16", "--pack", str(D / "faces/acc/cfg/packs/play6"),
        "--vars", str(D / "faces/acc/cfg/packs/play6/vars.toml"), "--allow-run",
        "--old-game-dir", str(D / "versions/1.8.2/game"), "--portrait-mods", "2220098919,2507209632,2996881191",
        "--reference", str(D / "originals/reference-1.20/ref_1_20_987_10_27.ck3"), "--wos-shape", "faith",
        "--no-record", "--force", "--no-ask", "--no-lint", "-o", str(target)]
config.plan_cache_on = lambda path=None: False

real_detect, real_plan, real_run_rules = detect.detect, engine.plan, cli.run_rules
state = {"phase": "plan", "env": None}
rec = {"mode": MODE, "plan_check_s": 0.0, "step_check_s": {}, "rule_s": {}, "skipped": [], "spliced": {}}
check_plans = {}                       # (id of the bytes, patch id) -> the check's Plan, for the rule to take
decided = {}                           # check function -> verdict, for a group of steps that share one


def detect_spy(rid, g, env):
    t = time.perf_counter()
    d = real_detect(rid, g, env)
    if state["phase"] == "plan":
        state["env"] = env
        rec["plan_check_s"] += time.perf_counter() - t
    return d


def plan_spy(d, patch, values):
    k = (id(d), patch.id)
    if MODE == "onepass" and state["phase"] == "rules":
        if state.get("checking"):
            pl = real_plan(d, patch, values)
            check_plans[k] = pl
            return pl
        if k in check_plans:                                  # the rule's search, already done by its check
            rec["spliced"][patch.id] = len(check_plans[k].edits)
            return check_plans.pop(k)
    return real_plan(d, patch, values)


def run_rules_spy(save, rules, ctx):
    state["phase"] = "rules"
    out = []
    for r in rules:
        env = state["env"]
        if MODE == "onepass" and env is not None and detect.has_detector(r.id, env):
            fn = detect.DETECTORS.get(r.id)
            t = time.perf_counter()
            if fn is not None and fn in decided:
                v = decided[fn]
            else:
                env.memo.clear()
                state["checking"] = True
                v = real_detect(r.id, save.gamestate, env).state
                state["checking"] = False
                if fn is not None:
                    decided[fn] = v
            rec["step_check_s"][r.id] = round(time.perf_counter() - t, 1)
            if v == "done":
                rec["skipped"].append(r.id)
                continue
        t = time.perf_counter()
        out += real_run_rules(save, [r], ctx)
        rec["rule_s"][r.id] = round(time.perf_counter() - t, 1)
    return out


detect.detect, engine.plan, cli.run_rules = detect_spy, plan_spy, run_rules_spy
t0 = time.perf_counter()
rec["exit"] = cli.main(ARGV)
rec["wall_s"] = round(time.perf_counter() - t0, 1)
rec["plan_check_s"] = round(rec["plan_check_s"], 1)
rec["rules_total_s"] = round(sum(rec["rule_s"].values()), 1)
rec["step_checks_total_s"] = round(sum(rec["step_check_s"].values()), 1)
rec["compare_s"] = (rec["plan_check_s"] if MODE == "today" else rec["step_checks_total_s"]) + rec["rules_total_s"]
rec["gamestate_sha"] = hashlib.sha256(read_save(target).gamestate).hexdigest()
(OUT / f"poc2_{MODE}.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
print(MODE, "exit", rec["exit"], "| sha", rec["gamestate_sha"][:8], "| skipped", rec["skipped"] or "none",
      "| checks", rec["plan_check_s"] if MODE == "today" else rec["step_checks_total_s"], "s + rules",
      rec["rules_total_s"], "s =", round(rec["compare_s"], 1), "s | spliced", rec["spliced"])
