"""dna_whole_save: R19 as ruled, applied to a whole migrated save (a prototype of the rule, not the rule).

Interim, by the lead (2026-10-26), so djdarcy has a playable save while R19's design waits for his approval.
Every decision here was ruled before; this only applies them to every character:

  * target layout (c): 1.20 + CFP + EPE + the CFP/EPE patch (djdarcy's eye on Uilleam, 2026-10-25 21:18);
  * by gene and template name (dna_translate.py), defaulting what the target lacks;
  * source layout from the string's length: 712 characters = layout (a) (1.8.1 + the 2023 CFP and EPE; places
    past its 130 genes dropped), 556 = layout (b) (1.20 vanilla: the transplanted reference characters),
    700 = the 967 save's layout, read as (a) at places 0-129 (the 18:35 decode); 696 = already (c), kept;
  * the earliest witness wins (decision G, closed 2026-10-26 01:16): where the 967 save holds the same person
    (same full id, same first name, same birth date) with a face, that face is used; a living character with no
    face in the input gets the 967 face when there is one;
  * portraits_version set to 5 (1.20 ignores stored DNA under 3: the 20:55 addendum).

Prints a report and writes a JSON beside the output. The input is never written.

Usage: python -I tests/one-offs/dna_whole_save.py <in.ck3> <967 witness.ck3> <out.ck3>
"""
from __future__ import annotations

import base64
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
import dna_layout as D  # noqa: E402
import dna_translate as X  # noqa: E402
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

PROJECT = HERE.parents[1]
ORIG = PROJECT / "private" / "data" / "originals"
GAME = Path(r"E:\SteamLibrary\steamapps\common\Crusader Kings III\game")
WS = Path(r"E:\SteamLibrary\steamapps\workshop\content\1158310")
LAYOUT_A = [("vanilla", PROJECT / "private" / "data" / "versions" / "1.8.2" / "game"),
            ("cfp", ORIG / "mods-2023" / "cfp_3.1.11"), ("epe", ORIG / "mods-2023" / "epe_1.6.0")]
LAYOUT_B = [("vanilla", GAME)]
LAYOUT_C = LAYOUT_B + [("cfp", WS / "2220098919"), ("epe", WS / "2507209632"), ("patch", WS / "2996881191")]
SECTIONS = ("living", "dead_unprunable", "characters/dead_prunable")
DNA_ANY = re.compile(rb'dna="([^"]*)"')
FIRST_INDENT = re.compile(rb"[^\n]*\n(\t*)")
_PATS: dict[bytes, tuple] = {}


def pats(indent: bytes) -> tuple:
    """The depth-1 field patterns for an entry whose fields sit at ``indent`` (one tab in 1.8.1 and 1.20, two in
    the 1.5.1.1 saves, whose sections are themselves indented)."""
    if indent not in _PATS:
        t = re.escape(indent)
        _PATS[indent] = (re.compile(rb'\n' + t + rb'dna="([^"]*)"'), re.compile(rb'\n' + t + rb'first_name="([^"]*)"'),
                         re.compile(rb'\n' + t + rb'birth=([\d.]+)'), re.compile(rb'\n' + t + rb"skill=\{[^}\n]*\}"))
    return _PATS[indent]


def b64d(s: bytes) -> bytes:
    return base64.b64decode(s + b"=" * (-len(s) % 4))


def people(g: bytes, with_entries: bool = False) -> dict:
    out = {}
    for sec in SECTIONS:
        try:
            b = gs.locate(g, sec)
        except gs.GamestateError:
            continue
        for e in gs.iter_entries(g, *b.body):
            if not (e.key and e.key.isdigit()):
                continue
            body = g[e.start:e.end]
            fi = FIRST_INDENT.match(body)
            DNA1, NAME, BIRTH, SKILL = pats(fi.group(1) if fi else b"\t")
            m, n, bi = DNA1.search(body), NAME.search(body), BIRTH.search(body)
            row = {"sec": sec, "dna": m.group(1) if m else None, "name": n.group(1) if n else None,
                   "birth": bi.group(1) if bi else None}
            if with_entries:
                row["start"], row["end"] = e.start, e.end
                row["dna_span"] = (e.start + m.start(1), e.start + m.end(1)) if m else None
                sk = SKILL.search(body) or BIRTH.search(body)    # where a recovered face is inserted
                row["skill_end"] = e.start + sk.end() if sk else None
            out[e.key.decode()] = row
    return out


