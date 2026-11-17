"""How well do the game's English display names cover a save's holy sites, faiths and rites? (DWP: display-name lookup)

Reads every localization/english/**/*.yml (` key:0 "Value" # comment`), then for the save's holy sites
(`holy_site_<type>_name`), faiths (their tag) and rites (their rite_type) counts: names found, accented names,
values that reference other keys ($x$ or [..]), and display names that collide once case, accents and punctuation
are dropped. Run: python -I tests/one-offs/display_names_census.py <save.ck3> <game_dir>
"""
import pathlib
import re
import sys
import unicodedata

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from ck3_save_migrator import faith_lookup as F  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

LINE = re.compile(r'^\s*([\w.\-]+):\d*\s*"(.*)"\s*(?:#.*)?$')


def load_loc(game: pathlib.Path) -> dict:
    out = {}
    for f in sorted((game / "localization" / "english").rglob("*.yml")):
        for line in f.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            m = LINE.match(line)
            if m and m.group(1) not in out:
                out[m.group(1)] = m.group(2)
    return out


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in s if not unicodedata.combining(c)).lower())


def report(kind, keys, loc_key, loc):
    names = {k: loc.get(loc_key(k)) for k in keys}
    found = {k: v for k, v in names.items() if v}
    accented = [v for v in found.values() if fold(v) != re.sub(r"[^a-z0-9]", "", v.lower())]
    refs = {k: v for k, v in found.items() if "$" in v or "[" in v}
    by = {}
    for k, v in found.items():
        by.setdefault(fold(v), []).append(k)
    clash = {n: ks for n, ks in by.items() if len(ks) > 1}
    keyclash = [(k, by[fold(k)]) for k in keys if fold(k) in by and k not in by[fold(k)]]
    print(f"\n{kind}: {len(keys)} in the save, {len(found)} with an English name, {len(accented)} accented, "
          f"{len(refs)} referencing other keys, {len(clash)} folded-name collisions, "
          f"{len(keyclash)} names equal to ANOTHER entry's key")
    print("  missing:", sorted(set(keys) - set(found))[:10])
    print("  accented:", accented[:8])
    print("  refs:", list(refs.items())[:5])
    print("  collisions:", list(clash.items())[:8])
    print("  name==other key:", keyclash[:5])


def main(save, game):
    g = read_save(save).gamestate
    loc = load_loc(pathlib.Path(game))
    print(f"{len(loc)} English localisation keys")
    report("holy sites", sorted(set(F.holy_sites(g).values())), lambda k: f"holy_site_{k}_name", loc)
    faiths = F.faiths(g)
    report("faiths (by tag; custom faiths carry their own name)",
           sorted({f.tag for f in faiths.values() if f.tag and not f.name}), lambda k: k, loc)
    report("rites (by rite_type)", sorted({r.rite_type for r in F.rites(g).values() if r.rite_type}), lambda k: k, loc)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
