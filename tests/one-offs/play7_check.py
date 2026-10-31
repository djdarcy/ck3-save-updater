"""play7_check: is play7 exactly play6 plus R23's nickname_text lines? (2026-10-30)

play7 is the founding save through the play6 recipe on main with rule R23 (PR #24). The design's acceptance checks
(2026-10-30__08-23-48__dev-workflow-process__nickname-text.md, N1-N6): R23 found 851 and wrote 851 with 0
unresolved; Uilleam 28792 -> "the Tuatha Dé Danann", Echmarcach 16798202 -> "the Ecumenist"; the templated texts
rendered, no "[" or "$" stored; and everything but the inserted lines identical to play6.

Usage: python -I tests/one-offs/play7_check.py <play6.ck3> <play7.ck3> <play7 report.json>
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator.savefile import read_save  # noqa: E402

LINE = re.compile(rb'\tnickname_text="[^"\n]*"\n')


def main():
    p6, p7 = read_save(sys.argv[1]), read_save(sys.argv[2])
    if len(sys.argv) > 3 and Path(sys.argv[3]).is_file():
        report = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
        r23 = next(r for r in report["rules"] if r.get("id") == "R23")
        print("R23 report:", {k: r23[k] for k in ("matched", "edited")}, r23["extra"])
    g6, g7 = p6.gamestate, p7.gamestate
    # unresolved, measured directly: a nickname line not followed by nickname_text
    lacking = re.findall(rb'\n(\d+)=\{\n(?:\t[^\n]*\n)*?\tnickname=("?)([^"\s]+)\2\n(?!\tnickname_text=)', g7)
    print("nicknamed characters still without nickname_text:", len(lacking), [(a.decode(), c.decode()) for a, _, c in lacking[:5]])
    for key in (b"nick_fabulous_she_he", b"nick_the_blood_motherfather", b"VIET_nick_crow_lady"):
        texts = re.findall(rb'\tnickname="?' + key + rb'"?\n\tnickname_text="([^"]*)"', g7)
        print(f"   {key.decode()}: {[t.decode('utf-8') for t in texts]}")
    new = [m for m in LINE.finditer(g7)]
    # remove the lines play7 has that play6 lacks: play6's own nickname_text lines are the transplanted characters'
    n6 = len(LINE.findall(g6))
    print(f"nickname_text lines: play6 {n6}, play7 {len(new)}, added {len(new) - n6}")
    for cid, want in ((28792, "the Tuatha Dé Danann"), (16798202, "the Ecumenist")):
        m = re.search(rb"\n" + str(cid).encode() + rb"=\{\n(?:\t[^\n]*\n)*?\tnickname=[^\n]*\n\tnickname_text=\"([^\"]*)\"", g7)
        got = m.group(1).decode("utf-8") if m else None
        print(f"   {cid}: {got!r}  {'ok' if got == want else 'MISMATCH, want ' + repr(want)}")
    stored = [m.group().decode("utf-8") for m in new]
    print("stored texts with [ or $:", [s for s in stored if "[" in s or "$" in s])
    # everything but the added lines: strip every nickname_text line from both and compare
    s6, s7 = LINE.sub(b"", g6), LINE.sub(b"", g7)
    print("gamestate without nickname_text lines identical:", s6 == s7,
          f"(play6 {hashlib.sha256(g6).hexdigest()[:8]}, play7 {hashlib.sha256(g7).hexdigest()[:8]})")
    print("meta identical:", bytes(p6.meta or b"") == bytes(p7.meta or b""),
          f"(play7 meta {hashlib.sha256(bytes(p7.meta or b'')).hexdigest()[:8]})")


if __name__ == "__main__":
    main()
