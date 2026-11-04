"""Show any character's face in the HUD by borrowing the player's slot (djdarcy, 2026-10-25: "if we can make him
20 to 30 again that should allow me to say if he looks correct or not").

Copies a donor's DNA (from any save of the campaign, 700 or 712 characters, translated to 1.20 vanilla by the
same gene-and-template plan as dna_poc.py) onto the PLAYER of <in.ck3>, and sets the player's sex to the donor's
and birth date to <age> years before the save's date. The game draws and keeps the player's face, so the HUD
portrait shows the donor's face at that age. A viewing aid only: the output is a MIGRATE_TEST__ save, never a
migration result.

Usage: python -I tests/one-offs/dna_show_as_player.py <in.ck3> <donor save> <donor id> <age> <out.ck3> [--keep-layout]

--with-dress: also copy the donor's culture= and faith= (portrait clothing follows them); same-save donors only.
--with-body: also copy traits (by name) and weight.
--keep-layout (2026-11-03, #40's judge): copy the donor's face as it is, untranslated -- for a donor whose save is
already in <in.ck3>'s layout (a 1.8.1 face onto a 1.8.1 save for the old build; a play7 or candidate face onto the
same save for 1.20). The output's file name must start with MIGRATE_TEST__ (refused otherwise).
"""
import base64
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
import dna_layout as D  # noqa: E402
import dna_poc as P  # noqa: E402
import dna_translate as X  # noqa: E402
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402


def entry(g: bytes, cid: bytes):
    for sec in ("living", "dead_unprunable", "characters/dead_prunable"):
        b = gs.locate(g, sec)
        for e in gs.iter_entries(g, *b.body):
            if e.key == cid:
                return e
    raise SystemExit(f"character {cid.decode()} not found")


def main():
    src_p, donor_p, did, age, out = sys.argv[1], sys.argv[2], sys.argv[3].encode(), int(sys.argv[4]), sys.argv[5]
    if not Path(out).name.startswith("MIGRATE_TEST__"):
        raise SystemExit(f"refused: the output must be a MIGRATE_TEST__ save, not {Path(out).name}")
    dg = sf.read_save(donor_p).gamestate
    de = entry(dg, did)
    blob = dg[de.start:de.end]
    old = re.search(rb'\n\t+dna="([^"]*)"', blob).group(1)
    female = re.search(rb"\n\t+female=yes", blob) is not None
    if "--keep-layout" in sys.argv:
        new = old
    else:
        src = D.dna_order(D.load_layout(P.SRC))
        dst_spec = P.DST
        if "--dst-mods" in sys.argv:
            # layout (c): 1.20 + the current Workshop mods, in the 987 save's order (CFP, EPE), the patch last
            ws = Path(r"E:\SteamLibrary\steamapps\workshop\content\1158310")
            dst_spec = P.DST + [("cfp", ws / "2220098919"), ("epe", ws / "2507209632"), ("patch", ws / "2996881191")]
        dst = D.dna_order(D.load_layout(dst_spec))
        raw = base64.b64decode(old + b"=" * (-len(old) % 4))
        new = base64.b64encode(X.build(src, dst).apply(raw[: 4 * len(src)]))

    save = sf.read_save(src_p)
    g = save.gamestate
    pid = re.search(rb"played_character=\{.*?character=(\d+)", g, re.S).group(1)
    date = re.search(rb"\n\tmeta_date=(\d+)\.(\d+)\.(\d+)", g)
    birth = b"%d.%s.%s" % (int(date.group(1)) - age, date.group(2), date.group(3))
    pe = entry(g, pid)
    body = g[pe.start:pe.end]
    body = re.sub(rb'(\n\tdna=")[^"]*(")', lambda m: m.group(1) + new + m.group(2), body, count=1)
    body = re.sub(rb"(\n\tbirth=)\S+", lambda m: m.group(1) + birth, body, count=1)
    body = re.sub(rb"\n\tfemale=yes", b"", body, count=1)
    if female:
        body = re.sub(rb"(\n\tbirth=\S+)", lambda m: m.group(1) + b"\n\tfemale=yes", body, count=1)
    notes = []
    if "--with-dress" in sys.argv:
        # portrait clothing follows culture and faith (djdarcy 2026-11-03 18:46: Uilleam in Beidh's clothes "might be
        # throwing me off"): copy the donor's culture= and faith= onto the player. Ids are only meaningful within one
        # save, so this is for a donor from the same save (or the same campaign line with unchanged ids)
        for key in (b"culture", b"faith"):
            dm = re.search(rb"\n\t" + key + rb"=(\d+)", blob)
            if not dm:
                notes.append(f"{key.decode()}: the donor has none, the player's kept")
                continue
            if re.search(rb"\n\t" + key + rb"=\d+", body):
                body = re.sub(rb"(\n\t" + key + rb"=)\d+", lambda m: m.group(1) + dm.group(1), body, count=1)
            else:
                body = re.sub(rb"(\n\tbirth=\S+)", lambda m: m.group(1) + b"\n\t" + key + b"=" + dm.group(1), body,
                              count=1)
            notes.append(f"{key.decode()} {dm.group(1).decode()} copied")
    if "--with-body" in sys.argv:
        # traits are indices into each save's own traits_lookup: translate by trait NAME; weight is copied as is
        def lookup(gg):
            b = gs.locate(gg, "traits_lookup")
            return re.findall(rb"[A-Za-z_0-9]+", gg[b.body[0]:b.body[1]])
        dl, tl = lookup(dg), lookup(g)
        dt = re.search(rb"\n\t+traits=\{([^}]*)\}", blob)
        names = [dl[int(x)] for x in dt.group(1).split()] if dt else []
        idx = [str(tl.index(n)).encode() for n in names if n in tl]
        missing = [n.decode() for n in names if n not in tl]
        body = re.sub(rb"(\n\ttraits=\{)[^}]*(\})", lambda m: m.group(1) + b" " + b" ".join(idx) + b" " + m.group(2),
                      body, count=1)
        dw = re.search(rb"\n\t+weight=\{([^}]*)\}", blob)
        if dw:
            w = b"\n\tweight={ " + b" ".join(dw.group(1).split()) + b" }"
            body = re.sub(rb"\n\tweight=\{[^}]*\}", lambda m: w, body, count=1)
        notes.append(f"traits {len(idx)} copied by name (missing in target: {missing}); weight "
                     f"{dw.group(1).split() if dw else 'none'}")
    save.replace_range(pe.start, pe.end, body)
    if "--pv5" in sys.argv:
        g2 = save.gamestate
        i = g2.find(b"portraits_version=3")
        if 0 < i < 5000:
            save.replace_range(i, i + len(b"portraits_version=3"), b"portraits_version=5")
            notes.append("portraits_version 3 -> 5")
    sf.write_save(save, out, force=True)
    print(f"player {pid.decode()} now shows {did.decode()} from {Path(donor_p).name}: dna {len(old)} -> {len(new)}, "
          f"{'female' if female else 'male'}, born {birth.decode()} (age {age}); {'; '.join(notes)}; wrote {out}")


if __name__ == "__main__":
    main()
