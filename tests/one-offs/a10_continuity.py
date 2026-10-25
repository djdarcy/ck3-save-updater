"""A10 continuity probe (read-only): did the people in djdarcy's campaign plans survive the migration unchanged?

Walks the family tree from two anchors -- Uilleam I (28792) and the played character (Beidh) -- to the people
named in his notes, reads each in the 1.8.1 gamestate and in a migrated save, and compares each character's
entry line by line. Expected differences: faith= -> rite= (and the rite= R12 adds), nothing else.

This only REPORTS. A link that looks wrong is raised with djdarcy, never "fixed" (it may be a spelling or a
misreading); no rule ever writes family, claim or succession data.

Usage: python -I tests/one-offs/a10_continuity.py <old gamestate (extracted)> <migrated .ck3>
"""
import re
import sys
import unicodedata
from bisect import bisect_right
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

CHAR_SECTIONS = ("living", "dead_unprunable", "characters")
ENTRY = re.compile(rb'(?m)^(\d+)=\{\n\tfirst_name="([^"]*)"')


def norm(s: str) -> str:
    """Compare names loosely. 1.8.1 escapes some accented letters as capital + '_' (MA_el-TO_lai = Máel-Tólai,
    E_lfweard = Ælfweard), others are stored as UTF-8 (Sésésé); both fold to plain lowercase letters here."""
    s = re.sub(r"([A-Z])_", lambda m: m.group(1), s)
    s = unicodedata.normalize("NFKD", s)
    return re.sub(r"[^a-z]", "", s.encode("ascii", "ignore").decode().lower())


class Save:
    def __init__(self, label: str, g: bytes):
        self.label, self.g = label, g
        self.chars = {}                       # id -> (name, section, start)
        self.starts, self.ids = [], []
        for sec in CHAR_SECTIONS:
            b = next(gs.find_sections(g, sec), None)
            if b is None:
                continue
            for m in ENTRY.finditer(g, b.open, b.close):
                cid = m.group(1).decode()
                self.chars.setdefault(cid, (m.group(2).decode("utf-8", "replace"), sec, m.start()))
        for cid, (_, _, st) in sorted(self.chars.items(), key=lambda kv: kv[1][2]):
            self.starts.append(st)
            self.ids.append(cid)
        self.title_key, self.holder_titles = {}, {}
        for t in gs.iter_entries(g, *gs.locate(g, "landed_titles/landed_titles").body):
            body = g[t.open:t.close]
            k = re.search(rb'\n\tkey="?([\w-]+)', body)
            if not k:
                continue
            self.title_key[t.key.decode()] = k.group(1).decode()
            h = re.search(rb"\n\tholder=(\d+)", body)
            if h:
                self.holder_titles.setdefault(h.group(1).decode(), []).append(k.group(1).decode())
        self.houses = {}
        for h in gs.iter_entries(g, *gs.locate(g, "dynasties/dynasty_house").body):
            body = g[h.open:h.close]
            nm = re.search(rb'\n\t(?:name|localized_name|key)="?([^"\n]+)', body)
            self.houses[h.key.decode()] = nm.group(1).decode("utf-8", "replace") if nm else "?"
        tl = re.search(rb"(?m)^traits_lookup=\{([^}]*)\}", g)
        self.traits = tl.group(1).split() if tl else []
        self.faith_name, self.rite_name = {}, {}
        try:
            for f in gs.iter_entries(g, *gs.locate(g, "religion/faiths").body):
                body = g[f.open:f.close]
                n = re.search(rb'\n\t\t\t(?:name|template)="([^"]+)"', body)
                self.faith_name[f.key.decode()] = n.group(1).decode() if n else "?"
        except gs.GamestateError:
            pass
        try:
            for r in gs.iter_entries(g, *gs.locate(g, "rites/database").body):
                body = g[r.open:r.close]
                n = re.search(rb'rite_type=(\w+)|\n\t\t\t\tname="([^"]+)"', body)
                self.rite_name[r.key.decode()] = (n.group(1) or n.group(2)).decode() if n else "?"
        except gs.GamestateError:
            pass

    def block(self, cid: str) -> bytes | None:
        if cid not in self.chars:
            return None
        st = self.chars[cid][2]
        op = self.g.index(b"{", st)
        return self.g[st:gs.match_brace(self.g, op) + 1]

    def owner_at(self, pos: int) -> str | None:
        i = bisect_right(self.starts, pos) - 1
        return self.ids[i] if i >= 0 else None

    def parents(self, cid: str) -> list[str]:
        out = []
        for m in re.finditer(rb"\n\t\tchild=\{[^}]*?\b" + cid.encode() + rb"\b", self.g):
            o = self.owner_at(m.start())
            if o and o not in out:
                out.append(o)
        return out

    def info(self, cid: str) -> dict:
        b = self.block(cid)
        if b is None:
            return {"id": cid, "missing": True}
        name, sec, _ = self.chars[cid]
        one = lambda pat: (lambda m: m.group(1).decode() if m else None)(re.search(pat, b))
        many = lambda pat: [x.decode() for x in re.findall(pat, b)]
        fam = re.search(rb"\n\tfamily_data=\{", b)
        fb = b[fam.end():gs.match_brace(b, fam.end() - 1)] if fam else b""
        lst = lambda key: (lambda m: m.group(1).split() if m else [])(re.search(rb"\n\t\t" + key + rb"=\{([^}]*)\}", fb))
        house = one(rb"\n\tdynasty_house=(\d+)")
        t = re.search(rb"\n\ttraits=\{([^}]*)\}", b)
        tr = [self.traits[int(x)].decode() if int(x) < len(self.traits) else x.decode() for x in (t.group(1).split() if t else [])]
        dom = re.search(rb"\n\t\tdomain=\{([^}]*)\}", b)
        titles = self.holder_titles.get(cid, []) if sec == "living" else \
            [self.title_key.get(x.decode(), x.decode()) for x in (dom.group(1).split() if dom else [])]
        claims = [self.title_key.get(x, x) for x in many(rb"\n\t+claim=\{[^}]*?title=(\d+)")]
        return {
            "id": cid, "name": name, "section": sec, "birth": one(rb"\n\tbirth=([\d.]+)"),
            "death": one(rb"\n\t\tdate=([\d.]+)") if sec != "living" else None,
            "house": f"{house} {self.houses.get(house, '?')}" if house else None,
            "faith": (lambda f: f and f"{f} {self.faith_name.get(f, '?')}")(one(rb"\n\tfaith=(\d+)")),
            "rite": (lambda r: r and f"{r} {self.rite_name.get(r, '?')}")(one(rb"\n\trite=(\d+)")),
            "primary_spouse": re.search(rb"\n\t\tprimary_spouse=(\d+)", fb) and re.search(rb"\n\t\tprimary_spouse=(\d+)", fb).group(1).decode(),
            "spouses": list(dict.fromkeys(x.decode() for x in re.findall(rb"\n\t\tspouse=(\d+)", fb))),
            "former_spouses": [x.decode() for x in lst(b"former_spouses")],
            "betrothed": [x.decode() for x in re.findall(rb"\n\t\tbetrothed=(\d+)", fb)],
            "children": [x.decode() for x in lst(b"child")],
            "real_father": (lambda m: m.group(1).decode() if m else None)(re.search(rb"\n\t\treal_father=(\d+)", fb)),
            "traits": tr, "titles": titles, "claims": claims,
            "flags": many(rb'flag="([^"]+)"'),
            "heir_lines": [x.decode("utf-8", "replace").strip() for x in
                           re.findall(rb"\n\t*[^\n]*(?:heir|disinherit|legitim|exclu|succession)[^\n]*", b)][:8],
        }

    def named(self, ids, *fragments: str) -> list[str]:
        """ids whose folded name contains every fragment (fragments are folded too)."""
        fs = [norm(f) for f in fragments]
        return list(dict.fromkeys(c for c in ids if c in self.chars and all(f in norm(self.chars[c][0]) for f in fs)))

    def find_by_name(self, want: str) -> list[str]:
        w = norm(want)
        return [c for c, (n, _, _) in self.chars.items() if norm(n) == w]


