"""Title catalogue (djdarcy, 2026-11-05: "create a dump of counties, baronies, etc to disk similar to what we did
with artifacts"): one JSON per save under private/data/ref/, so #6's checks and the next expansion's are queries on
files, not one-off probes over 200 MB gamestates.

  export <save .ck3 or extracted gamestate> <name>    -> private/data/ref/titles__<name>.json
  land <old name> <updated name> <reference name>     -> per new-map county: who holds it, its liege now, 1.20's
                                                         liege, and the campaign ruler who held the land it was
                                                         carved from (djdarcy's "liege by the land", 13:35)

Per title: tier, holder (id, first name, birth, house, dynasty), de facto and de jure liege keys, capital key.
Also every holy site (index, barony key, is_active), the played character, and every living character's id (a
campaign character keeps its id; a copied one does not exist in the old save). Known answer on export: the played
character holds at least one title.
Usage: python -I title_catalogue.py export|land ..."""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator import savefile as sf, gamestate as gs  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REF = ROOT / "private" / "data" / "ref"
TIER = {"b": "barony", "c": "county", "d": "duchy", "k": "kingdom", "e": "empire", "h": "hegemony"}


def load(p):
    try:
        return sf.read_save(p).gamestate
    except Exception:
        return open(p, "rb").read()


def field(body, name, pat=rb"(\d+)"):
    m = re.search(rb"(?m)^\t" + name + rb"=" + pat, body)
    return m.group(1).decode() if m else None


def export(path, name):
    d = load(path)
    b = gs.locate(d, "landed_titles/landed_titles")
    raw, key_of = {}, {}
    for e in gs.iter_entries(d, *b.body):
        body = d[e.open:e.close]
        k = re.search(rb'(?m)^\tkey="?([\w-]+)', body)
        if not k:
            continue
        key = k.group(1).decode()
        key_of[e.key.decode()] = key
        raw[key] = {f: field(body, f.encode()) for f in ("holder", "de_facto_liege", "de_jure_liege", "capital")}
    lv = gs.find_section(d, "living")
    seg = d[lv.start:lv.end]
    living, people = [], {}
    for m in re.finditer(rb"(?m)^(\d+)=\{", seg):
        living.append(int(m.group(1)))
    holders = {r["holder"] for r in raw.values() if r["holder"]}
    for m in re.finditer(rb"(?m)^(\d+)=\{", seg):
        cid = m.group(1).decode()
        if cid not in holders:
            continue
        end = gs.match_brace(seg, m.end() - 1)
        body = seg[m.start():end]
        people[cid] = {"name": (field(body, b"first_name", rb'"?([^"\n]*)"?') or ""),
                       "birth": field(body, b"birth", rb"([\d.]+)"),
                       "house": field(body, b"dynasty_house")}
    houses = {}
    try:
        hs = gs.locate(d, "dynasties/dynasty_house")
        for e in gs.iter_entries(d, *hs.body):
            m = re.search(rb"(?m)^\t{1,2}dynasty=(\d+)", d[e.open:e.close])
            if m:
                houses[e.key.decode()] = m.group(1).decode()
    except gs.GamestateError:
        pass
    titles = {}
    for key, r in raw.items():
        h = r["holder"]
        titles[key] = {"tier": TIER.get(key[:1], "other"),
                       "holder": ({"id": int(h), **people.get(h, {}),
                                   "dynasty": houses.get((people.get(h) or {}).get("house") or "")} if h else None),
                       "de_facto_liege": key_of.get(r["de_facto_liege"]),
                       "de_jure_liege": key_of.get(r["de_jure_liege"]),
                       "capital": key_of.get(r["capital"])}
    sites = []
    try:
        hsb = gs.locate(d, "religion/holy_sites")
        for e in gs.iter_entries(d, *hsb.body):
            body = d[e.open:e.close]
            sites.append({"index": e.key.decode(), "type": field(body, b"\t?type", rb'"?(\w+)"?') or
                          (re.search(rb'type="?(\w+)', body).group(1).decode() if b"type=" in body else None),
                          "barony": key_of.get(re.search(rb"barony=(\d+)", body).group(1).decode())
                          if b"barony=" in body else None,
                          "is_active": (re.search(rb"is_active=(\w+)", body).group(1).decode()
                                        if b"is_active=" in body else None)})
    except gs.GamestateError:
        pass
    pm = re.search(rb"(?m)^played_character=\{\s*name=[^\n]*\n\s*character=(\d+)", d)
    player = int(pm.group(1)) if pm else None
    held = [k for k, t in titles.items() if t["holder"] and t["holder"]["id"] == player]
    assert held, "known answer failed: the played character holds no title"
    out = {"source": str(path), "player": player, "titles": titles, "holy_sites": sites, "living": sorted(living)}
    REF.mkdir(parents=True, exist_ok=True)
    dest = REF / f"titles__{name}.json"
    dest.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"{dest.name}: {len(titles)} titles ({dict(Counter(t['tier'] for t in titles.values()))}), "
          f"{len(sites)} holy sites, {len(living)} living, player {player} holds {len(held)}")


