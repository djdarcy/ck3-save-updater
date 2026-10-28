"""rule_shapes: which of the registered rules could be a declarative patch.toml (a path selector plus an operation
over the gamestate tree), and which need code. Measures the population the epic #14 patch format rests on
(first-mile, 2026-10-27): the claim to test was "about 2 of 7 subtractive rules fit a declarative shape".

For each rule's apply function (its own source, not the helpers it calls), the features it uses:
  ops      delete_key / delete_block / rename_key / insert (EditPass primitives on a located block)
  raw      gs.Edit(...) with computed text (a replacement the rule builds)
  ctx      ctx.game_dir / ctx.state / ctx.reference / reference_gamestate / Transplant (data beyond the save)
  calls    helper functions it delegates to (named so a reader can follow them)
Classified: DECLARATIVE (ops only, no raw, no ctx), DECLARATIVE+PREDICATE (ops plus a computed condition in the
rule itself, e.g. a predicate over the entry), CODE (raw edits or outside data).

Known answers: R1 (delete converging under a path) must be DECLARATIVE; R17 (the transplant write) must be CODE.

Usage: python -I tests/one-offs/rule_shapes.py
"""
from __future__ import annotations

import inspect
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import rules as R  # noqa: E402

OPS = re.compile(r"\.(delete_key|delete_block|rename_key|insert)\(")
RAW = re.compile(r"gs\.Edit\((?![^)]*,\s*b\"\"\s*,)")           # a computed replacement (not an empty one)
DEL = re.compile(r"gs\.Edit\([^)]*,\s*b\"\"\s*,")               # a deletion written as an empty replacement
CTX = re.compile(r"ctx\.(game_dir|state|reference|old_game_dir|wos_shape|expansion_orders)|reference_gamestate|Transplant\b|ctx\.state")
CALL = re.compile(r"(?<![\w.])(_[a-z]\w+|[a-z]\w*_(?:entries|plan|keys|cycles|coordinator))\(")
PRED = re.compile(r"\bif\b(?!.*\bis not None\b\s*(and|:)).*(==|!=|<=|>=|\bin\b|[<>]|\bnot\b)")  # not a null guard


def classify(rule):
    src = inspect.getsource(rule.apply)
    body = src.split('"""', 2)[-1] if src.count('"""') >= 2 else src     # skip the docstring
    ops = sorted(set(OPS.findall(body)) | ({"delete(empty edit)"} if DEL.search(body) else set()))
    raw = len(RAW.findall(body))
    ctx = sorted(set(m.group(0) for m in CTX.finditer(body)))
    calls = sorted(set(CALL.findall(body)) - {"_skip"})
    if raw or ctx:
        kind = "CODE"
    elif ops and PRED.search(body):
        kind = "DECLARATIVE+PREDICATE"
    elif ops:
        kind = "DECLARATIVE"
    else:
        kind = "CODE"           # no EditPass primitive at all: a report, a delegation, or computed edits
    return kind, ops, raw, ctx, calls


def main():
    rows = [(r.id, r.name, *classify(r)) for r in R.REGISTRY]
    for rid, name, kind, ops, raw, ctx, calls in rows:
        print(f"{rid:4} {name:24} {kind:22} ops={','.join(ops) or '-':28} raw={raw:<2} "
              f"ctx={','.join(ctx) or '-'}  calls={','.join(calls) or '-'}")
    c = Counter(k for _, _, k, *_ in rows)
    print(f"\n{len(rows)} rules: " + ", ".join(f"{k} {n}" for k, n in c.most_common()))
    known = {r[0]: r[2] for r in rows}
    ok = known.get("R1") == "DECLARATIVE" and known.get("R17") == "CODE"
    print(f"known answers (R1 DECLARATIVE, R17 CODE): {'ok' if ok else 'FAILED: ' + str((known.get('R1'), known.get('R17')))}")


if __name__ == "__main__":
    main()