def short(s: Save, cid) -> str:
    """id name (house) [top titles held now, or at death]."""
    if not cid:
        return "-"
    if cid not in s.chars:
        return f"{cid} ?"
    i = s.info(cid)
    top = [t for t in i["titles"] if t[:2] in ("e_", "k_")][:3]
    house = (i["house"] or "").split(" ", 1)[-1]
    return f"{cid} {i['name']} ({house})" + (f" [{', '.join(top)}]" if top else "")


def diff(old: Save, new: Save, cid: str) -> tuple[int, list[str]]:
    a, b = old.block(cid), new.block(cid)
    if a is None or b is None:
        return -1, ["missing in " + ("old" if a is None else "new")]
    drop = re.compile(rb"^\s*(faith|rite)=")
    la = [l for l in a.split(b"\n") if not drop.match(l)]
    lb = [l for l in b.split(b"\n") if not drop.match(l)]
    if la == lb:
        return 0, []
    import difflib
    d = [x for x in difflib.unified_diff([l.decode("utf-8", "replace") for l in la],
                                         [l.decode("utf-8", "replace") for l in lb], lineterm="", n=0)
         if x[:1] in "+-" and not x.startswith(("+++", "---"))]
    return len(d), d[:8]


def main():
    old = Save("1.8.1", Path(sys.argv[1]).read_bytes())
    new = Save("migrated", sf.read_save(sys.argv[2]).gamestate)
    player = re.search(rb"(?m)^played_character=\{[^}]*?\n\tcharacter=(\d+)", old.g).group(1).decode()
    people: list[tuple[str, str]] = [("Uilleam I", "28792"), ("Beidh (player)", player)]

    uil = old.info("28792")
    # the notes' spellings vs the save's: match on a distinctive fragment of each name
    for label, frags in (("Sesese", ("sesese",)), ("Ganntanas", ("ganntanas",)), ("Dub-Lemna", ("dub", "lemn")),
                         ("Naid", ("naid",)), ("Eithne", ("eithne",)), ("Fiachra", ("fiachra",)),
                         ("Deannech", ("deann",))):
        hits = old.named(uil["children"], *frags)
        people += [(f"{label} (Uilleam's child)", h) for h in hits] or [(f"{label} (Uilleam's child)", "")]
    for role, cid in list(people):
        if not cid:
            continue
        for who, wife, frag in (("Fiachra", "Xenia", "xenia"), ("Deannech", "Huup", "huup")):
            if role.startswith(who):
                i = old.info(cid)
                people += [(f"{wife} ({who}'s wife)", h) for h in old.named(i["spouses"] + i["former_spouses"], frag)] \
                    or [(f"{wife} ({who}'s wife)", "")]
    # the Arab emperor (holder of e_arabia) and, per the 987 plan, his son Bruide married to Queen Aelfweard,
    # whose son Gabran was born out of wedlock
    emp = [c for c, ts in old.holder_titles.items() if "e_arabia" in ts]
    for e in emp:
        people.append(("Arab emperor (e_arabia)", e))
        for b_ in old.named(old.info(e)["children"], "bruide"):
            people.append(("Bruide (the emperor's son)", b_))
            bi = old.info(b_)
            for a in old.named(bi["spouses"] + bi["former_spouses"] + bi["betrothed"], "lfweard"):
                par = old.parents(a)
                grand = [g for p in par for g in old.parents(p)]
                tag = "Beidh's granddaughter" if player in grand else f"parents {par}, grandparents {grand}"
                people.append((f"Aelfweard (Bruide's wife; {tag})", a))
                for g_ in old.named(old.info(a)["children"], "gabran"):
                    people.append(("Gabran (Aelfweard's son)", g_))
    # Dub-Lemna is not Uilleam's child; the plan says she married the Umayyad heir -- find her by that link
    for d in old.named(old.chars, "dub", "lemn"):
        i = old.info(d)
        mates = i["spouses"] + i["former_spouses"] + i["betrothed"]
        if any("umayy" in norm(old.info(m).get("house") or "") for m in mates if m in old.chars):
            par = old.parents(d)
            people.append((f"Dub-Lemna (married an Umayyad; parents {[short(old, p) for p in par]})", d))
    seen = set()
    people = [p for p in people if not (p in seen or seen.add(p))]

    print(f"player = {player}; e_arabia holders = {emp}")
    print(f"Uilleam's {len(uil['children'])} children: {[old.chars.get(c, ('?',))[0] for c in uil['children']]}\n")
    for role, cid in people:
        if not cid:
            print(f"## {role}: NOT FOUND among the expected relatives\n")
            continue
        o, n = old.info(cid), new.info(cid)
        print(f"## {role}: {cid} {o.get('name')}")
        if o.get("missing"):
            print("   missing in the 1.8.1 save\n")
            continue
        print(f"   1.8.1   : {o['section']}, born {o['birth']}" + (f", died {o['death']}" if o['death'] else "") +
              f", house {o['house']}, faith {o['faith']}")
        print(f"   migrated: {'MISSING' if n.get('missing') else n['section'] + ', rite ' + str(n['rite'])}")
        print(f"   spouse  : primary {short(old, o['primary_spouse'])}; spouses {[short(old, x) for x in o['spouses']]}")
        if o["betrothed"]:
            print(f"   betrothed: {[short(old, x) for x in o['betrothed']]}")
        if o["former_spouses"]:
            print(f"   former  : {len(o['former_spouses'])}")
        kids = o["children"]
        print(f"   children: {len(kids)}" + (f" -- {[old.chars.get(k, ('?',))[0] for k in kids][:14]}" if kids else ""))
        if o["real_father"]:
            print(f"   real_father: {short(old, o['real_father'])}")
        print(f"   titles  : {o['titles'][:10]}{' ...' if len(o['titles']) > 10 else ''}")
        if o["claims"]:
            print(f"   claims  : {o['claims'][:10]}")
        flagged = [t for t in o["traits"] if re.search(r"bastard|disinh|legitim|concubine|wild_oat|denounced", t)]
        if flagged or "Gabran" in role:
            print(f"   traits of note: {flagged}  (all: {len(o['traits'])})")
        fl = [f for f in o["flags"] if re.search(r"heir|disinh|succ|exclu|bastard", f, re.I)]
        if fl or "Gabran" in role:
            print(f"   flags of note : {fl}")
        if o["heir_lines"] and ("Gabran" in role or "Aelfweard" in role):
            print(f"   heir-related lines: {o['heir_lines']}")
        if "Gabran" in role or "Aelfweard" in role:
            print(f"   parents : {[short(old, p) for p in old.parents(cid)]}")
        same = all(o[k] == n.get(k) for k in ("spouses", "primary_spouse", "former_spouses", "children", "betrothed",
                                               "house", "traits", "claims", "real_father"))
        nd, sample = diff(old, new, cid)
        print(f"   links same in migrated: {same}; entry diff (faith/rite lines ignored): {nd} line(s)")
        for x in sample:
            print(f"      {x[:140]}")
        print()


if __name__ == "__main__":
    main()
