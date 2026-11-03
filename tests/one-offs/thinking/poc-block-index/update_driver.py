"""POC arm 2: update's wall time on the founding save, today's resolver against the block index.

PREDICTION (written before running): with the index (rebuilt only when a `**` rule sees a new gamestate object: the
plan's detectors on the input, then R5 and R11 on their edited inputs, so about three builds of ~11-13 s), update is
faster than today's, the output is play7 byte for byte (gamestate e31b5718, meta 1289c61a), and the report's R5 and
R11 counts are 99/99 and 997/997. Pass: index wall < baseline wall, both outputs equal play7, counts equal.
Fallback: if slower, the index must survive a splice by an offset shift instead of a rebuild (measure that next).

How the index survives update's edits, as built here: it never does -- it belongs to one bytes object
(index_resolve.cached_for), and a rule that edits the gamestate makes a new one, so the next `**` rule rebuilds it.
Rules without a `**` path never build one.

Run (one mode per process, so the two runs do not share caches):
  python -I tests/one-offs/thinking/poc-block-index/update_driver.py baseline|index <out.ck3> <config.toml>
Writes only <out.ck3> and its report/lint files (under scratch), with --no-record.
"""

import hashlib
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))


def main() -> int:
    mode, out, cfg = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
    os.environ["CK3SM_CONFIG"] = cfg
    from ck3_save_migrator import cli
    from ck3_save_migrator import savefile as sf
    # both modes run the same tree (the detector cache included); only the resolver differs
    from ck3_save_migrator.patches import blockindex as BI
    from ck3_save_migrator.patches import paths as P
    builds = [0]
    real_init = BI.BlockIndex.__init__

    def counted(self, data):
        builds[0] += 1
        real_init(self, data)
    BI.BlockIndex.__init__ = counted
    if mode == "baseline":
        P.resolve = P.resolve_by_descent              # the resolver before the index
    save = ROOT / "private/data/originals/save games/Arch-Abbot_Beidh_of_Omni_Church_Council_987_10_27_husband_died.ck3"
    argv = ["update", str(save), "--rules", "all,R14,R15,R16",
            "--old-game-dir", str(ROOT / "private/data/versions/1.8.2/game"),
            "--reference", str(ROOT / "private/data/originals/reference-1.20/ref_1_20_987_10_27.ck3"),
            "--wos-shape", "faith", "-o", str(out), "--no-record", "--plain", "--show", "timing:1"]
    t = time.perf_counter()
    code = cli.main(argv)
    wall = time.perf_counter() - t
    s = sf.read_save(out)
    gs_sha, meta_sha = hashlib.sha256(s.gamestate).hexdigest()[:8], hashlib.sha256(s.meta).hexdigest()[:8]
    rep = json.loads(out.with_suffix(".report.json").read_text(encoding="utf-8"))
    counts = {r["id"]: (r.get("matched"), r.get("edited")) for r in rep["rules"] if r["id"] in ("R5", "R11")}
    print(json.dumps({"mode": mode, "exit": code, "wall_s": round(wall, 1), "gamestate": gs_sha, "meta": meta_sha,
                      "play7": gs_sha == "e31b5718" and meta_sha == "1289c61a", "counts": counts,
                      "index_builds": builds[0]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
