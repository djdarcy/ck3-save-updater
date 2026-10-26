"""shape_diff: the shape of three gamestates at one date, compared by counts and key sets only.

Prototype of a future library's ``shape()`` and ``keys()`` (stdlib plus this project's ``gamestate`` /
``savefile`` / ``lint.SectionIndex``). There is NO entry-level alignment: an entry is read for its key, never for
its content -- with one exception, titles, whose identity is the ``key=`` scalar at the head of each entry.

Witnesses (all at 987.10.27):
  ref    the vanilla 1.20 reference save, the transplant's source;
  chain  the campaign loaded by the engine itself through 1.18.4 -> 1.19.0 -> 1.20.1.2 (no transplant);
  ours   our migrated output.

``shape(g)``  -> {path: Shape}: every top-level section, and every named block one level down (the "databases"),
                with the entries counted by kind: numeric keys (an id database), title-key-like keys, other bare
                keys, anonymous list items, bare list values; distinct keys kept as a set.
``keys()``     the key sets the comparison needs, translated into ours's id space by key arithmetic alone:
  titles      by key (title id -> key from each title's key=), the transplant offset = the mode of
              index(ours id) - index(ref id) over shared keys; new-map titles = shared keys at that offset;
  characters  campaign characters keep their ids, so ours & chain = the campaign; R13's offset = 1 + the highest
              index among them; a ref id translates to (generation kept) index + offset; new-map = translated ids
              present in ours;
  provinces   an identity space.

Usage: python -I tests/one-offs/shape_diff.py <ref.ck3> <chain.ck3> <ours.ck3> [--json out.json] [--md out.md]
"""
from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import lint as L  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

LOW, GEN, NONE = 0xFFFFFF, 0xFF000000, 0xFFFFFFFF
TITLE_KEY = re.compile(r"^[bcdkehx]_[\w\-']+$")
SCALAR_LIMIT = 32 * 1024 * 1024          # iter_children tokenises a whole body: only below this size
TITLES = "landed_titles/landed_titles"
CHARACTERS = ("living", "dead_unprunable", "characters/dead_prunable")
_TKEY = re.compile(rb'\n\t+key="?([^"\s]+)"?')
_TOP = re.compile(rb"(?m)^([A-Za-z_][\w.]*)[ \t]*=[ \t]*\{")


def load(path: str) -> bytes:
    """A compressed save through read_save; a plain-text save (header kind 00) by dropping its header line."""
    raw = Path(path).read_bytes()
    if raw[:3] == b"SAV" and raw[5:7] == b"00":
        return raw[raw.index(b"\n") + 1:]
    return sf.read_save(path).gamestate


# --------------------------------------------------------------------------- #
# shape()
# --------------------------------------------------------------------------- #
@dataclass
class Shape:
    size: int
    kinds: Counter = field(default_factory=Counter)   # num / tkey / other / anon / scalar:<kind> / bare
    keys: set = field(default_factory=set)             # distinct keys of keyed blocks and keyed scalars
    repeats: int = 1

    @property
    def count(self) -> int:
        """Entries: distinct keys when keyed (1.20 writes dead_unprunable twice), else list items / values."""
        if self.keys:
            return len(self.keys)
        return self.kinds.get("anon", 0) + self.kinds.get("bare", 0)

    @property
    def kind(self) -> str:
        if not self.kinds:
            return "empty"
        k, _ = self.kinds.most_common(1)[0]
        return k


def _kind(k: bytes | None) -> str:
    if k is None:
        return "anon"
    if k.isdigit():
        return "num"
    return "tkey" if TITLE_KEY.match(k.decode("utf-8", "replace")) else "other"


def _shape(g: bytes, blk: gs.Block) -> Shape:
    s = Shape(blk.close - blk.open)
    try:
        for e in gs.iter_entries(g, *blk.body):
            s.kinds[_kind(e.key)] += 1
            if e.key is not None:
                s.keys.add(e.key.decode("utf-8", "replace"))
    except gs.GamestateError:
        return s
    if s.size < SCALAR_LIMIT:
        try:
            for c in gs.iter_children(g, *blk.body):
                if c.block is not None:
                    continue
                if c.key is None or c.key == b"":
                    s.kinds["bare"] += 1
                elif c.key.isdigit() and g[c.value_start:c.value_end] == b"none":
                    s.kinds["free"] += 1        # a freed slot (``12=none``), not an entry
                else:
                    s.kinds["scalar:" + _kind(c.key)] += 1
                    s.keys.add(c.key.decode("utf-8", "replace"))
        except gs.GamestateError:
            pass
    return s


