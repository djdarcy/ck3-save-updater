"""Which doctrine groups does each faith (and its main rite) have no doctrine in? (S4 of the faith-edits goal)

Reads the game's doctrine and tenet definitions (each top-level `name = { doctrine_group_type = G ... }`) and a save,
then lists, for the faiths named, the groups with no member on the faith's own lines and on its main rite's data
lines. The game fills an empty group on load (index 0 is the first doctrine), so an empty group in a migrated save
reads in game as that group's first doctrine.
Run: python -I tests/one-offs/doctrine_groups_census.py <save.ck3> <game_dir> [faith_id ...]
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402


def doctrine_groups(game: pathlib.Path) -> dict:
    """doctrine or tenet key -> (group, index, file:line)."""
    out = {}
    for sub in ("doctrine_types", "tenet_types"):
        for f in sorted((game / "common/religion" / sub).glob("*.txt")):
            text = f.read_text(encoding="utf-8-sig", errors="replace")
            heads = [(m.start(), m.group(1), text.count("\n", 0, m.start()) + 1)
                     for m in re.finditer(r"(?m)^(\w+)\s*=\s*\{", text)]
            for i, (pos, key, line) in enumerate(heads):
                body = text[pos:heads[i + 1][0] if i + 1 < len(heads) else len(text)]
                g = re.search(r"(?m)^\s*doctrine_group_type\s*=\s*(\w+)", body)
                ix = re.search(r"(?m)^\s*index\s*=\s*(\d+)", body)
                if g:
                    out[key] = (g.group(1), int(ix.group(1)) if ix else None, f"{f.name}:{line}")
    return out


def main(save, game, faith_ids):
    g = read_save(save).gamestate
    groups = doctrine_groups(pathlib.Path(game))
    members = {}
    for k, (grp, ix, where) in groups.items():
        members.setdefault(grp, []).append((ix if ix is not None else 99, k))
    print(f"{len(groups)} doctrines/tenets in {len(members)} groups")
    fdb, rdb = gs.locate(g, "faiths/database"), gs.locate(g, "rites/database")
    F = {e.key.decode(): e for e in gs.iter_entries(g, fdb.open + 1, fdb.close)}
    R = {e.key.decode(): e for e in gs.iter_entries(g, rdb.open + 1, rdb.close)}
    for fid in faith_ids:
        fb = g[F[fid].open:F[fid].close]
        mr = re.search(rb"(?m)^\t\t\tmain_rite=(\d+)", fb)
        rb_ = g[R[mr.group(1).decode()].open:R[mr.group(1).decode()].close] if mr else b""
        have = {m.decode() for m in re.findall(rb"(?m)^\t\t\t(?:tenet|doctrine)=(\S+)", fb)}
        have |= {m.decode() for m in re.findall(rb"(?m)^\t\t\t\t(?:tenet|doctrine)=(\S+)", rb_)}
        unknown = sorted(k for k in have if k not in groups)
        empty = sorted(grp for grp in members if not any(k in have for _, k in members[grp]))
        print(f"\nfaith {fid} (main rite {mr.group(1).decode() if mr else '?'}): {len(have)} keys, "
              f"{len(empty)} empty groups, {len(unknown)} keys the game does not define")
        for grp in empty:
            first = sorted(members[grp])[0][1]
            print(f"  empty: {grp:42s} first = {first}")
        for k in unknown:
            print(f"  not a game doctrine: {k}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:] or ["103"])
