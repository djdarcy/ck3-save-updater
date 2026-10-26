"""Census step 1: the shape of every top-level section and every named child (one level down) of a gamestate.

For each block: its byte size, and its children's key kinds -- numeric keys (an id database), title-key-like keys
(b_/c_/d_/k_/e_/h_/x_), other bare keys, anonymous list items -- split by block children and scalar children.
Scalar children are counted only for bodies under 32 MB (iter_children tokenises the whole body).

Usage: python -I tests/one-offs/census_survey.py <save.ck3> [out.json]
"""
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import lint as L  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

TITLE_KEY = re.compile(rb"^[bcdkehx]_\w+$")
SCALAR_LIMIT = 32 * 1024 * 1024


def kind(k):
    if k is None:
        return "anon"
    if k.isdigit():
        return "num"
    if TITLE_KEY.match(k):
        return "tkey"
    return "other"


def shape(g, blk):
    size = blk.close - blk.open
    blocks = Counter()
    sample = {}
    named = []
    try:
        for e in gs.iter_entries(g, *blk.body):
            kd = kind(e.key)
            blocks[kd] += 1
            sample.setdefault(kd, e.key.decode() if e.key else None)
            if kd in ("other", "tkey") and len(named) < 400:
                named.append(e.key.decode())
    except gs.GamestateError as ex:
        return {"size": size, "error": str(ex)}
    scalars = Counter()
    ssample = {}
    if size < SCALAR_LIMIT:
        try:
            for c in gs.iter_children(g, *blk.body):
                if c.block is None:
                    kd = kind(c.key) if c.key is not None else "bare"
                    scalars[kd] += 1
                    ssample.setdefault(kd, (c.key.decode() if c.key else "") + "=" +
                                       g[c.value_start:c.value_end][:40].decode("utf-8", "replace"))
        except gs.GamestateError:
            pass
    return {"size": size, "blocks": dict(blocks), "block_sample": sample, "scalars": dict(scalars),
            "scalar_sample": ssample, "named": named}


def load(path: str) -> bytes:
    """A compressed save through read_save; a plain-text save (header kind 00) by stripping its header line."""
    raw = Path(path).read_bytes()
    if raw[:3] == b"SAV" and raw[5:7] == b"00":
        return raw[raw.index(b"\n") + 1:]
    return sf.read_save(path).gamestate


def main():
    t0 = time.time()
    g = load(sys.argv[1])
    idx = L.SectionIndex(g)
    reps = Counter(m.group(1).decode() for m in gs._TOP_KEY.finditer(g)
                   if g.rfind(b"\n", 0, m.start()) == m.start() - 1 or m.start() == 0)
    out = {}
    for name, b in idx.top.items():
        s = shape(g, b)
        s["repeats"] = reps.get(name, 1)
        out[name] = s
        for child in s.get("named", [])[:60]:
            if s["blocks"].get("num", 0) > 50:       # a database whose entries happen to carry named keys too
                break
            try:
                cb = gs.find_child(g, b, child)
            except gs.GamestateError:
                continue
            cs = shape(g, cb)
            cs.pop("named", None)
            out[f"{name}/{child}"] = cs
    for name, s in out.items():
        s.pop("named", None)
        print(f"{name:60} {s['size']:>11,} rep={s.get('repeats', '-')} blocks={s.get('blocks')} "
              f"scalars={s.get('scalars')} e.g.={s.get('block_sample')} {s.get('scalar_sample') or ''}")
    print(f"done in {time.time() - t0:.0f}s")
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