def shape(g: bytes) -> dict[str, Shape]:
    """Every top-level section and every named child block (one level down)."""
    idx = L.SectionIndex(g)
    reps = Counter(m.group(1).decode() for m in _TOP.finditer(g))
    out: dict[str, Shape] = {}
    for name, b in idx.top.items():
        s = _shape(g, b)
        s.repeats = reps.get(name, 1)
        out[name] = s
        if s.kinds.get("num", 0) > 50:       # a database itself: its entries are not sub-databases
            continue
        try:
            children = [e for e in gs.iter_entries(g, *b.body) if e.key and not e.key.isdigit()]
        except gs.GamestateError:
            continue
        seen = set()
        for c in children[:60]:
            if c.key in seen:
                continue
            seen.add(c.key)
            out[f"{name}/{c.key.decode()}"] = _shape(g, c)
    return out


# --------------------------------------------------------------------------- #
# keys()
# --------------------------------------------------------------------------- #
def ids(g: bytes, path: str) -> set[int]:
    try:
        b = gs.locate(g, path)
    except gs.GamestateError:
        return set()
    return {int(e.key) for e in gs.iter_entries(g, *b.body) if e.key and e.key.isdigit()}


def title_keys(g: bytes) -> dict[int, str]:
    """title id -> key, from the key= at depth 0 of each title entry (the one content read)."""
    out = {}
    b = gs.locate(g, TITLES)
    for e in gs.iter_entries(g, *b.body):
        if not (e.key and e.key.isdigit()):
            continue
        head = g[e.open:min(e.close, e.open + 4096)]
        for m in _TKEY.finditer(head):
            if head.count(b"{", 0, m.start()) - head.count(b"}", 0, m.start()) == 1:
                out[int(e.key)] = m.group(1).decode()
                break
    return out


def characters(g: bytes) -> set[int]:
    out: set[int] = set()
    for p in CHARACTERS:
        out |= ids(g, p)
    return out


@dataclass
class Keys:
    """The key sets of one comparison, with the translation of ref ids into ours."""
    tkey: dict[str, dict[int, str]]
    chars: dict[str, set[int]]
    provinces: dict[str, set[int]]
    title_offset: int
    char_offset: int
    new_titles: set[str]              # title keys the transplant added (ours)
    new_chars_ref: set[int]           # ref character ids the transplant copied

    def tr_char(self, r: int) -> int:
        return (r & GEN) | ((r & LOW) + self.char_offset)


def keys(gs3: dict[str, bytes]) -> Keys:
    tk = {n: title_keys(g) for n, g in gs3.items()}
    tid = {n: {k: i for i, k in m.items()} for n, m in tk.items()}
    shared = [k for k in tid["ref"] if k in tid["ours"]]
    diffs = Counter((tid["ours"][k] & LOW) - (tid["ref"][k] & LOW) for k in shared
                    if (tid["ours"][k] & GEN) == (tid["ref"][k] & GEN))
    toff = diffs.most_common(1)[0][0]
    new_titles = {k for k in shared if (tid["ours"][k] & GEN) == (tid["ref"][k] & GEN)
                  and (tid["ours"][k] & LOW) - (tid["ref"][k] & LOW) == toff}
    ch = {n: characters(g) for n, g in gs3.items()}
    campaign = ch["ours"] & ch["chain"]
    coff = 1 + max(i & LOW for i in campaign)
    new_ref = {r for r in ch["ref"] if ((r & GEN) | ((r & LOW) + coff)) in ch["ours"]}
    pv = {n: ids(g, "provinces") for n, g in gs3.items()}
    return Keys(tk, ch, pv, toff, coff, new_titles, new_ref)


# --------------------------------------------------------------------------- #
# the comparison
# --------------------------------------------------------------------------- #
def mechanical(r: Shape | None, c: Shape | None, o: Shape | None) -> str:
    """A first-pass class from the counts alone; the census document refines it with evidence."""
    rc, cc, oc = (x.count if x else None for x in (r, c, o))
    if r is None:
        return "not in ref"
    if o is None and c is None:
        return "n/a: chain lost it too"
    if o is None:
        return "ours lacks the block"
    if rc == 0:
        return "ref empty: nothing to carry"
    if oc >= rc:
        return "ours >= ref"
    if cc is not None and cc <= oc:
        return "ours < ref, chain <= ours"
    return "ours < ref, chain > ours"


