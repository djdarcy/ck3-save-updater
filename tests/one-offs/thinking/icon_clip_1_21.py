"""The icon map's ART signal, done with djdarcy's own imgcompare (CLIP embeddings, cosine similarity, his named bands).

djdarcy 2026-11-19: "We already have a tool called "imgcompare.py" ... that does cosine similarity checks. We can just
check for anything probably in the 0.8 to 0.9 bracket for similarity enough? I had it all mapped out with names in
that tool."

Uses C:/code/ImgCompare/imgcompare.py unchanged: load_models, compute_embeddings, cosine_similarity, classify_similarity.
The game's icons are DDS black silhouettes on transparency; CLIP takes RGB, and dropping alpha would leave every icon a
black square, so each icon is first flattened onto white and written as PNG to a scratch folder.

For every 1.20 family in the icon map's JSON (icon_map_1_21.py's output), compares its old picture
(old_buildings/<icon>.dds) with every 1.21 building icon outside old_buildings/, and prints the top matches with
imgcompare's band name. Writes <out.json>.

Prediction (written first): every pair the silhouette check called identical (REUSE, and NAME at IoU >= 0.9) scores
"same" (> 0.989) here; barracks' NAME icons (IoU 0.81, identical by eye) score at least "almost_same"; guild halls'
name-only icon (different art) scores below 0.9.
CONTROL: an old icon against its own REUSE copy must be "same".

Run: python -I -X utf8 tests/one-offs/thinking/icon_clip_1_21.py <1.21 game dir> <icon_map.json> <scratch dir> <out.json>
Reads the game's icons; writes PNGs under <scratch dir> and <out.json>. Needs torch, transformers and the CLIP model.
"""
import collections
import json
import pathlib
import sys

sys.path.insert(0, r"C:/code/ImgCompare")
import imgcompare  # noqa: E402  (djdarcy's tool, used as-is)

ICON_DIR = pathlib.Path("gfx/interface/icons/building_types")


def flatten(src: pathlib.Path, dst: pathlib.Path):
    from PIL import Image
    im = Image.open(src).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    dst.parent.mkdir(parents=True, exist_ok=True)
    bg.convert("RGB").save(dst)


def main(game, icon_map, scratch, out_json):
    root = pathlib.Path(game) / ICON_DIR
    scratch = pathlib.Path(scratch)
    rows = json.loads(pathlib.Path(icon_map).read_text(encoding="utf-8"))

    pngs = {}
    for p in sorted(root.rglob("*.dds")):
        rel = p.relative_to(root).with_suffix("").as_posix()
        dst = scratch / (rel + ".png")
        try:
            if not dst.exists():
                flatten(p, dst)
            pngs[rel] = dst
        except Exception as e:  # an icon PIL cannot decode is reported, not fatal
            print(f"skip {rel}: {e}")

    model, processor, device = imgcompare.load_models()
    emb = {rel: imgcompare.compute_embeddings(str(p), model, processor, device) for rel, p in pngs.items()}

    new = [rel for rel in emb if not rel.startswith("old_buildings/")]
    result, bands = [], collections.Counter()
    print("family | v17 | top 1.21 icons by cosine (band)")
    for r in rows:
        old = f"old_buildings/{r['old_icon']}" if r.get("old_icon") else None
        if old not in emb:
            result.append({"family": r["family"], "v17": r["v17"], "top": []})
            continue
        scored = sorted(((imgcompare.cosine_similarity(emb[old], emb[n]), n) for n in new), reverse=True)[:5]
        top = [{"icon": n, "cosine": round(s, 4), "band": imgcompare.classify_similarity(s)[0]} for s, n in scored]
        bands[top[0]["band"]] += r["v17"]
        result.append({"family": r["family"], "v17": r["v17"], "top": top})
        print(f"{r['family']} | {r['v17']} | " + "; ".join(f"{t['icon']} {t['cosine']} ({t['band']})" for t in top[:3]))
    total = sum(r["v17"] for r in rows)
    print("\nv17 buildings by the band of their family's best match:")
    for b, n in bands.most_common():
        print(f"  {b:32s} {n:6d} ({100 * n / total:.0f}%)")
    pathlib.Path(out_json).write_text(json.dumps(result, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(*sys.argv[1:])
