"""kin_continuity: is the family's history intact across the migration and the game's own load? (djdarcy,
2026-10-26: "checking any other historical components ... for dead characters (especially in the family since
that determines who is entitled to which titles elsewhere)").

For every member of the player's dynasty, living and dead, compares three saves of the campaign:
  old      the 1.8.1 original;
  ours     the migrator's output;
  resaved  the game's own save of `ours` (what 1.20 kept on load).
Fields, each normalised so that ids which legitimately differ between versions are compared by name:
  identity    section, first_name, birth, female, nickname, was_playable, dynasty_house (by house key)
  family      primary_spouse, spouses, former spouses, children, real_father (character ids are kept for the
              campaign, so they compare as ids)
  death       dead_data date, reason, liege, liege_title and domain (titles by key), government
  traits      by name (each save's traits_lookup)
  portrait    portrait_override present / its text
For each field: how many family members changed old -> ours (the migrator) and ours -> resaved (the game), with
up to five examples each. A character missing from a later save is counted under "presence".

Usage: python -I tests/one-offs/kin_continuity.py <old.ck3> <ours.ck3> <resaved.ck3> [player id] [--examples N]
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

SECTIONS = ("living", "dead_unprunable", "characters/dead_prunable")
TKEY = re.compile(rb'\n\t+key="?([^"\s]+)"?')


def load(path: str) -> bytes:
    raw = Path(path).read_bytes()
    if raw[:3] == b"SAV" and raw[5:7] == b"00":
        return raw[raw.index(b"\n") + 1:]
    return sf.read_save(path).gamestate


def field(body: bytes, key: str, indent: bytes = b"\t") -> str | None:
    m = re.search(rb"\n" + indent + key.encode() + rb'="?([^"\n]*?)"?\s*\n', body)
    return m.group(1).decode("utf-8", "replace") if m else None


def block(body: bytes, key: str, indent: bytes = b"\t") -> bytes | None:
    m = re.search(rb"\n" + indent + key.encode() + rb"=\{", body)
    if not m:
        return None
    end = gs.match_brace(body, m.end() - 1)
    return body[m.end():end]


def ids(text: bytes | None) -> list[str]:
    return [] if text is None else [x.decode() for x in re.findall(rb"\d+", text)]


class Save:
    def __init__(self, path: str):
        self.g = g = load(path)
        self.title = {}
        for e in gs.iter_entries(g, *gs.locate(g, "landed_titles/landed_titles").body):
            if e.key and e.key.isdigit():
                head = g[e.open:min(e.close, e.open + 4096)]
                m = TKEY.search(head)
                if m:
                    self.title[e.key.decode()] = m.group(1).decode()
        self.house = {}
        for e in gs.iter_entries(g, *gs.locate(g, "dynasties/dynasty_house").body):
            body = g[e.start:e.end]
            k, d = re.search(rb'\n\t+key="?([^"\s]+)', body), re.search(rb"\n\t+dynasty=(\d+)", body)
            self.house[e.key.decode()] = ((k.group(1).decode() if k else e.key.decode()), d.group(1).decode() if d else None)
        tl = gs.find_section(g, "traits_lookup")
        self.traits = [t.decode() for t in re.findall(rb'"?([A-Za-z0-9_]+)"?', g[tl.open + 1:tl.close])]
        self.chars = {}
        for sec in SECTIONS:
            try:
                b = gs.locate(g, sec)
            except gs.GamestateError:
                continue
            for e in gs.iter_entries(g, *b.body):
                if e.key and e.key.isdigit():
                    self.chars[e.key.decode()] = (sec.split("/")[-1], e.start, e.end)

    def record(self, cid: str) -> dict | None:
        if cid not in self.chars:
            return None
        sec, s, t = self.chars[cid]
        body = self.g[s:t]
        fam = block(body, "family_data") or b""
        dead = block(body, "dead_data") or b""
        house = field(body, "dynasty_house")
        tr = block(body, "traits") if False else re.search(rb"\n\ttraits=\{([^}]*)\}", body)
        title = lambda i: self.title.get(i, f"#{i}")                      # noqa: E731
        return {
            "presence": sec,
            "identity": (field(body, "first_name"), field(body, "birth"), field(body, "female"),
                         field(body, "nickname"), field(body, "was_playable"),
                         self.house.get(house or "", (house,))[0]),
            "family": (field(fam, "primary_spouse", b"\t\t"),
                       tuple(sorted(re.findall(r"\n\t\tspouse=(\d+)", fam.decode("utf-8", "replace")))),
                       tuple(sorted(ids(block(fam, "former_spouses", b"\t\t")))),
                       tuple(sorted(ids(block(fam, "child", b"\t\t")))),
                       field(fam, "real_father", b"\t\t")),
            "death": (field(dead, "date", b"\t\t"), field(dead, "reason", b"\t\t"), field(dead, "liege", b"\t\t"),
                      title(field(dead, "liege_title", b"\t\t") or ""),
                      tuple(sorted(title(i) for i in ids(block(dead, "domain", b"\t\t")))),
                      field(dead, "government", b"\t\t")),
            "traits": tuple(sorted(self.traits[int(i)] if int(i) < len(self.traits) else f"#{i}"
                                   for i in ids(tr.group(1) if tr else None))),
            "portrait": (block(body, "portrait_override") or b"").strip().replace(b"\r", b""),
        }


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    n_ex = int(sys.argv[sys.argv.index("--examples") + 1]) if "--examples" in sys.argv else 5
    old_p, ours_p, res_p = args[:3]
    player = args[3] if len(args) > 3 else "50822"
    old, ours, res = Save(old_p), Save(ours_p), Save(res_p)

    def dyn_of(save, cid):
        r = save.chars.get(cid)
        if not r:
            return None
        h = field(save.g[r[1]:r[2]], "dynasty_house")
        return save.house.get(h or "", (None, None))[1]

    fam_dyn = dyn_of(old, player)
    family = [c for c in old.chars if dyn_of(old, c) == fam_dyn]
    print(f"player {player}; dynasty {fam_dyn}; family members in the 1.8.1 save: {len(family)} "
          f"(living {sum(1 for c in family if old.chars[c][0] == 'living')})")
    changes = {"old -> ours (the migrator)": defaultdict(list), "ours -> resaved (the game)": defaultdict(list)}
    for c in family:
        a, b, r = old.record(c), ours.record(c), res.record(c)
        for label, x, y in (("old -> ours (the migrator)", a, b), ("ours -> resaved (the game)", b, r)):
            if x is None:
                continue
            if y is None:
                changes[label]["presence"].append((c, x["presence"], "absent"))
                continue
            for k in x:
                if x[k] != y[k]:
                    changes[label][k].append((c, x[k], y[k]))
    from collections import Counter
    for label, d in changes.items():
        gone, came = Counter(), Counter()
        for _, x, y in d.get("traits", []):
            gone.update(set(x) - set(y))
            came.update(set(y) - set(x))
        if gone or came:
            print(f"\n== {label}: traits by name across the family")
            print("  removed: " + ", ".join(f"{k} {v}" for k, v in gone.most_common()))
            print("  added:   " + ", ".join(f"{k} {v}" for k, v in came.most_common()))
    for label, d in changes.items():
        print(f"\n== {label}")
        if not d:
            print("  no change in any field")
        for k in ("presence", "identity", "family", "death", "traits", "portrait"):
            rows = d.get(k, [])
            print(f"  {k:9} {len(rows)} changed")
            for c, x, y in rows[:n_ex]:
                if isinstance(x, tuple) and isinstance(y, tuple) and len(x) == len(y):
                    diff = [(i, x[i], y[i]) for i in range(len(x)) if x[i] != y[i]]
                    show = "; ".join(f"[{i}] {str(u)[:90]} -> {str(v)[:90]}" for i, u, v in diff)
                else:
                    show = f"{str(x)[:120]} -> {str(y)[:120]}"
                print(f"      {c}: {show}")


if __name__ == "__main__":
    main()
