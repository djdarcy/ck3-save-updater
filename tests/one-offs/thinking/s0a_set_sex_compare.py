"""MEASURE S0(a), step 2: what did the game do with a character whose female=yes was removed? (control vs edited)

Inputs: the edited copy we wrote (input), and the game's own console re-saves of the control (unedited) and the edited
copy, both loaded and saved at once in -debug_mode (plain-text saves, header kind 00: read as raw text here).
Prints, for the character: sex key in each; the entry's keys that differ between control re-save and edited
re-save; DNA equal to the input or not; and her position in every heir={ } list in each re-save, with the counts of
lists where it moved. Read-only.

Prediction (in s0a_set_sex_copy.py's docstring): she stays male; DNA unchanged; only her entry and sex-derived
values (heir order) differ between the two re-saves.

Run: python -I tests/one-offs/thinking/s0a_set_sex_compare.py <edited input.ck3> <control_resaved.ck3> <male_resaved.ck3> <id>
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator.savefile import read_save  # noqa: E402

inp, ctrl, male, cid = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]


def text(p: Path) -> bytes:
    raw = p.read_bytes()
    if raw[:7] == b"SAV0100" or raw[:3] == b"SAV" and raw[3:7] != b"0102":
        pass
    try:
        return read_save(p).gamestate
    except Exception:
        return raw                                          # a plain-text console save: the whole file is text


def entry(g: bytes, cid: str) -> bytes:
    living = g.find(b"\nliving={")
    m = re.compile(rb"(?m)^" + cid.encode() + rb"=\{").search(g, living)
    if not m:
        return b""
    depth, i = 0, m.end() - 1
    while i < len(g):
        c = g[i:i + 1]
        if c == b"{": depth += 1
        elif c == b"}":
            depth -= 1
            if depth == 0: return g[m.start():i + 1]
        i += 1
    return b""


def keys(body: bytes) -> dict:
    out = {}
    for m in re.finditer(rb"(?m)^\t([a-z_]+)=(.*)$", body):
        out.setdefault(m.group(1).decode(), m.group(2).decode("utf-8", "replace")[:80])
    return out


def heirs(g: bytes, cid: str) -> list[tuple[int, int]]:
    res = []
    for m in re.finditer(rb"heir=\{([^}]*)\}", g):
        ids = m.group(1).split()
        if cid.encode() in ids:
            res.append((m.start(), ids.index(cid.encode())))
    return res


gi, gc, gm = text(inp), text(ctrl), text(male)
ei, ec, em = entry(gi, cid), entry(gc, cid), entry(gm, cid)
print(f"entry bytes: input {len(ei)}, control re-save {len(ec)}, edited re-save {len(em)}")
for name, e in (("input", ei), ("control", ec), ("edited", em)):
    print(f"  {name:8} female={'yes' if re.search(rb'(?m)^\tfemale=yes', e) else 'absent'}")
kc, km = keys(ec), keys(em)
diff = sorted(k for k in set(kc) | set(km) if kc.get(k) != km.get(k))
print("depth-1 keys differing control vs edited:", diff)
for k in diff:
    print(f"   {k}: control={kc.get(k)!r}  edited={km.get(k)!r}")
dna = lambda e: (re.search(rb'(?m)^\tdna="([^"]*)"', e) or [None, b""])[1]
print("DNA: input == edited re-save:", dna(ei) == dna(em), "| control == edited:", dna(ec) == dna(em))
hc, hm = heirs(gc, cid), heirs(gm, cid)
pc, pm = Counter(p for _, p in hc), Counter(p for _, p in hm)
print(f"heir lists naming {cid}: control {len(hc)}, edited {len(hm)}")
print("  positions (0 = first heir) control:", sorted(pc.items())[:12])
print("  positions edited:               ", sorted(pm.items())[:12])
print(f"occurrences of {cid} anywhere: input {len(re.findall(rb'(?<![0-9])' + cid.encode() + rb'(?![0-9])', gi))}, "
      f"control {len(re.findall(rb'(?<![0-9])' + cid.encode() + rb'(?![0-9])', gc))}, "
      f"edited {len(re.findall(rb'(?<![0-9])' + cid.encode() + rb'(?![0-9])', gm))}")
