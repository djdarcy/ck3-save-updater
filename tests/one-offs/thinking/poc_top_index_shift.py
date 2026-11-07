"""POC A: can the top-level section index survive an edit pass by shifting its offsets, instead of a rebuild?

DWP 2026-11-07__01-37-15 (build step 1). Counted tonight: gs._top_index is rebuilt ~30 times per update (~6 s each,
~170 s), because every EditPass.apply_to makes a new bytes object. The pass knows every splice (start, end,
replacement), in file order.

The shift: every edit must lie inside one top-level section's interior (open < start, end <= close), and both the
removed text and the replacement must be brace-balanced. Then each section's start/open/close moves by the sum of
the length changes of the edits that end at or before it. Anything else falls back to a rebuild.

Predictions, before running:
  1  on every pass where the shift applies, the shifted index equals a fresh rebuild (100%).
  2  most passes apply (the wholesale replacements -- set_gamestate -- are not EditPasses and are not seen here).
  3  a shift costs well under 0.1 s; a rebuild ~6 s.
  Control: a deliberately wrong shift must disagree with the rebuild on some pass, or the comparison cannot see an
  error and nothing is reported. First run: "ignore inserts at a section's close" -- it never fired (no such insert
  on the v12 recipe), so that run proved nothing. Second run: no shift at all.

Runs the v12 recipe through cli.main with a shim around EditPass.apply_to (it only reads and compares; the run's
own bytes are untouched). Output folder argv[1]; writes only there.
Run: python -I tests/one-offs/thinking/poc_top_index_shift.py <scratch dir>
"""
from __future__ import annotations

import bisect
import json
import os
import sys
import tempfile
import time
from pathlib import Path

OUT = Path(sys.argv[1])
os.environ["CK3UPDATE_CACHE_DIR"] = tempfile.mkdtemp(prefix="pocA_", dir=OUT)
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator import cli, config  # noqa: E402
from ck3_save_migrator import gamestate as gs  # noqa: E402

D = ROOT / "private" / "data"
ARGV = ["update", str(D / "originals/save games/Arch-Abbot_Beidh_of_Omni_Church_Council_987_10_27_husband_died.ck3"),
        "--rules", "all,R14,R15,R16", "--pack", str(D / "faces/acc/cfg/packs/play6"),
        "--vars", str(D / "faces/acc/cfg/packs/play6/vars.toml"), "--allow-run",
        "--old-game-dir", str(D / "versions/1.8.2/game"), "--portrait-mods", "2220098919,2507209632,2996881191",
        "--reference", str(D / "originals/reference-1.20/ref_1_20_987_10_27.ck3"), "--wos-shape", "faith",
        "--no-record", "--force", "--no-ask", "--no-lint", "-o", str(OUT / "pocA.ck3")]
config.plan_cache_on = lambda path=None: False


def balanced(b: bytes) -> bool:
    return b.count(b"{") == b.count(b"}")


def shift(old_idx, edits, old_data, wrong=False):
    """The new index, or (None, reason) when the shift does not apply."""
    if old_idx is None:
        return None, "old index None"
    blocks = sorted((b for bs in old_idx.values() for b in bs), key=lambda b: b.start)
    opens = [b.open for b in blocks]
    for e in edits:
        i = bisect.bisect_left(opens, e.start) - 1           # the last section opening before the edit
        if i < 0 or not (blocks[i].open < e.start and e.end <= blocks[i].close):
            return None, "edit outside a section's interior"
        if not (balanced(old_data[e.start:e.end]) and balanced(e.replacement)):
            return None, "unbalanced braces"
    ends = [e.end for e in edits]
    pref = [0]
    for e in edits:
        pref.append(pref[-1] + len(e.replacement) - (e.end - e.start))

    def moved(p, at_close=False):
        # the control (second run, 2026-11-07): no shift at all. The first control (ignore inserts exactly at a
        # section's close) never fired on the v12 recipe -- no pass inserts at a close -- so it proved nothing.
        if wrong:
            return p
        k = bisect.bisect_right(ends, p)                     # every edit that ends at or before p
        return p + pref[k]
    new = {}
    for key, bs in old_idx.items():
        new[key] = [gs.Block(b.key, moved(b.start), moved(b.open), moved(b.close, True)) for b in bs]
    return new, "shifted"


def flat(idx):
    return None if idx is None else {k: [(b.start, b.open, b.close) for b in v] for k, v in idx.items()}


rec = {"passes": []}
real_apply_to = gs.EditPass.apply_to


def apply_to_spy(self, save):
    old = save.gamestate
    old_idx = gs._top_index(old)
    ordered = self.ordered()
    real_apply_to(self, save)
    new = save.gamestate
    t = time.perf_counter()
    shifted, why = shift(old_idx, ordered, old)
    ts = time.perf_counter() - t
    wrong, _ = shift(old_idx, ordered, old, wrong=True)
    t = time.perf_counter()
    rebuilt = gs._top_index(new)                              # a new object: a real rebuild
    tr = time.perf_counter() - t
    row = {"edits": len(ordered), "why": why, "shift_s": round(ts, 3), "rebuild_s": round(tr, 2),
           "size_mb": round(len(new) / 1e6, 1)}
    if shifted is not None:
        row["equal"] = flat(shifted) == flat(rebuilt)
        row["control_equal"] = flat(wrong) == flat(rebuilt)
        row["inserts_at_close"] = sum(1 for e in ordered if e.start == e.end and
                                      any(b.close == e.start for bs in old_idx.values() for b in bs))
    rec["passes"].append(row)


gs.EditPass.apply_to = apply_to_spy
t0 = time.perf_counter()
rec["exit"] = cli.main(ARGV)
rec["wall_s"] = round(time.perf_counter() - t0, 1)
P = rec["passes"]
applied = [p for p in P if p["why"] == "shifted"]
rec["summary"] = {
    "passes": len(P), "shift_applied": len(applied),
    "equal": sum(p["equal"] for p in applied), "control_equal": sum(p["control_equal"] for p in applied),
    "control_differs_somewhere": any(not p["control_equal"] for p in applied),
    "fallbacks": {w: sum(1 for p in P if p["why"] == w) for w in {p["why"] for p in P} if w != "shifted"},
    "rebuild_s_saved": round(sum(p["rebuild_s"] for p in applied), 1),
    "shift_s_total": round(sum(p["shift_s"] for p in applied), 2)}
(OUT / "pocA.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
print(json.dumps(rec["summary"], indent=1))
