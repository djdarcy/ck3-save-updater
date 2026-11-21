"""S4 (goal 2026-11-20__16-02-08; board U35; EMERGING E2): which duchies have a market in a fresh 1.21 game but not in
the converted campaign (922 against 902), and what do they have in common?

Markets (trade_markets/database) carry `duchy=<title id>` and `location=<title id>`; ids differ between saves, so
both are mapped to title keys through landed_titles. For each duchy the fresh game has and the campaign lacks, it
prints the duchy's key, whether the campaign has that duchy title at all, its holder, and its de jure counties in the
campaign (how many, how many held); and the same for any duchy the campaign has and the fresh game lacks.

Usage: python -I tests/one-offs/thinking/markets_trace.py <ref.ck3> <campaign.ck3>
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402


def titles(g):
    out = {}
    for e in gs.iter_entries(g, *gs.locate(g, "landed_titles/landed_titles").body):
        if not e.key:
            continue
        b = g[e.open:e.close]
        k = re.search(rb'\tkey="?([a-z_0-9]+)', b)      # 1.21 writes "type=...\tkey=..." on one line
        if k:
            out[e.key.decode()] = (k.group(1).decode(), b)
    return out


def markets(g, t):
    out = {}
    for e in gs.iter_entries(g, *gs.locate(g, "trade_markets/database").body):
        b = g[e.open:e.close]
        d = re.search(rb"\n\t+duchy=(\d+)", b)          # database fields sit three tabs in
        loc = re.search(rb"\n\t+location=(\d+)", b)
        if d:
            out[t[d.group(1).decode()][0]] = t.get(loc.group(1).decode(), ("?",))[0] if loc else "?"
    return out


def describe(key, t_by_key, t):
    if key not in t_by_key:
        return "no such title in this save"
    b = t_by_key[key]
    holder = re.search(rb"\tholder=(\d+)", b)
    de_jure = re.search(rb"\tde_jure_vassals=\{([^}]*)\}", b)
    vass = re.findall(rb"\d+", de_jure.group(1)) if de_jure else []
    counties = [t[v.decode()] for v in vass if v.decode() in t]
    held = sum(1 for _, cb in counties if re.search(rb"\tholder=\d+", cb))
    return (f"holder {holder.group(1).decode() if holder else 'none'}; de jure counties {len(counties)} "
            f"({held} held): {[k for k, _ in counties][:6]}")


def main(ref_path, camp_path):
    out = []
    for p in (ref_path, camp_path):
        g = read_save(p).gamestate
        t = titles(g)
        out.append((g, t, {k: b for k, b in t.values()}, markets(g, t)))
    (_, tr, kr, mr), (_, tc, kc, mc) = out
    print(f"markets: ref {len(mr)}, campaign {len(mc)}")
    only_ref = sorted(set(mr) - set(mc))
    only_camp = sorted(set(mc) - set(mr))
    print(f"\nduchies with a market in ref only ({len(only_ref)}):")
    for k in only_ref:
        print(f"  {k} (ref location {mr[k]})")
        print(f"     ref:      {describe(k, kr, tr)}")
        print(f"     campaign: {describe(k, kc, tc)}")
    print(f"\nduchies with a market in the campaign only ({len(only_camp)}):")
    for k in only_camp:
        print(f"  {k}: campaign {describe(k, kc, tc)}; ref {describe(k, kr, tr)}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
