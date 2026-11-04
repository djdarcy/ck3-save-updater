"""U3: what happens to the cultures' innovation-spread markers. 1.8 writes exposure_marker (an innovation in progress),
culture_marker (the culture it comes from) and exposure_type (border / realm / religion); 1.20 writes spread_marker and
culture_marker. Align cultures by id between our updated save and the game's re-save of it (ids are kept on load), and
compare our exposure_marker with the re-save's spread_marker, and each culture's progress on that innovation.
Usage: spread_marker_compare.py <our save> <the game's re-save>"""
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\code\ck3-save-migrator")
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402


def load(path):
    try:
        return sf.read_save(path).gamestate
    except sf.UnsupportedKindError:
        raw = open(path, "rb").read()
        return raw[raw.index(b"\n") + 1:]


def cultures(d):
    cm = gs.locate(d, "culture_manager/cultures")
    return {e.key.decode(): d[e.body[0]:e.body[1]] for e in gs.iter_entries(d, *cm.body)}


def val(body, key):
    m = re.search(rb"(?<![\w])" + key + rb"=\"?([\w.]+)", body)
    return m.group(1).decode() if m else None


def progress(body, innovation):
    m = re.search(rb"type=\"?" + innovation.encode() + rb"\"?\s*\n(\s*progress=(\S+))?", body)
    return None if not m else (float(m.group(2)) if m.group(2) else "complete")


ours, theirs = cultures(load(sys.argv[1])), cultures(load(sys.argv[2]))
n = Counter()
examples = []
for cid, b in ours.items():
    exp, src, typ = val(b, b"exposure_marker"), val(b, b"culture_marker"), val(b, b"exposure_type")
    t = theirs.get(cid)
    if t is None:
        n["culture gone in the re-save"] += 1
        continue
    spr, tsrc = val(t, b"spread_marker"), val(t, b"culture_marker")
    if exp is None:
        n["no exposure_marker; re-save spread_marker " + ("set" if spr else "none")] += 1
        continue
    same = spr == exp
    n[f"{typ}: re-save spread_marker {'SAME' if same else ('other' if spr else 'none')}, "
      f"source {'same' if tsrc == src else ('other' if tsrc else 'none')}"] += 1
    p0, p1 = progress(b, exp), progress(t, exp)
    n[f"progress on our marker: {'kept' if p0 == p1 else 'changed'}"] += 1
    if len(examples) < 6 and not same:
        examples.append((cid, typ, exp, src, spr, tsrc, p0, p1))
for k, v in sorted(n.items()):
    print(f"{v:5}  {k}")
for e in examples:
    print("  ", e)
