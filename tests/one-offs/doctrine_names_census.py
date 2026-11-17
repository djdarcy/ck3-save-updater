"""Display names of tenets, doctrines and doctrine groups: coverage and collisions. (multi-word names goal, S2)

For every tenet and doctrine faith_rules reads, and every doctrine group, try the localisation keys `<key>_name`
and `<key>`, then count names found, accented, `$ref$`, and collisions once folded -- within all doctrines, within
each group, and between tenets. Also counts how many collisions a group-qualified name ("<group name>: <name>")
resolves. Run: python -I -X utf8 tests/one-offs/doctrine_names_census.py <game_dir>
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from ck3_save_migrator import faith_rules  # noqa: E402
from display_names_census import fold, load_loc  # noqa: E402


def name_of(loc, key):
    for k in (f"{key}_name", key):
        v = loc.get(k)
        if v:
            m = re.fullmatch(r"\$(\w+)\$", v)
            return (loc.get(m.group(1)) or v) if m else v, k
    return None, None


def main(game):
    game = pathlib.Path(game)
    loc = load_loc(game)
    rules = faith_rules.load(str(game))
    for kind, keys in (("tenets", sorted(rules.tenets)), ("doctrines", sorted(rules.doctrines)),
                       ("groups", sorted(rules.group_category))):
        found, via, missing = {}, {}, []
        for k in keys:
            n, k2 = name_of(loc, k)
            if n:
                found[k], via[k] = n, k2
            else:
                missing.append(k)
        by = {}
        for k, n in found.items():
            by.setdefault(fold(n), []).append(k)
        clash = {n: ks for n, ks in by.items() if len(ks) > 1}
        pattern = {p: sum(1 for k in via if via[k] == (k + p if p else k)) for p in ("_name", "")}
        print(f"\n{kind}: {len(keys)}; named {len(found)} ({pattern}); missing {len(missing)} {missing[:6]}; "
              f"refs left {sum('$' in n for n in found.values())}; folded collisions {len(clash)}")
        for n, ks in list(clash.items())[:12]:
            print(f"  {n}: {ks}")
        if kind == "doctrines":
            groups = {k: rules.doctrines[k].group for k in found}
            within = sum(1 for ks in clash.values() if len({groups[k] for k in ks}) < len(ks))
            gname = {g: name_of(loc, g)[0] or g for g in set(groups.values())}
            qual = {}
            for k, n in found.items():
                qual.setdefault(fold(f"{gname[groups[k]]}: {n}"), []).append(k)
            print(f"  collisions inside one group: {within}; after qualifying with the group's name: "
                  f"{sum(len(v) > 1 for v in qual.values())}")
            print("  e.g.", [(f"{gname[groups[k]]}: {found[k]}", k) for k in found if 'pilgrimage' in k][:3])


if __name__ == "__main__":
    main(sys.argv[1])
