"""S1 review page: djdarcy rates the unclear icon pairings and picks among same-picture candidates, in one local page.

djdarcy 2026-11-19: "You could give me unclear pairings of images as side-by-sides or sheets of pairings and I can
confirm whether they're a fit or not ... I rate whether the items are related and I say "yes" or no and you can give
the imgcompare score and your own determination and I can sign off".

Two kinds of card, for the 39 regular families v17 holds:
  A  "Same thing?"  -- an old 1.20 picture beside a 1.21 picture whose art is unclear: imgcompare cosine 0.90-0.978,
                       or the same file name with different art. Yes / no.
  B  "Which one?"   -- a family whose candidates carry the same picture (reused as-is, or cosine >= 0.978): each
                       candidate with the districts that host it on the family's holdings, gates, and tier ladder.
                       Pick one, or none.
Every card carries the imgcompare score and band and the lead worker's own call with its reason.

Inputs: the icon map JSON (icon_map_1_21.py), the CLIP JSON (icon_clip_1_21.py), the S1 JSON, the flattened icon PNGs
(icon_clip_1_21.py's scratch folder), the 1.21 game dir. Run in ImgCompare's venv (needs torch for the per-candidate
cosine), offline:
  HF_HUB_OFFLINE=1 C:/code/ImgCompare/venv/Scripts/python.exe -I -X utf8 tests/one-offs/thinking/s1_review_page.py \
      <game> <icon_map.json> <icon_clip.json> <s1.json> <png dir> <out.html>
Writes only <out.html> (self-contained: icons embedded). The page saves progress in the browser and exports answers
as JSON (copy, or download s1-review-answers.json).
"""
import base64
import collections
import html
import io
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
sys.path.insert(0, r"C:/code/ImgCompare")
from ck3_save_migrator import host_rules  # noqa: E402
import imgcompare  # noqa: E402  (djdarcy's tool, used as-is)

SAME, UNCLEAR = 0.978, 0.90
DFILE = {}   # district -> the common/districts file stem that defines it (set in main)
KIND_BY_FILE = {"duchy_capital_districts": "duchy_capital", "great_districts": "great", "special_mines_districts": "mine",
                "legendary_districts": "legendary", "trade_post_districts": "trade", "entrepot_districts": "trade"}
HOLDING_LINES = {"castle", "city", "temple", "tribe", "church"}   # a holding's own building, never a regular successor


def fam(k):
    return re.sub(r"_\d+$", "", k)


def b64(png: pathlib.Path, size=72):
    from PIL import Image
    im = Image.open(png).convert("RGB").resize((size, size))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


DUCHY_SUCCESSOR = {   # v2 (2026-11-19 rethink): 1.20 duchy-capital family -> (1.21 district, building, source)
    "blacksmiths": ("military_duchy_capital_district", "blacksmiths", "same key"),
    "march": ("military_duchy_capital_district", "march", "same key"),
    "jousting_lists": ("military_duchy_capital_district", "jousting_lists", "same key"),
    "royal_forest": ("ducal_residence_district", "royal_forest", "same key"),
    "tax_assessor": ("assay_district", "assay_district", "same picture (duchy_buildings/tax_assessor.dds); the old key is gone"),
}


