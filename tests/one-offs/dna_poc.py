"""DNA POC (U7, director 2026-10-25): one living character's 1.8.1 DNA translated to the 1.20 vanilla layout by
gene and template name; everyone else untouched (their 712-character DNA is still rejected by the game).

Prediction, written before running:
  TEST    (translated, 556 characters): the game accepts the DNA for this character -- no "Unexpected DNA string
          length" for them, and after load the save keeps `dna=` for the character (not `ethnicity=`). The face
          should resemble the 1.8.1 face where the 100 carried genes dominate; it will differ where the 26 EPE-only
          genes and the 3 unidentified tail places mattered.
  CONTROL (untouched, 712 characters): the DNA is rejected and the face is regenerated from an ethnicity.

Layouts: source (a) = 1.8.2 vanilla + cfp_3.1.11 + epe_1.6.0, the best available fit for places 0-129 of the 987
save's 133 (see the 18-32-18 decode note); places 130-132 are dropped. Target (b) = the 1.20 game install.

Usage: python -I tests/one-offs/dna_poc.py <in.ck3> <character id> <out dir>
Writes <out dir>/test.ck3 and <out dir>/control.ck3 (a byte copy of the input), plus poc.txt. Never writes into the
game's folders; staging into `save games` is a separate, explicit step.
"""
import base64
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
import dna_layout as D  # noqa: E402
import dna_translate as X  # noqa: E402
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

PROJECT = HERE.parents[1]
ORIG = PROJECT / "private" / "data" / "originals"
SRC = [("vanilla", PROJECT / "private" / "data" / "versions" / "1.8.2" / "game"),
       ("cfp", ORIG / "mods-2023" / "cfp_3.1.11"), ("epe", ORIG / "mods-2023" / "epe_1.6.0")]
DST = [("vanilla", Path(r"E:\SteamLibrary\steamapps\common\Crusader Kings III\game"))]


def main():
    src_p, cid, out = sys.argv[1], sys.argv[2].encode(), Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    save = sf.read_save(src_p)
    g = save.gamestate
    blk = gs.locate(g, "living")
    ent = next(e for e in gs.iter_entries(g, *blk.body) if e.key == cid)
    m = re.compile(rb'\n\tdna="([^"]*)"').search(g, ent.start, ent.end)
    old = m.group(1)
    raw = base64.b64decode(old + b"=" * (-len(old) % 4))
    src = D.dna_order(D.load_layout(SRC))
    dst_spec = DST
    if "--dst-mods" in sys.argv:   # layout (c): 1.20 + current CFP, EPE, patch (the 987 save's order, patch last)
        ws = Path(r"E:\SteamLibrary\steamapps\workshop\content\1158310")
        dst_spec = DST + [("cfp", ws / "2220098919"), ("epe", ws / "2507209632"), ("patch", ws / "2996881191")]
    dst = D.dna_order(D.load_layout(dst_spec))
    plan = X.build(src, dst)
    new_raw = plan.apply(raw[: 4 * len(src)])
    new = base64.b64encode(new_raw)
    lines = [
        f"input {src_p}; character {cid.decode()}",
        f"old dna: {len(old)} characters, {len(raw)} bytes; source layout {len(src)} genes (places past it dropped: "
        f"{len(raw) // 4 - len(src)})",
        f"new dna: {len(new)} characters, {len(new_raw)} bytes; target layout {len(dst)} genes",
        f"plan: kept {plan.kept}, templates remapped {plan.remapped}, templates with no target {plan.lost_templates}, "
        f"dropped {len(plan.dropped)}, defaulted {len(plan.defaulted)}",
        f"dropped genes: {plan.dropped}",
    ]
    save.replace_range(m.start(1), m.end(1), new)

    # second kind (optional): a face only the 967 save has, inserted for a character who has no DNA in the input
    if "--from-967" in sys.argv:
        k = sys.argv.index("--from-967")
        early, eid = sys.argv[k + 1], sys.argv[k + 2].encode()
        e_g = sf.read_save(early).gamestate
        e_blk = gs.locate(e_g, "living")
        e_ent = next(e for e in gs.iter_entries(e_g, *e_blk.body) if e.key == eid)
        em = re.compile(rb'\n\t+dna="([^"]*)"').search(e_g, e_ent.start, e_ent.end)
        e_old = em.group(1)
        e_raw = base64.b64decode(e_old + b"=" * (-len(e_old) % 4))
        e_new = base64.b64encode(plan.apply(e_raw[: 4 * len(src)]))
        g = save.gamestate
        blk = gs.locate(g, "living")
        tgt = next(e for e in gs.iter_entries(g, *blk.body) if e.key == eid)
        if re.compile(rb'\n\tdna="').search(g, tgt.start, tgt.end):
            raise SystemExit(f"character {eid.decode()} already has DNA in the input; not a 967-only face")
        sk = re.compile(rb"\n\tskill=\{[^}\n]*\}").search(g, tgt.start, tgt.end)
        save.replace_range(sk.end(), sk.end(), b'\n\tdna="' + e_new + b'"')
        lines.append(f"967-only face: character {eid.decode()} from {early}: {len(e_old)} characters -> "
                     f"{len(e_new)}, inserted after its skill line")

    def pv5(s) -> None:
        gg = s.gamestate
        i = gg.find(b"portraits_version=3")
        if 0 < i < 5000:
            s.replace_range(i, i + len(b"portraits_version=3"), b"portraits_version=5")
            lines.append("portraits_version 3 -> 5")

    if "--pv5" in sys.argv:
        pv5(save)
    sf.write_save(save, out / "test.ck3", force=True)
    if "--pv5" in sys.argv:
        ctrl = sf.read_save(src_p)       # CONTROL: the untranslated records, same header change
        pv5(ctrl)
        sf.write_save(ctrl, out / "control.ck3", force=True)
    else:
        shutil.copy2(src_p, out / "control.ck3")
    lines.append(f"wrote {out / 'test.ck3'} and {out / 'control.ck3'}")
    (out / "poc.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
