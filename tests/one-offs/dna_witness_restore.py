"""dna_witness_restore: the founding recipe's faces step (G1) reduced to the witness restore, now that R19 carries
the save's own faces (PR #39, 2026-11-02).

dna_whole_save.py did two things: translate every face into layout (c), and use the 967 save's face wherever the
967 save holds the same person (decision G: the earliest witness wins), inserting one for a character with no
face. R19 now does the first. This does only the second, on R19's output, so the recipe plus R19 should give
play7 byte for byte (the R19 brief's acceptance).

Same person = same full id, same first name, same birth date (as dna_whole_save.py). The witness face is
translated from layout (a) into layout (c) with the prototype's own plan (dna_whole_save's LAYOUT_A / LAYOUT_C),
so the bytes are the ones play7 holds. Nothing else is touched: R19 already translated the other faces and
stamped portraits_version.

Usage: python -I tests/one-offs/dna_witness_restore.py <in.ck3> <967 witness.ck3> <out.ck3>
"""
from __future__ import annotations

import base64
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
import dna_layout as D  # noqa: E402
import dna_translate as X  # noqa: E402
import dna_whole_save as W  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402


def main():
    src_p, wit_p, out_p = sys.argv[1:4]
    a = D.dna_order(D.load_layout(W.LAYOUT_A))
    c = D.dna_order(D.load_layout(W.LAYOUT_C))
    plan_a = X.build(a, c)
    chars = lambda nbytes: len(base64.b64encode(bytes(nbytes)))      # noqa: E731
    readable = {chars(532), chars(524)}             # 712 (1.8.1) and 700 (967): layout (a) at its 130 places

    def translate(s: bytes) -> bytes | None:
        if len(s) not in readable:
            return None
        return base64.b64encode(plan_a.apply(W.b64d(s)[:4 * len(a)]))

    save = sf.read_save(src_p)
    g = save.gamestate
    wit = W.people(sf.read_save(wit_p).gamestate)
    ours = W.people(g, with_entries=True)
    edits, tally = [], Counter()
    for cid, r in ours.items():
        w = wit.get(cid)
        if not (w and w["dna"] and w["name"] == r["name"] and w["birth"] == r["birth"]):
            continue
        new = translate(w["dna"])
        if new is None:
            tally[f"967 face not usable: length {len(w['dna'])}"] += 1
            continue
        if r["dna_span"]:
            s0, s1 = r["dna_span"]
            tally["967 witness face used"] += 1
            edits.append((s0, s1, new))
        elif r["skill_end"]:
            tally[f"recovered from 967 ({r['sec'].split('/')[-1]}, had no face)"] += 1
            edits.append((r["skill_end"], r["skill_end"], b'\n\tdna="' + new + b'"'))
    edits.sort(key=lambda e: (e[0], e[1]))
    parts, pos = [], 0
    for s0, s1, rep in edits:
        if s0 < pos:
            raise SystemExit(f"overlapping edits at {s0}")
        parts += [g[pos:s0], rep]
        pos = s1
    parts.append(g[pos:])
    save.set_gamestate(b"".join(parts))
    sf.write_save(save, out_p, force=True)
    report = {"input": str(src_p), "witness": str(wit_p), "output": str(out_p), "faces": dict(tally)}
    Path(out_p).with_suffix(".witness.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    print(f"wrote {out_p}")


if __name__ == "__main__":
    main()