def main(game, icon_map, icon_clip, s1_json, png_dir, out_html, duchy_json=None, version="v1"):
    game, png_dir = pathlib.Path(game), pathlib.Path(png_dir)
    global DFILE
    DFILE = {}
    for f in sorted((game / "common" / "districts").glob("*.txt")):
        for k, _, _ in host_rules._blocks(f):
            DFILE[k] = f.stem
    rows = json.loads(pathlib.Path(icon_map).read_text(encoding="utf-8"))
    clip = {r["family"]: r["top"] for r in json.loads(pathlib.Path(icon_clip).read_text(encoding="utf-8"))}
    s1 = json.loads(pathlib.Path(s1_json).read_text(encoding="utf-8"))
    rules = host_rules.load(game)

    holds = collections.defaultdict(collections.Counter)
    for r in s1:
        if r["kind"] not in ("holding line", "wonder"):
            holds[r["family"]][r["holding"]] += r["instances"]

    icon_of, chain = {}, collections.defaultdict(list)
    for f in sorted((game / "common" / "buildings").rglob("*.txt")):
        for k, body, _ in host_rules._blocks(f):
            m = re.search(r'type_icon\s*=\s*"?([^"\s]+)', body)
            if m and fam(k) not in icon_of:
                icon_of[fam(k)] = m.group(1).replace(".dds", "")
            chain[fam(k)].append(k)
    users = collections.defaultdict(set)
    for f, ic in icon_of.items():
        users[ic].add(f)

    def facts(cand, family):
        """Per holding the family sits on: the districts of that holding that host the candidate, gated or not."""
        out = []
        for h, n in holds[family].most_common():
            names, _ = rules.holdings.get(h, (set(), None))
            ds = [(d, rules.districts[d].gated) for d in sorted(names)
                  if d in rules.districts and any(fam(b) == cand for b in rules.districts[d].buildings)]
            out.append({"holding": h, "n": n, "districts": [{"d": d, "gated": g} for d, g in ds]})
        anywhere = sorted({h for h, (names, _) in rules.holdings.items()
                           for d in names if d in rules.districts
                           and any(fam(b) == cand for b in rules.districts[d].buildings)})
        tiers = sorted(chain[cand], key=lambda k: int(re.search(r"_(\d+)$", k).group(1)) if re.search(r"_(\d+)$", k) else 0)
        lives_in = sorted({(d, KIND_BY_FILE.get(DFILE.get(d), x.kind)) for d, x in rules.districts.items()
                           if any(fam(b) == cand for b in x.buildings)})
        return {"per_holding": out, "anywhere": anywhere, "lives_in": lives_in, "tiers": len(tiers),
                "level_req": [rules.level_req.get(k) for k in tiers]}

    model, processor, device = imgcompare.load_models()
    cache = {}

    def emb(ic):
        if ic not in cache:
            cache[ic] = imgcompare.compute_embeddings(str(png_dir / (ic + ".png")), model, processor, device)
        return cache[ic]

    def png(ic):
        p = png_dir / (ic + ".png")
        return b64(p) if p.exists() else ""

    cards_a, cards_b = [], []
    for r in rows:
        f, old = r["family"], (f"old_buildings/{r['old_icon']}" if r.get("old_icon") else None)
        if not old or not (png_dir / (old + ".png")).exists():
            continue
        cands = {}
        for d in r["reuse"] + r["name"]:
            cands[d["family"]] = d["icon"]
        for t in clip.get(f, []):
            if t["cosine"] >= UNCLEAR:
                for g in users.get(t["icon"], ()):
                    cands.setdefault(g, t["icon"])
        same, unclear = [], []
        names = {d["family"] for d in r["name"]}
        for g, ic in sorted(cands.items()):
            if not (png_dir / (ic + ".png")).exists() or g in HOLDING_LINES:
                continue
            cos = 1.0 if ic == old else imgcompare.cosine_similarity(emb(old), emb(ic))
            band = imgcompare.classify_similarity(cos)[0]
            item = {"family": g, "icon": ic, "cos": round(cos, 4), "band": band, **facts(g, f)}
            if cos >= SAME:
                same.append(item)
            elif cos >= 0.96 or g in names:
                unclear.append(item)
            elif cos >= UNCLEAR:
                unclear.append({**item, "weak": True})
        # 0.90-0.96 is mostly coincidence on these icons: ask only where nothing better exists, best three
        if same or any(not u.get("weak") for u in unclear):
            unclear = [u for u in unclear if not u.get("weak")]
        else:
            unclear = sorted(unclear, key=lambda u: -u["cos"])[:3]
        for u in unclear:
            if u["cos"] >= 0.96:
                call, why = "maybe (high score)", ("0.96+ was the same subject redrawn in the five pairs checked by eye, "
                                                   "but some pairs here look like the same drawing style only")
            elif u["cos"] >= UNCLEAR:
                call, why = "maybe", "same theme or only the same drawing style (0.90-0.96 mixes both)"
            else:
                call, why = "likely no", "same file name, but CLIP scores the art below 0.90"
            cards_a.append({"key": f"{f}->{u['family']}", "family": f, "v17": r["v17"], "old": png(old),
                            "new": png(u["icon"]), "cand": u, "call": call, "why": why})
        if same:
            main_h = holds[f].most_common(1)[0][0] if holds[f] else None

            def score(c):
                on = next((p for p in c["per_holding"] if p["holding"] == main_h), None)
                hostable = bool(on and on["districts"])
                ungated = bool(on and any(not d["gated"] for d in on["districts"]))
                starts_low = (c["level_req"][:1] or [None])[0] in (None, 1)   # tier 1 needs no district level
                return (hostable, starts_low, ungated, len([p for p in c["per_holding"] if p["districts"]]),
                        c["icon"] == old)
            ranked = sorted(same, key=score, reverse=True)
            best = ranked[0] if score(ranked[0])[0] else None
            if best:
                s = score(best)
                why = (f"hosted on {main_h}" + (" in an ungated district" if s[2] else " but only in a gated district")
                       + ("; its tier 1 needs no district level" if s[1] else "; even its tier 1 needs a raised district")
                       + f"; fits {s[3]} of the family's {len(holds[f])} holding types")
            else:
                why = f"no candidate is hosted on {main_h}, the holding where v17 has most of them"
            cards_b.append({"family": f, "v17": r["v17"], "holdings": dict(holds[f]), "v17_tiers": r["v17_tiers"],
                            "old": png(old), "cands": [{**c, "img": png(c["icon"])} for c in ranked],
                            "rec": best["family"] if best else "none", "why": why})

    cards_a.sort(key=lambda c: -c["v17"])
    cards_b.sort(key=lambda c: -c["v17"])
    cards_c = []
    if duchy_json:
        for rec in json.loads(pathlib.Path(duchy_json).read_text(encoding="utf-8")):
            old_key = rec["building"][0]
            f = fam(old_key)
            dist, bld, src = DUCHY_SUCCESSOR.get(f, (None, None, None))
            ok = rec["allowed"] and (dist != "ducal_residence_district" or rec["household"])
            if not dist:
                call, why = "none", "no 1.21 successor found"
            elif not ok:
                call, why = "no", "the province does not qualify in your converted campaign"
            elif src == "same key":
                call, why = "yes", f"same key in 1.21, inside the {dist.replace('_', ' ')}; the province qualifies"
            else:
                call, why = "maybe", src
            cards_c.append({"key": f"{rec['province']}:{old_key}", "rec": rec, "old_key": old_key, "dist": dist,
                            "bld": bld, "src": src, "call": call, "why": why,
                            "img": png(f"duchy_buildings/{f}"), "dimg": png(f"duchy_buildings/{dist.replace('_district', '')}") if dist else ""})
    pathlib.Path(out_html).write_text(render(cards_a, cards_b, cards_c, version), encoding="utf-8")
    print(f"wrote {out_html}: {len(cards_a)} 'same thing?' cards, {len(cards_b)} 'which one?' cards, "
          f"{len(cards_c)} duchy-capital cards")


