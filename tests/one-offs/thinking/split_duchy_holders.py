"""djdarcy (2026-11-20): "Did any of our people in our family control those duchies that were split? And if so when we
upgraded our save did we get those duchies?" For each old duchy that loses counties to a new duchy (the 1.20 side: the
reference's county->duchy against the campaign's; the 1.21 side: the 11 new duchies' counties), print its holder and
whether he is of the player's house or dynasty, and who holds the moved counties.

Usage: python -I tests/one-offs/thinking/split_duchy_holders.py <ref.ck3> <campaign.ck3>
"""
import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[0]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import dejure_diff as D  # noqa: E402
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402


def people(g):
    house_of, name_of = {}, {}
    for e in gs.iter_entries(g, *gs.locate(g, "living").body):
        if not e.key:
            continue
        b = g[e.open:min(e.close, e.open + 3000)]
        h = re.search(rb"\n\tdynasty_house=(\d+)", b)
        n = re.search(rb'\n\tfirst_name="([^"]*)"', b)
        house_of[e.key.decode()] = h.group(1).decode() if h else None
        name_of[e.key.decode()] = n.group(1).decode() if n else "?"
    dyn_of = {}
    for e in gs.iter_entries(g, *gs.locate(g, "dynasties/dynasty_house").body):
        if e.key:
            d = re.search(rb"\n\t+dynasty=(\d+)", g[e.open:min(e.close, e.open + 2000)])
            dyn_of[e.key.decode()] = d.group(1).decode() if d else None
    return house_of, name_of, dyn_of


def main(ref_path, camp_path):
    rg, cg = read_save(ref_path).gamestate, read_save(camp_path).gamestate
    ref_cd, _ = D.county_duchy(rg)
    camp_cd, camp_titles = D.county_duchy(cg)
    house_of, name_of, dyn_of = people(cg)
    pc = re.search(rb"\nplayed_character=\{[^}]*?\n\tcharacter=(\d+)", cg) or re.search(rb"currently_played_characters=\{\s*(\d+)", cg)
    player = pc.group(1).decode() if pc else None
    p_house = house_of.get(player)
    p_dyn = dyn_of.get(p_house)
    print(f"player {player} ({name_of.get(player)}), house {p_house}, dynasty {p_dyn}")

    def holder(key):
        b = camp_titles.get(key, b"")
        m = re.findall(rb"\n\tholder=(\d+)", b)
        return m[-1].decode() if m else None

    def who(cid):
        if cid is None:
            return "unheld"
        h = house_of.get(cid)
        tag = "THE PLAYER" if cid == player else ("player's house" if h and h == p_house else
                                                    ("player's dynasty" if h and dyn_of.get(h) == p_dyn else "other"))
        return f"{cid} {name_of.get(cid, '?')} [{tag}]"

    moves = collections.defaultdict(list)          # (old duchy, new duchy) -> counties
    for c, rd in ref_cd.items():
        cd = camp_cd.get(c)
        if cd and rd and cd != rd and (rd not in camp_titles or not any(v == rd for v in camp_cd.values())):
            moves[(cd, rd)].append(c)
    print(f"old duchies losing counties to a duchy the campaign has empty or lacks: {len({o for o, _ in moves})}")
    ours = 0
    for (old, new), cs in sorted(moves.items()):
        h = holder(old)
        tag = who(h)
        if "player" in tag.lower():
            ours += 1
        ch = collections.Counter(who(holder(c)).split(" [")[-1].rstrip("]") for c in cs)
        print(f"  {old} (held by {tag}) -> {new} {'(absent)' if new not in camp_titles else '(empty)'}: "
              f"{len(cs)} counties {cs[:4]}; county holders {dict(ch)}")
    print(f"held by the player or his family: {ours}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