def main():
    src_p, wit_p, out_p = sys.argv[1:4]
    a = D.dna_order(D.load_layout(LAYOUT_A))
    b = D.dna_order(D.load_layout(LAYOUT_B))
    c = D.dna_order(D.load_layout(LAYOUT_C))
    plan_a, plan_b = X.build(a, c), X.build(b, c)
    want = 4 * len(c)
    chars = lambda nbytes: len(base64.b64encode(bytes(nbytes)))      # noqa: E731
    # source string length -> (plan, bytes read): 712 (1.8.1, 133 places) and 700 (967, 131 places) both read
    # as layout (a) at its 130 places; 556 is 1.20 vanilla
    by_len = {chars(532): (plan_a, 4 * len(a)), chars(524): (plan_a, 4 * len(a)), chars(4 * len(b)): (plan_b, 4 * len(b))}

    save = sf.read_save(src_p)
    g = save.gamestate
    wit = people(sf.read_save(wit_p).gamestate)
    ours = people(g, with_entries=True)

    def translate(s: bytes) -> tuple[bytes | None, str]:
        if len(s) == chars(want):
            return s, "already (c)"
        if len(s) not in by_len:
            return None, f"unknown length {len(s)}"
        plan, n = by_len[len(s)]
        return base64.b64encode(plan.apply(b64d(s)[:n])), ("layout (a)" if plan is plan_a else "layout (b)")

    edits = []                                    # (start, end, replacement)
    tally, lengths_in = Counter(), Counter()
    covered = set()
    for cid, r in ours.items():
        w = wit.get(cid)
        same_person = bool(w and w["dna"] and w["name"] == r["name"] and w["birth"] == r["birth"])
        if r["dna_span"]:
            s0, s1 = r["dna_span"]
            covered.add(s0)
            lengths_in[len(r["dna"])] += 1
            src = w["dna"] if same_person else r["dna"]
            new, how = translate(src)
            if new is None:
                tally[f"left as is: {how}"] += 1
                continue
            tally[f"{'967 witness' if same_person else 'own face'}, {how}"] += 1
            edits.append((s0, s1, new))
        elif same_person and r["skill_end"]:
            new, how = translate(w["dna"])
            if new is None:
                tally[f"967 face not usable: {how}"] += 1
                continue
            tally[f"recovered from 967 ({r['sec'].split('/')[-1]}, had no face)"] += 1
            edits.append((r["skill_end"], r["skill_end"], b'\n\tdna="' + new + b'"'))
        elif w and w["dna"] and r["sec"] == "living" and not same_person:
            tally["967 has a face under this id but a different person: not used"] += 1
    other = Counter()
    for m in DNA_ANY.finditer(g):                 # DNA outside the character entries' own depth-1 line
        if m.start(1) in covered:
            continue
        s = m.group(1)
        new, how = translate(s)
        other[how] += 1
        if new is not None and new != s:
            edits.append((m.start(1), m.end(1), new))
    pv = [(m.start(), m.end(), m.group(1) + b"portraits_version=5")
          for m in re.finditer(rb"(?m)^(\t*)portraits_version=3\b", g)]
    edits += pv
    edits.sort(key=lambda e: (e[0], e[1]))
    parts, pos = [], 0
    for s0, s1, rep in edits:
        if s0 < pos:
            raise SystemExit(f"overlapping edits at {s0}")
        parts += [g[pos:s0], rep]
        pos = s1
    parts.append(g[pos:])
    new_g = b"".join(parts)
    save.set_gamestate(new_g)
    res = sf.write_save(save, out_p, force=True)

    after = Counter(len(m.group(1)) for m in DNA_ANY.finditer(new_g))
    report = {
        "input": str(src_p), "witness": str(wit_p), "output": str(out_p),
        "target_layout_genes": len(c), "target_dna_chars": chars(want),
        "plan_a": {"kept": plan_a.kept, "remapped": plan_a.remapped, "defaulted": plan_a.defaulted,
                   "dropped": plan_a.dropped, "templates_lost": plan_a.lost_templates},
        "plan_b": {"kept": plan_b.kept, "remapped": plan_b.remapped, "defaulted": plan_b.defaulted,
                   "dropped": plan_b.dropped, "templates_lost": plan_b.lost_templates},
        "dna_lengths_in_characters": dict(lengths_in), "faces": dict(tally), "other_dna": dict(other),
        "portraits_version_set": len(pv), "dna_lengths_after": dict(after),
    }
    Path(out_p).with_suffix(".dna.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    print(f"wrote {out_p}")


if __name__ == "__main__":
    main()