def esc(s):
    return html.escape(str(s))


def render(cards_a, cards_b, cards_c=(), version="v1"):
    def where(c):
        parts = []
        for p in c["per_holding"]:
            ds = ", ".join(d["d"].replace("_district", "") + (" (gated)" if d["gated"] else "") for d in p["districts"])
            parts.append(f"{esc(p['holding'].replace('_holding', ''))} ({p['n']}): {esc(ds) or '<b>not hosted</b>'}")
        lv = " / ".join("-" if x is None else str(x) for x in c["level_req"])
        anywhere = ", ".join(h.replace("_holding", "") for h in c["anywhere"]) or "no holding type can build it"
        what = {"resource": ("resource district: player-built where the county has potential for its trade good; one per "
                             "province, replaceable (the game also places some at start)"),
                "holding": "the holding's own district (where the castle/city/temple building itself is), not a regular slot",
                "special": "special district (holy site or wonder): made by a great project or an event (add_special_district)",
                "duchy_capital": ("duchy-capital district: one per province, player-built where the county's holder "
                                  "also holds that province's duchy (only those provinces)"),
                "great": "great district: made by a great project or an event (set_great_district)",
                "mine": "special mine: placed at game start, or found during play by the survey events",
                "legendary": "legendary district: built through a legend",
                "trade": "trade location: placed by the trade system",
                "regular": "regular district: a slot the player builds"}
        lives = "<br>".join(f"lives in {esc(d)}: {esc(what.get(k, k))}" for d, k in c["lives_in"][:4])
        return (f"<div class=f>{'<br>'.join(parts)}<br>tiers {c['tiers']}, district level per tier: {esc(lv)}"
                f"<br><span class=dim>holding types that can build it: {esc(anywhere)}<br>{lives}</span></div>")

    a = []
    for i, c in enumerate(cards_a):
        u = c["cand"]
        a.append(f"""<div class=card data-kind=A data-key="{esc(c['key'])}">
<div class=pair><figure><img src="{c['old']}"><figcaption>1.20 {esc(c['family'])}<br>v17: {c['v17']}</figcaption></figure>
<figure><img src="{c['new']}"><figcaption>1.21 {esc(u['family'])}<br><span class=dim>{esc(u['icon'])}</span></figcaption></figure></div>
<div class=meta>imgcompare <b>{u['cos']}</b> ({esc(u['band'])}) &middot; my call: <b>{esc(c['call'])}</b> &mdash; {esc(c['why'])}</div>
{where(u)}
<div class=ans><label><input type=radio name="A{i}" value=yes> yes, related</label>
<label><input type=radio name="A{i}" value=no> no</label>
<input class=note placeholder="note (optional)"></div></div>""")
    b = []
    for i, c in enumerate(cards_b):
        opts = []
        for j, x in enumerate(c["cands"]):
            rec = " rec" if x["family"] == c["rec"] else ""
            opts.append(f"""<label class="opt{rec}"><input type=radio name="B{i}" value="{esc(x['family'])}">
<img src="{x['img']}"><div><b>{esc(x['family'])}</b>{' &larr; my pick' if rec else ''}<br>
<span class=dim>{esc(x['icon'])} &middot; imgcompare {x['cos']} ({esc(x['band'])})</span>{where(x)}</div></label>""")
        tiers = ", ".join(f"t{k}: {v}" for k, v in c["v17_tiers"].items())
        b.append(f"""<div class=card data-kind=B data-key="{esc(c['family'])}">
<div class=head><img src="{c['old']}"><div><b>1.20 {esc(c['family'])}</b> &middot; v17: {c['v17']} ({esc(tiers)})<br>
on {esc(', '.join(f"{h.replace('_holding', '')} {n}" for h, n in c['holdings'].items()))}<br>
my pick: <b>{esc(c['rec'])}</b> &mdash; {esc(c['why'])}</div></div>
{''.join(opts)}
<label class=opt><input type=radio name="B{i}" value="none"><div><b>none of these</b> (not carried; named in the report)</div></label>
<input class=note placeholder="note (optional)"></div>""")
    c = []
    for i, x in enumerate(cards_c):
        r = x["rec"]
        c.append(f"""<div class=card data-kind=C data-key="{esc(x['key'])}">
<div class=head><img src="{x['img']}"><div><b>province {esc(r['province'])}</b> ({esc(r['barony'])}, {esc(r['county'])}, {esc(r['duchy'])})<br>
1.20 duchy-capital building: <b>{esc(x['old_key'])}</b><br>
proposed: <b>{esc(x['bld'] or '-')}</b> in a <b>{esc((x['dist'] or '-').replace('_', ' '))}</b> <span class=dim>({esc(x['src'] or '')})</span><br>
<span class=dim>county holder {esc(r['county_holder'])}, duchy holder {esc(r['duchy_holder'])}, {esc(r['government'])};
allowed: {'yes' if r['allowed'] else 'no'}</span><br>
my call: <b>{esc(x['call'])}</b> &mdash; {esc(x['why'])}</div></div>
<div class=ans><label><input type=radio name="C{i}" value=yes> yes, carry it</label>
<label><input type=radio name="C{i}" value=no> no</label>
<input class=note placeholder="note (optional)"></div></div>""")
    duchy = (f"<h2>Duchy capitals ({len(cards_c)} provinces)</h2><p>Your campaign had these 1.20 duchy-capital buildings; "
             "the game's 1.21 conversion kept none. 1.21 keeps the same buildings inside duchy-capital districts, which a "
             "province may have when its county's holder also holds its duchy. Each card checks that in your converted "
             "campaign (v19).</p>" + "".join(c)) if c else ""
    key = f"s1-review-2026-11-19{'' if version == 'v1' else '-' + version}"
    return f"""<!DOCTYPE html><html><head><meta charset=utf-8><title>S1 review {esc(version)}: 1.20 buildings to 1.21</title>
<style>
body{{font:14px system-ui,sans-serif;max-width:1000px;margin:20px auto;background:#f4f4f4;color:#222}}
h2{{margin-top:32px}} .card{{background:#fff;border-radius:8px;padding:12px;margin:12px 0;box-shadow:0 1px 3px #0002}}
.pair{{display:flex;gap:24px}} figure{{margin:0;text-align:center}} img{{width:72px;height:72px;border:1px solid #ddd}}
.meta{{margin:8px 0}} .f{{font-size:12px;color:#444;margin:4px 0}} .dim{{color:#888;font-size:12px}}
.ans label{{margin-right:16px}} .note{{width:60%;margin-top:6px}} .head{{display:flex;gap:12px;align-items:center}}
.opt{{display:flex;gap:10px;align-items:flex-start;padding:6px;margin:6px 0;border:1px solid #eee;border-radius:6px}}
.opt.rec{{border-color:#4a8;background:#f3fbf6}} .done{{outline:2px solid #4a8}}
#bar{{position:sticky;top:0;background:#222;color:#fff;padding:8px 12px;border-radius:6px;z-index:9}}
#bar button{{margin-left:8px}}
</style></head><body>
<div id=bar><span id=count></span><button onclick="copyOut()">Copy answers</button><button onclick="dl()">Download answers</button>
<button onclick="if(confirm('Clear all answers?')){{localStorage.removeItem(K);location.reload()}}">Reset</button></div>
<h1>S1 review: what each 1.20 building becomes in 1.21</h1>
<p>Two kinds of card. <b>Same thing?</b> asks whether an old picture and a 1.21 picture are related (art unclear:
imgcompare 0.90-0.978, or a shared file name). <b>Which one?</b> lists a family's candidates that carry the same picture;
pick the one the old building should become, or none. Each card shows the imgcompare score and band, my own call and why,
and where the candidate can stand on the holdings your campaign has this family on. Progress is saved in this browser.
When done, <b>Copy answers</b> (paste into the chat) or <b>Download answers</b>.</p>
<h2>Which one? ({len(cards_b)} families)</h2>{''.join(b)}
<h2>Same thing? ({len(cards_a)} pairs)</h2>{''.join(a)}
{duchy}
<script>
const K='{key}';
const st=JSON.parse(localStorage.getItem(K)||localStorage.getItem('s1-review-2026-11-19')||'{{}}');
const cards=[...document.querySelectorAll('.card')];
function key(c){{return c.dataset.kind+':'+c.dataset.key}}
function save(){{const o={{}};cards.forEach(c=>{{const r=c.querySelector('input[type=radio]:checked');const n=c.querySelector('.note').value;
if(r||n)o[key(c)]={{answer:r?r.value:null,note:n||undefined}};c.classList.toggle('done',!!r)}});
localStorage.setItem(K,JSON.stringify(o));document.getElementById('count').textContent=Object.values(o).filter(x=>x.answer).length+' of '+cards.length+' answered';return o}}
cards.forEach(c=>{{const v=st[key(c)];if(v){{if(v.answer){{const r=[...c.querySelectorAll('input[type=radio]')].find(x=>x.value===v.answer);if(r)r.checked=true}}
if(v.note)c.querySelector('.note').value=v.note}};c.addEventListener('change',save);c.querySelector('.note').addEventListener('input',save)}});
save();
function out(){{return JSON.stringify({{page:K,answers:save()}},null,1)}}
function copyOut(){{navigator.clipboard.writeText(out()).then(()=>alert('Copied'))}}
function dl(){{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([out()],{{type:'application/json'}}));a.download='s1-review-answers.json';a.click()}}
</script></body></html>"""


if __name__ == "__main__":
    main(*sys.argv[1:])
