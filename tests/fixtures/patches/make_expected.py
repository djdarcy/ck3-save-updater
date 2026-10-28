"""Write the expected outputs of the declarative patches' test cases, from the Python rules they replaced.

The Python rules R1, R4, R5, R7 and R11 were removed after v0.3.11, so this runs the rules of another checkout:
v0.3.11 (commit 1a7a626), where ``REGISTRY`` still held them. From the project folder:

    git worktree add ../ck3sm-v0.3.11 1a7a626
    python tests/fixtures/patches/make_expected.py --code ../ck3sm-v0.3.11

It refuses to run against code whose rules come from the pack (that would compare the patches with themselves).
It writes ``<case>.gamestate`` for each case in ``cases.py`` (the gamestate bytes exactly as the rule left them) and
``expected.json`` (each case's rule, matched and edited counts and sha256; for the speed test's big gamestate,
the counts and the sha256 only).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--code", required=True, help="a checkout of v0.3.11 (commit 1a7a626), whose rules are run")
    args = ap.parse_args()
    code = Path(args.code).resolve()
    sys.path.insert(0, str(code))                   # its ck3_save_migrator ...
    sys.path.insert(1, str(PROJECT))                # ... and this project's test cases
    import ck3_save_migrator
    from ck3_save_migrator import savefile as sf
    from ck3_save_migrator.rules import REGISTRY, RuleContext
    from tests.fixtures.make_ck3 import build_ck3
    from tests.fixtures.patches.cases import BIG, CASES, META, big_gamestate

    assert Path(ck3_save_migrator.__file__).resolve().is_relative_to(code), ck3_save_migrator.__file__
    by_id = {r.id: r for r in REGISTRY}
    for rid in ("R1", "R4", "R5", "R7", "R11"):
        if hasattr(by_id[rid].apply, "patch"):
            raise SystemExit(f"{code}: {rid} comes from the pack there; give a checkout whose rules are Python")

    expected = {}
    for name, (rid, meta, body, ctx_kw) in CASES.items():
        save = sf.parse_save(build_ck3(meta=meta, body=body))
        res = by_id[rid].run(save, RuleContext(**ctx_kw))
        (HERE / f"{name}.gamestate").write_bytes(save.gamestate)
        expected[name] = {"rule": rid, "matched": res.matched, "edited": res.edited,
                          "sha256": hashlib.sha256(save.gamestate).hexdigest()}
    body = big_gamestate()
    for rid in BIG:
        save = sf.parse_save(build_ck3(meta=META, body=body))
        res = by_id[rid].run(save, RuleContext())
        expected[f"big-{rid}"] = {"rule": rid, "matched": res.matched, "edited": res.edited,
                                  "sha256": hashlib.sha256(save.gamestate).hexdigest()}
    (HERE / "expected.json").write_text(json.dumps(expected, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {len(CASES)} gamestates and expected.json from {code}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
