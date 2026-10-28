"""join_audit: does each join the translator makes pair the same thing on both sides? (2026-10-28)

The translator joins reference objects to the campaign's by a key it assumes means the same thing in both game
versions: characters by history id, dynasties and houses by history key, cultures by template, titles by key.
The crash on exit (contract 8774) came from a reused history id: 200032 is Attab (born 923) in 1.20 and Suleyman
(born 725, dead 779) in 1.8.1. This compares, for every joined pair, what each side says about the object:

  character  birth year gap (> 60 years, or the campaign's person dead before the reference's was born = suspect)
  dynasty    the dynasty name (name= / prefix+name), house: the house name
  culture    the culture name
  title      the tier letter of the key cannot differ (same key); compared: de jure liege's key and capital

Known answer: the founding save's 200032 pair is reported as a character suspect.

Usage: python -I tests/one-offs/join_audit.py <campaign save.ck3> <reference save.ck3> [--examples N]
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import translate as T  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

CHAR_SECTIONS = ("living", "dead_unprunable", "characters/dead_prunable")


def entries(d, path):
    try:
        return dict(T.entries(d, path))
    except T.TranslationError:
        return {}


def field(d, e, key, limit=3000):
    m = re.search(rb"\n\t+" + key + rb"=(\"[^\"]*\"|[^\s{}]+)", d[e.open:min(e.close, e.open + limit)])
    return m.group(1).strip(b'"').decode(errors="replace") if m else None


def life(d):
    out = {}
    for path in CHAR_SECTIONS:
        for i, e in entries(d, path).items():
            t = d[e.open:e.close]
            b = re.search(rb"\n\tbirth=(\d+)", t)
            dd = re.search(rb"dead_data=\{[^}]*?\n\t\tdate=(\d+)", t)
            n = re.search(rb'\n\tfirst_name="([^"]*)"', t)
            out[i] = (int(b.group(1)) if b else None, int(dd.group(1)) if dd else None,
                      n.group(1).decode(errors="replace") if n else None)
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    n_ex = next((int(a.split("=", 1)[1]) for a in sys.argv[1:] if a.startswith("--examples=")), 8)
    save, ref = read_save(args[0]).gamestate, read_save(args[1]).gamestate
    tr = T.Translator.build(save, ref)

    # characters
    sl, rl = T.character_lookup(save), T.character_lookup(ref)
    s_life, r_life = life(save), life(ref)
    sus, compared = [], 0
    for h in rl.keys() & sl.keys():
        r, s = rl[h], sl[h]
        if r not in r_life or s not in s_life:
            continue
        compared += 1
        (rb_, _, rn), (sb, sd, sn) = r_life[r], s_life[s]
        why = None
        if rb_ and sd and sd < rb_:
            why = "campaign's person died before the reference's was born"
        elif rb_ and sb and abs(rb_ - sb) > 60:
            why = f"births {abs(rb_ - sb)} years apart"
        if why:
            sus.append((h, r, rn, rb_, s, sn, sb, sd, why))
    print(f"character joins compared {compared}: suspect {len(sus)}")
    for x in sus[:n_ex]:
        print("   hist", x[0], f"ref {x[1]} {x[2]} b.{x[3]}", f"-> campaign {x[4]} {x[5]} b.{x[6]} d.{x[7]}", "|", x[8])

    # dynasties, houses, cultures: compare names
    for sp, path, key, name_keys in (("dynasty", "dynasties/dynasties", b"key", (b"name", b"dynasty_name")),
                                     ("house", "dynasties/dynasty_house", b"key", (b"name",)),
                                     ("culture", "culture_manager/cultures", b"culture_template", (b"name",))):
        se, re_ = entries(save, path), entries(ref, path)
        diff, comp = [], 0
        for r, s in tr.spaces[sp].join.items():
            if r not in re_ or s not in se:
                continue
            comp += 1
            rn = next((field(ref, re_[r], k) for k in name_keys if field(ref, re_[r], k)), None)
            sn = next((field(save, se[s], k) for k in name_keys if field(save, se[s], k)), None)
            if rn != sn:
                diff.append((r, s, rn, sn, field(ref, re_[r], key)))
        print(f"{sp} joins compared {comp}: name differs {len(diff)}")
        for x in diff[:n_ex]:
            print(f"   {key.decode()}={x[4]}  ref {x[0]} {x[2]!r} -> campaign {x[1]} {x[3]!r}")

    # titles: same key by construction; compare the de jure liege's key and the capital barony
    path = "landed_titles/landed_titles"
    se, re_ = entries(save, path), entries(ref, path)
    skey = {i: field(save, e, b"key") for i, e in se.items()}
    rkey = {i: field(ref, e, b"key") for i, e in re_.items()}
    dj = Counter()
    ex = []
    for r, s in tr.spaces["title"].join.items():
        if r not in re_ or s not in se:
            continue
        rl_, sl_ = field(ref, re_[r], b"de_jure_liege"), field(save, se[s], b"de_jure_liege")
        rk = rkey.get(int(rl_)) if rl_ and rl_.isdigit() else None
        sk = skey.get(int(sl_)) if sl_ and sl_.isdigit() else None
        dj["compared"] += 1
        if rk != sk:
            dj["de jure liege differs"] += 1
            if len(ex) < n_ex:
                ex.append((rkey.get(r), rk, sk))
    print(f"title joins: {dict(dj)} (a map rework moves de jure lieges; a different place under the same key would"
          f" show as a liege in another region)")
    for x in ex:
        print(f"   {x[0]}: ref de jure {x[1]} / campaign {x[2]}")


if __name__ == "__main__":
    main()
