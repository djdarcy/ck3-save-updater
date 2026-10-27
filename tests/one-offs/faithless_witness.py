"""faithless_witness: what the game itself does with characters the 1.8.1 save writes no faith for.

R12 gives every character without faith= their house head's rite (else dynasty head's, employer's, player's).
djdarcy (2026-10-26): "I wouldn't mess with it if it isn't set." In 1.20 every character carries rite=, so
"not set" cannot survive the load: the engine picks one. This probe asks the engine, using its own conversions of
the untouched save (same lineage, so character ids are kept):

  for each character with no depth-1 faith= in the original, in each witness save:
    - what faith=/rite= the witness writes for them (or none);
    - whether it equals the faith/rite of their house head IN THAT SAME witness (R12's predictor, judged in the
      engine's own numbering, so no id translation is needed);
  split by living / dead, and by adult / child (age at the save date), plus the named people of decision D.

Control: the same agreement measured on characters that DO carry faith= in the original (how often anyone
shares their house head's faith anyway). R12 is a copy of the engine only if the faithless agreement is high
AND clearly above that base rate.

Usage: python -I tests/one-offs/faithless_witness.py <original gamestate (text)> <witness.ck3> [<witness.ck3> ...]
"""
from __future__ import annotations

import re
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

SECTIONS = ("living", "dead_unprunable", "characters/dead_prunable")
F = {k: re.compile(rb'\n\t' + k + rb'="?([^"\s]+)"?') for k in (b"faith", b"rite", b"dynasty_house", b"birth")}
NAMED = {"50822": "Beidh", "16819727": "the Arab emperor", "64975": "Bruide", "65171": "Aelfweard",
         "16838491": "Gabran", "33558090": "Sesese"}
CHILD_NAMES = ("Laidgenn", "Scáthach", "Tailefhlaith", "Sésésé")


def chars(g: bytes) -> dict[str, dict]:
    out = {}
    for sec in SECTIONS:
        try:
            b = gs.locate(g, sec)
        except gs.GamestateError:
            continue
        for e in gs.iter_entries(g, *b.body):
            if not (e.key and e.key.isdigit()):
                continue
            body = g[e.open:e.close]
            row = {"sec": sec.split("/")[-1]}
            for k, rx in F.items():
                m = rx.search(body)
                row[k.decode()] = m.group(1).decode() if m else None
            fn = re.search(rb'\n\tfirst_name="([^"]*)"', body)
            row["name"] = fn.group(1).decode("utf-8", "replace") if fn else ""
            out[e.key.decode()] = row
    return out


def heads(g: bytes) -> dict[str, str]:
    b = gs.locate(g, "dynasties/dynasty_house")
    out = {}
    for e in gs.iter_entries(g, *b.body):
        m = re.search(rb'\n\t+head_of_house=(\d+)', g[e.open:e.close])
        if m and e.key:
            out[e.key.decode()] = m.group(1).decode()
    return out


def rite_names(g: bytes) -> dict[str, str]:
    out = {}
    for sec in ("rites/database", "religion/faiths"):
        try:
            b = gs.locate(g, sec)
        except gs.GamestateError:
            continue
        for e in gs.iter_entries(g, *b.body):
            body = g[e.open:e.close]
            m = (re.search(rb'\n\t+rite_type="?([^"\s]+)', body) or re.search(rb'\n\t+tag="?([^"\s]+)', body)
                 or re.search(rb'\n\t+template="?([^"\s]+)', body))
            out[e.key.decode()] = m.group(1).decode() if m else "?"
    return out


def date(g: bytes) -> tuple[int, int, int]:
    m = re.search(rb'\ndate=(\d+)\.(\d+)\.(\d+)', g) or re.search(rb'date=(\d+)\.(\d+)\.(\d+)', g)
    return tuple(int(x) for x in m.groups())


def age(birth: str | None, today) -> int | None:
    if not birth:
        return None
    y, mo, d = (int(x) for x in birth.split("."))
    return today[0] - y - ((today[1], today[2]) < (mo, d))


def load(path: str) -> bytes:
    p = Path(path)
    raw = p.read_bytes()
    if raw[:3] == b"SAV" and raw[5:7] == b"00":
        return raw[raw.index(b"\n") + 1:]
    if raw[:3] != b"SAV":
        return raw
    return sf.read_save(path).gamestate


def main():
    t0 = time.time()
    orig_path, *wits = sys.argv[1:]
    g0 = load(orig_path)
    today = date(g0)
    c0 = chars(g0)
    faithless = {i for i, r in c0.items() if r["faith"] is None}
    faithful = set(c0) - faithless
    print(f"original: {len(c0)} characters, {len(faithless)} with no faith= ({time.time() - t0:.0f}s); date {today}")
    for w in wits:
        g = load(w)
        c, hh, names = chars(g), heads(g), rite_names(g)
        key = "rite" if any(r["rite"] for r in list(c.values())[:2000]) else "faith"
        print(f"\n== {Path(w).name}  (field {key}=, {len(c)} characters, {time.time() - t0:.0f}s)")

        def val(i):
            r = c.get(i)
            return r[key] if r else None

        def head_val(i):
            r = c.get(i)
            if not r or not r["dynasty_house"]:
                return None
            h = hh.get(r["dynasty_house"])
            return None if h in (None, i) else val(h)

        for label, pop in (("FAITHLESS in 1.8.1", faithless), ("control: HAS faith= in 1.8.1", faithful)):
            tally = Counter()
            for i in pop:
                if i not in c:
                    tally["gone from witness"] += 1
                    continue
                v, hv = val(i), head_val(i)
                a = age(c0[i]["birth"], today)
                grp = f"{c[i]['sec']}/{'child' if a is not None and a < 16 else 'adult'}"
                if v is None:
                    tally[(grp, "witness writes none")] += 1
                elif hv is None:
                    tally[(grp, "no house head to compare")] += 1
                else:
                    tally[(grp, "= house head's" if v == hv else "differs from house head's")] += 1
            print(f"  {label}: {len(pop)}")
            groups = sorted({k[0] for k in tally if isinstance(k, tuple)})
            for grp in groups:
                same = tally[(grp, "= house head's")]
                diff = tally[(grp, "differs from house head's")]
                none = tally[(grp, "witness writes none")]
                nohead = tally[(grp, "no house head to compare")]
                pct = f"{100 * same / (same + diff):.1f}%" if same + diff else "n/a"
                print(f"    {grp:24} same={same:6} differs={diff:6} none={none:6} no-head={nohead:6}  agreement {pct}")
            if tally["gone from witness"]:
                print(f"    gone from witness: {tally['gone from witness']}")
        print("  named people (1.8.1 faith -> witness value / house head's value):")
        named = dict(NAMED)
        for i, r in c0.items():
            if r["sec"] == "living" and any(n in r["name"] for n in CHILD_NAMES) and i not in named:
                named[i] = r["name"]
        for i, n in named.items():
            if i in c0:
                print(f"    {i:>9} {n[:24]:24} 1.8.1 faith={c0[i]['faith']}  witness={val(i)} ({names.get(val(i) or '', '-')})"
                      f"  house head's={head_val(i)} ({names.get(head_val(i) or '', '-')})")
    print(f"\ndone in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