def read(name):
    return json.loads((REF / f"titles__{name}.json").read_text(encoding="utf-8"))


def chain(cat, key):
    """The de facto liege chain above a title, as keys."""
    out, seen = [], {key}
    k = cat["titles"][key]["de_facto_liege"]
    while k and k not in seen:
        out.append(k)
        seen.add(k)
        k = cat["titles"].get(k, {}).get("de_facto_liege")
    return out


def land(old_n, new_n, ref_n):
    old, new, ref = read(old_n), read(new_n), read(ref_n)
    old_living = set(old["living"])
    rows, kinds = [], Counter()
    for key, t in new["titles"].items():
        if t["tier"] != "county" or key in old["titles"] or not t["holder"]:
            continue
        copied = t["holder"]["id"] not in old_living
        baronies = [b for b, x in new["titles"].items() if x["tier"] == "barony" and x["de_jure_liege"] == key]
        old_counties = sorted({old["titles"][b]["de_jure_liege"] for b in baronies if b in old["titles"]} - {None})
        owners = []
        for oc in old_counties:
            h = old["titles"].get(oc, {}).get("holder")
            if h:
                # who controlled that land in the original game (djdarcy 13:35: "territory I controlled in the
                # original game"): the nearest liege above count tier over the old county, in the OLD save
                up = next((k for k in chain(old, oc) if old["titles"].get(k, {}).get("tier")
                           in ("duchy", "kingdom", "empire", "hegemony")), None)
                top = (chain(old, oc) or [oc])[-1]
                owners.append({"old_county": oc, "count": h["id"], "by_land": up, "realm_top": top,
                               "player_realm": (old["titles"].get(top, {}).get("holder") or {}).get("id")
                               == old["player"]})
        now = t["de_facto_liege"]
        ref_liege = ref["titles"].get(key, {}).get("de_facto_liege")
        land_liege = owners[0]["by_land"] if owners else None
        kind = ("land nobody in the campaign held" if not owners else
                "by land = now" if land_liege == now else "by land differs from now")
        kinds[(("copied" if copied else "campaign") + " holder", kind)] += 1
        rows.append({"county": key, "holder": t["holder"], "copied": copied, "liege_now": now,
                     "liege_1_20": ref_liege, "carved_from": owners, "liege_by_land": land_liege})
    print("new-map counties by holder and by liege-by-the-land:")
    for k, n in sorted(kinds.items()):
        print(f"  {n:>5}  {k[0]}: {k[1]}")
    dest = REF / f"land__{new_n}.json"
    dest.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"rows: {dest}")
    for r in rows:
        if r["copied"] and r["carved_from"] and r["liege_by_land"] != r["liege_now"]:
            o = r["carved_from"][0]
            print(f"  {r['county']}: {r['holder']['name']}; now {r['liege_now']}, 1.20 {r['liege_1_20']}, by land "
                  f"{r['liege_by_land']} (from {o['old_county']}, realm {o['realm_top']}"
                  f"{', PLAYER' if o['player_realm'] else ''})")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "export":
        export(sys.argv[2], sys.argv[3])
    elif cmd == "land":
        land(*sys.argv[2:5])
    else:
        sys.exit(__doc__)
