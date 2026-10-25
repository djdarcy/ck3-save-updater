"""U12: the per-version definition table for CK3, from each version's script files (fetched by DepotDownloader into
private/data/versions/<version>/game/...). For every version: the keys each common/ folder defines (top level;
nested for landed_titles, genes and game rules), the culture keys, the province count; then, between consecutive
versions, what was added and removed. Optional word timeline: which versions' scripts mention a word at all.

Usage: python -I tests/one-offs/version_table.py <versions dir> [--json out.json] [--words w1,w2,...]
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ORDER = ["1.8.2", "1.9.2", "1.10.2", "1.11.5", "1.12.5", "1.13.2", "1.14.3", "1.15.0", "1.16.2", "1.17.1",
         "1.18.4", "1.19.0", "1.20.0", "public"]
COMMENT = re.compile(r"#[^\n]*")
TOP = re.compile(r"(?m)^([A-Za-z0-9_@][\w.\-:@']*)[ \t]*=")
DEPTH1 = re.compile(r"(?m)^\t([A-Za-z_][\w.\-']*)[ \t]*=[ \t]*\{")
TITLE = re.compile(r"(?<![\w.])([hekdcb]_[\w\-']+)\s*=\s*\{")


def read(p: Path) -> str:
    return COMMENT.sub("", p.read_bytes().removeprefix(b"\xef\xbb\xbf").decode("utf-8", "replace"))


def definitions(game: Path) -> dict[str, set[str]]:
    """category -> keys. Categories are common/ folders relative to common/, plus a few nested kinds."""
    out = defaultdict(set)
    common = game / "common"
    for f in common.rglob("*.txt"):
        rel = f.parent.relative_to(common).as_posix()
        text = read(f)
        if rel.startswith("landed_titles"):
            out["titles"] |= set(TITLE.findall(text))
            continue
        out[rel] |= set(TOP.findall(text))
        if rel.startswith("genes"):
            out["genes (nested)"] |= set(DEPTH1.findall(text))
        if rel.startswith("game_rules"):
            out["game rule options"] |= set(DEPTH1.findall(text))
    d = game / "map_data" / "definition.csv"
    if d.exists():
        ids = [int(m.group(1)) for m in re.finditer(r"(?m)^(\d+);", d.read_text(encoding="utf-8", errors="replace"))]
        out["provinces (definition.csv ids)"] = {str(i) for i in ids}
    return out


def words_timeline(versions: dict[str, Path], words: list[str]) -> dict[str, list[str]]:
    hits = {w: [] for w in words}
    pats = {w: re.compile(r"(?<![\w])" + re.escape(w) + r"(?![\w])") for w in words}
    for v, game in versions.items():
        found = set()
        for f in list((game / "common").rglob("*.txt")) + list((game / "events").rglob("*.txt")):
            t = f.read_text(encoding="utf-8", errors="replace")
            found |= {w for w, p in pats.items() if w not in found and p.search(t)}
            if len(found) == len(words):
                break
        for w in words:
            hits[w].append(v if w in found else "-")
    return hits


def main():
    root = Path(sys.argv[1])
    versions = {v: root / v / "game" for v in ORDER if (root / v / "game" / "common").is_dir()}
    defs = {v: definitions(g) for v, g in versions.items()}
    cats = sorted({c for d in defs.values() for c in d})
    table = {"versions": list(versions), "steps": []}
    print(f"versions: {', '.join(versions)}")
    names = list(versions)
    for a, b in zip(names, names[1:]):
        step = {"from": a, "to": b, "changes": {}}
        lines = []
        for c in cats:
            old, new = defs[a].get(c, set()), defs[b].get(c, set())
            add, rem = sorted(new - old), sorted(old - new)
            if add or rem:
                step["changes"][c] = {"added": add, "removed": rem}
                if c.startswith("provinces"):
                    lines.append(f"    {c}: +{len(add)} -{len(rem)} (max {max(map(int, new)) if new else 0})")
                elif len(add) + len(rem) and (c in ("titles", "culture/cultures", "genes (nested)", "game rule options",
                                                   "modifiers", "on_action", "dynasties") or len(rem) >= 5):
                    lines.append(f"    {c}: +{len(add)} -{len(rem)}" + (f"; removed e.g. {rem[:5]}" if rem else ""))
        table["steps"].append(step)
        total_add = sum(len(x["added"]) for x in step["changes"].values())
        total_rem = sum(len(x["removed"]) for x in step["changes"].values())
        print(f"{a} -> {b}: {total_add:,} added, {total_rem:,} removed across {len(step['changes'])} categories")
        print("\n".join(lines[:14]))
    if "--words" in sys.argv:
        words = sys.argv[sys.argv.index("--words") + 1].split(",")
        tl = words_timeline(versions, words)
        table["words"] = tl
        print("word timeline (version where the scripts mention it, '-' where not):")
        for w, row in tl.items():
            print(f"  {w:24} {' '.join(x if x != '-' else '·' for x in row)}")
    if "--json" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--json") + 1])
        out.write_text(json.dumps(table, indent=1), encoding="utf-8")
        print(f"table written: {out}")


if __name__ == "__main__":
    main()
