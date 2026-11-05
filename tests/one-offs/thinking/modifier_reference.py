"""S4: a reference of every static modifier a game version defines, and a matcher for keys a later version lost.

`export <game_dir> <out.json>`: every top-level block in common/modifiers (key, file, effects) with its English name
and description from localization. `match <old.json> <new.json> key [key ...]`: for each old key, the new modifiers
ranked by (a) shared name words, (b) shared words in the English name and description, (c) the same effect keys
with the same signs -- each scored apart and summed, so a match on concept shows even when the numbers differ.

Usage:
  python -I modifier_reference.py export "E:/SteamLibrary/.../Crusader Kings III/game" private/data/ref/modifiers_1.20.1.2.json
  python -I modifier_reference.py match private/data/ref/modifiers_1.8.2.json private/data/ref/modifiers_1.20.1.2.json KEY ..."""
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
STOP = {"modifier", "county", "character", "the", "a", "of", "and", "in", "is", "to", "this", "for", "with", "has",
        "are", "be", "by", "from", "on", "their", "its", "it", "that", "was", "as", "an", "at", "or", "s", "t", "desc",
        "roco", "dlc", "ep1", "ep2", "ep3", "fp1", "fp2", "fp3", "bp1", "bp2", "tgp", "mpo", "hc", "court", "hold",
        "positive", "negative", "been", "have", "these", "they", "will", "who", "which", "more", "less"}


def strip_comments(t):
    return re.sub(r"#[^\n]*", "", t)


def blocks(text):
    """Top-level `key = { ... }` blocks: (key, body)."""
    i, n = 0, len(text)
    for m in re.finditer(r"(?m)^([A-Za-z0-9_.\-]+)\s*=\s*\{", text):
        if m.start() < i:
            continue
        depth, j = 0, m.end() - 1
        while j < n:
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        i = j + 1
        yield m.group(1), text[m.end():j]


def effects(body):
    out = {}
    for k, v in re.findall(r"(?m)^\s*([a-z_]+)\s*=\s*(-?[\d.]+)\s*$", body):
        try:
            out[k] = float(v)
        except ValueError:
            pass
    return out


def loc(game):
    out = {}
    root = Path(game) / "localization" / "english"
    for p in root.rglob("*.yml"):
        for m in re.finditer(r'^\s*([\w.\-]+):\d*\s+"(.*)"', p.read_text(encoding="utf-8-sig", errors="replace"), re.M):
            out[m.group(1)] = m.group(2)
    return out


def export(game, out):
    game = Path(game)
    names = loc(game)
    ref = {}
    for p in sorted((game / "common" / "modifiers").glob("*.txt")):
        for key, body in blocks(strip_comments(p.read_text(encoding="utf-8-sig", errors="replace"))):
            ref[key] = {"file": p.name, "effects": effects(body), "name": names.get(key, ""),
                        "desc": names.get(key + "_desc", "")}
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(ref, indent=0, ensure_ascii=False), encoding="utf-8")
    print(f"{len(ref)} modifiers -> {out}")


def words(s):
    s = re.sub(r"\[[^\]]*\]|\$[^$]*\$|#\w+|@\w+", " ", s)
    return {w for w in re.findall(r"[a-z]+", s.lower()) if w not in STOP and len(w) > 2 and not w.isdigit()}


def match(old_path, new_path, keys):
    old = json.load(open(old_path, encoding="utf-8"))
    new = json.load(open(new_path, encoding="utf-8"))
    for key in keys:
        o = old.get(key)
        if not o:
            print(f"\n== {key}: not in the old reference")
            continue
        kw, tw = words(key.replace("_", " ")), words(o["name"] + " " + o["desc"])
        sign = {(k, v > 0) for k, v in o["effects"].items()}
        print(f"\n== {key}  \"{o['name']}\"  {o['effects']}")
        scored = []
        for nk, n in new.items():
            a = len(kw & words(nk.replace("_", " ")))
            b = len(tw & words(n["name"] + " " + n["desc"]))
            c = len(sign & {(k, v > 0) for k, v in n["effects"].items()})
            exact = 1 if sign and sign == {(k, v > 0) for k, v in n["effects"].items()} else 0
            s = 2 * a + b + c + exact
            if a or b >= 2:
                scored.append((s, a, b, c, nk, n))
        for s, a, b, c, nk, n in sorted(scored, key=lambda x: -x[0])[:5]:
            print(f"   {s:2} (name {a}, text {b}, effects {c})  {nk:45.45} \"{n['name'][:40]}\"  {n['effects']}")


def catalogue(game, out):
    """Every top-level key in every common/<folder> (one level of subfolders too), with its English name: the
    reference to search any sub-topic against (perks, regiment types, innovations, traits, artifact visuals ...)."""
    game = Path(game)
    names = loc(game)
    cat: dict[str, dict] = {}
    for p in sorted((game / "common").rglob("*.txt")):
        folder = p.parent.relative_to(game / "common").as_posix()
        keys = cat.setdefault(folder, {})
        for key, body in blocks(strip_comments(p.read_text(encoding="utf-8-sig", errors="replace"))):
            keys[key] = {"file": p.name, "name": names.get(key, "") or names.get(key + "_name", ""),
                         "effects": effects(body)}
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(cat, indent=0, ensure_ascii=False), encoding="utf-8")
    print(f"{sum(len(v) for v in cat.values())} keys in {len(cat)} folders -> {out}")


if __name__ == "__main__":
    if sys.argv[1] == "export":
        export(sys.argv[2], sys.argv[3])
    elif sys.argv[1] == "catalogue":
        catalogue(sys.argv[2], sys.argv[3])
    else:
        match(sys.argv[2], sys.argv[3], sys.argv[4:])
