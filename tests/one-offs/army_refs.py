"""army_refs: does every army, unit and army regiment of a save point at things that exist, and point back?

2026-10-27: the 20 March 989 stop is the AI's army planner (ck3+0x19f93e0) splitting an army group without end and
allocating a new group each pass (130 GB in ten minutes). The split shrinks only when the armies it moves have
strength; an army whose reference fails to resolve takes the engine's default object instead, and a group of those
never shrinks. This probe lists every reference of the armies/units/army_regiments sections that does not resolve.

Checks: army.unit is a unit whose army= is that army; army.commander and unit.owner and regiment.knight are living
characters; army.regiments are army_regiments whose army= is that army; unit.location/prev are provinces; every
regiment's army= is an army; unit.army is an army.

Usage: python -I tests/one-offs/army_refs.py <save.ck3> [examples]
"""
from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402


def field(t: bytes, k: str) -> str | None:
    m = re.search(rb"(?m)^\s*" + k.encode() + rb"=(\S+)", t)
    return m.group(1).decode() if m else None


def ids(g: bytes, path: str) -> dict[str, bytes]:
    try:
        b = gs.locate(g, path)
    except Exception:
        return {}
    return {e.key.decode(): g[e.open:e.close] for e in gs.iter_entries(g, *b.body) if e.key}


def load(path: str) -> bytes:
    """A normal save through read_save; a plain-text save (header kind 00, written under -debug_mode) by
    dropping its header line (as face_check.py does)."""
    raw = Path(path).read_bytes()
    if raw[:3] == b"SAV" and raw[5:7] == b"00":
        return raw[raw.index(b"\n") + 1:]
    return sf.read_save(path).gamestate


def main():
    save = sys.argv[1]
    nex = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    g = load(save)
    m = re.search(rb"\ndate=(\S+)", g[:20000])
    print("save date:", m.group(1).decode() if m else "?")
    living = set(ids(g, "living"))
    armies = ids(g, "armies/armies")
    regs = ids(g, "armies/army_regiments")
    units = {e.key.decode(): g[e.open:e.close] for e in gs.iter_entries(g, *gs.find_section(g, "units").body) if e.key}
    provinces = set(ids(g, "provinces"))
    bad = defaultdict(list)

    def flag(kind, who, what):
        bad[kind].append(f"{who} -> {what}")

    for aid, t in armies.items():
        u = field(t, "unit")
        if u is not None:
            if u not in units:
                flag("army.unit is not a unit", aid, u)
            elif field(units[u], "army") != aid:
                flag("army.unit's army= is another army", aid, f"{u} (army={field(units[u], 'army')})")
        c = field(t, "commander")
        if c is not None and c not in living:
            flag("army.commander not living", aid, c)
        m = re.search(rb"regiments=\{([^}]*)\}", t)
        for r in (m.group(1).split() if m else []):
            r = r.decode()
            if not r.isdigit():                   # a nested regiments={ { ... } } form, not an id list
                break
            if r not in regs:
                flag("army.regiments entry is not a regiment", aid, r)
            elif field(regs[r], "army") != aid:
                flag("regiment listed by an army names another army", aid, f"{r} (army={field(regs[r], 'army')})")
    pools = ids(g, "armies/regiments")            # the soldier pools army regiments draw from (chunks={ {regiment=N} })
    strength = Counter()
    for rid, t in regs.items():
        for p in re.findall(rb"regiment=(\d+)", t):
            if p.decode() not in pools:
                flag("regiment chunk names a missing armies/regiments pool", rid, p.decode())
        cur = re.search(rb"current=([\d.]+)", t)
        size = re.search(rb"cached=\{\s*size=(\d+)", t)
        strength[field(t, "army")] += float(cur.group(1)) if cur else (int(size.group(1)) if size else 0)
    for aid, t in armies.items():
        if strength[aid] <= 0:
            flag("army with no soldiers", aid, f"commander={field(t, 'commander')} unit={field(t, 'unit')}")
    for rid, t in regs.items():
        a = field(t, "army")
        if a is not None and a not in armies:
            flag("regiment.army is not an army", rid, a)
        k = field(t, "knight")
        if k is not None and k not in living:
            flag("regiment.knight not living", rid, k)
    for uid, t in units.items():
        a = field(t, "army")
        if a is not None and a not in armies:
            flag("unit.army is not an army", uid, a)
        o = field(t, "owner")
        if o is not None and o not in living:
            flag("unit.owner not living", uid, o)
        for k in ("location", "prev"):
            p = field(t, k)
            if p is not None and provinces and p not in provinces:
                flag(f"unit.{k} not a province", uid, p)
    print(f"{save}: {len(armies)} armies, {len(units)} units, {len(regs)} regiments, {len(living):,} living")
    print("unit types:", dict(Counter(field(t, "type") for t in units.values())))
    if not bad:
        print("every reference resolves")
    for kind, rows in sorted(bad.items(), key=lambda x: -len(x[1])):
        print(f"{len(rows):>6}  {kind}   e.g. " + "; ".join(rows[:nex]))


if __name__ == "__main__":
    main()