def keyed_gaps(g3: dict[str, bytes], sh: dict[str, dict[str, Shape]], K: Keys) -> list[dict]:
    """Output 2: for sections keyed by title key, province id or character id, the ref keys ours lacks, split
    into new-map (the transplant adds the thing) and campaign."""
    rows = []
    # title-keyed: county records, the coat name map's title keys, the titles themselves
    title_sets = {
        "county_manager/counties": {n: sh[n]["county_manager/counties"].keys for n in g3},
        "coat_of_arms/coat_of_arms_manager_name_map (title keys)":
            {n: {k for k in sh[n]["coat_of_arms/coat_of_arms_manager_name_map"].keys if TITLE_KEY.match(k)}
             for n in g3},
        f"{TITLES} (by key=)": {n: set(K.tkey[n].values()) for n in g3},
    }
    for name, s in title_sets.items():
        lack = s["ref"] - s["ours"]
        rows.append({"section": name, "key": "title key", "ref": len(s["ref"]), "chain": len(s["chain"]),
                     "ours": len(s["ours"]), "lack_new_map": len(lack & K.new_titles),
                     "lack_campaign": len(lack - K.new_titles),
                     "chain_has_of_new_map_lack": len(lack & K.new_titles & s["chain"]),
                     "e.g. new-map": sorted(lack & K.new_titles)[:6],
                     "e.g. campaign": sorted(lack - K.new_titles)[:6]})
    # province-keyed
    lack = K.provinces["ref"] - K.provinces["ours"]
    rows.append({"section": "provinces", "key": "province id", "ref": len(K.provinces["ref"]),
                 "chain": len(K.provinces["chain"]), "ours": len(K.provinces["ours"]),
                 "lack_new_map": len(lack), "lack_campaign": 0, "chain_has_of_new_map_lack": len(lack & K.provinces["chain"]),
                 "e.g. new-map": sorted(lack)[:6], "e.g. campaign": []})
    # character-keyed: the ref key translated into ours; a ref key whose translation is not a character in ours
    # is one of the reference's own people the campaign has its own version of (campaign side)
    for path in ("living", "dead_unprunable", "ai/ai_strategies"):
        s = {n: ids(g, path) for n, g in g3.items()}
        new = s["ref"] & K.new_chars_ref
        lack_new = {r for r in new if K.tr_char(r) not in s["ours"]}
        lack_camp = {r for r in s["ref"] - K.new_chars_ref}
        rows.append({"section": path, "key": "character id", "ref": len(s["ref"]), "chain": len(s["chain"]),
                     "ours": len(s["ours"]), "lack_new_map": len(lack_new), "lack_campaign": len(lack_camp),
                     "chain_has_of_new_map_lack": None, "e.g. new-map": sorted(lack_new)[:6],
                     "e.g. campaign": sorted(lack_camp)[:6]})
    # character_lookup: keyed by history id (numeric OR not: ``han_1176``, ``188854bis``), valued by character id;
    # the key is the whole token at the line start -- an unanchored ``(\d+)=`` reads ``han_1176`` as ``1176``
    maps = {}
    for n, g in g3.items():
        b = gs.find_section(g, "character_lookup")
        maps[n] = {k.decode(): int(v) for k, v in re.findall(rb"(?m)^\t*([^\s={}]+)=(\d+)", g[b.open + 1:b.close])}
    lack = set(maps["ref"]) - set(maps["ours"])
    lack_new = {k for k in lack if maps["ref"][k] in K.new_chars_ref}
    rows.append({"section": "character_lookup", "key": "history id -> character id", "ref": len(maps["ref"]),
                 "chain": len(maps["chain"]), "ours": len(maps["ours"]), "lack_new_map": len(lack_new),
                 "lack_campaign": len(lack - lack_new), "chain_has_of_new_map_lack": len(lack_new & set(maps["chain"])),
                 "e.g. new-map": sorted(lack_new)[:6], "e.g. campaign": sorted(lack - lack_new)[:6]})
    return rows


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opt = {k: sys.argv[sys.argv.index(k) + 1] for k in ("--json", "--md") if k in sys.argv}
    args = [a for a in args if a not in opt.values()]
    t0 = time.time()
    g3 = {n: load(p) for n, p in zip(("ref", "chain", "ours"), args)}
    print(f"loaded in {time.time() - t0:.0f}s")
    sh = {n: shape(g) for n, g in g3.items()}
    print(f"shapes in {time.time() - t0:.0f}s")
    K = keys(g3)
    print(f"keys in {time.time() - t0:.0f}s: title offset {K.title_offset}, new-map titles {len(K.new_titles)}; "
          f"character offset {K.char_offset}, new-map characters {len(K.new_chars_ref)}")
    rows = []
    for path in sorted(set().union(*sh.values())):
        r, c, o = (sh[n].get(path) for n in ("ref", "chain", "ours"))
        rows.append({"path": path, "kind": (r or c or o).kind,
                     "ref": r.count if r else None, "chain": c.count if c else None, "ours": o.count if o else None,
                     "repeats": {n: sh[n][path].repeats for n in sh if path in sh[n] and sh[n][path].repeats > 1},
                     "class": mechanical(r, c, o)})
    gaps = keyed_gaps(g3, sh, K)
    for x in rows:
        print(f"{x['path']:58} {x['kind']:12} ref={x['ref']!s:>7} chain={x['chain']!s:>7} ours={x['ours']!s:>7}"
              f"  {x['class']}{'  rep=' + str(x['repeats']) if x['repeats'] else ''}")
    print("\n== keyed sections: ref keys ours lacks")
    for x in gaps:
        print(json.dumps(x))
    if "--json" in opt:
        Path(opt["--json"]).write_text(json.dumps({"rows": rows, "keyed_gaps": gaps, "title_offset": K.title_offset,
                                                   "char_offset": K.char_offset, "new_titles": len(K.new_titles),
                                                   "new_chars": len(K.new_chars_ref)}, indent=1), encoding="utf-8")
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
