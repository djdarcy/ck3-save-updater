"""R19 dna-layout (S4 i): faces carried into the target's gene layout, by gene and template name.

Every test builds its own tiny common/genes folders and DNA strings; nothing reads a real install or save, and
nothing launches the game. The two layouts:

  old (the save's):  hair_color, skin_color (colour) | gene_a {t1=0, t2=1}, gene_b {u1=0}, gene_gone {g1=0}
  new (the target):  hair_color, skin_color (colour) | gene_b {u1=0}, gene_a {t2=0, t1=1, t3=2}, gene_new, gene_new2

so gene_a and gene_b swap places, gene_a's templates are renumbered (and t3 added), gene_gone is dropped, and two
genes are new. A special gene in each is never stored in DNA.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from ck3_save_migrator import cli, detect as D, dna
from ck3_save_migrator import lint as L
from ck3_save_migrator import record
from ck3_save_migrator import savefile as sf
from ck3_save_migrator.rules import REGISTRY, RuleContext
from tests import test_update as TU
from tests.fixtures.make_ck3 import build_ck3
from tests.test_update import game, run

saves = TU.saves
no_reference_from_the_environment = TU.no_reference_from_the_environment
R19 = next(r for r in REGISTRY if r.id == "R19")

COLOR = "color_genes = {\n\thair_color = { group = hair }\n\tskin_color = { group = skin }\n}\n"
SPECIAL = "special_genes = {\n\tmorph_genes = {\n\t\tgene_special = { s = { index = 0 } }\n\t}\n}\n"
OLD_MORPH = ("morph_genes = {\n\tgene_a = {\n\t\tt1 = { index = 0 }\n\t\tt2 = { index = 1 }\n\t}\n"
             "\tgene_b = { u1 = { index = 0 } }\n\tgene_gone = { g1 = { index = 0 } }\n}\n")
NEW_MORPH = ("morph_genes = {\n\tgene_b = { u1 = { index = 0 } }\n\tgene_a = {\n\t\tt2 = { index = 0 }\n"
             "\t\tt1 = { index = 1 }\n\t\tt3 = { index = 2 }\n\t}\n\tgene_new = { n = { index = 0 } }\n"
             "\tgene_new2 = { m = { index = 0 } }\n}\n")


def genes(root: Path, files: dict[str, str]) -> Path:
    g = root / "common" / "genes"
    g.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (g / name).write_text(text, encoding="utf-8-sig")
    return root


def old_layout(root: Path) -> Path:
    return genes(root, {"00_color.txt": COLOR, "01_morph.txt": OLD_MORPH, "02_special.txt": SPECIAL})


def new_layout(root: Path) -> Path:
    return genes(root, {"00_color.txt": COLOR, "01_morph.txt": NEW_MORPH, "02_special.txt": SPECIAL})


def b64(*places: tuple[int, int, int, int]) -> bytes:
    return base64.b64encode(bytes(b for p in places for b in p))


OLD_FACE = b64((10, 20, 30, 40), (1, 2, 3, 4), (0, 50, 1, 60), (0, 70, 0, 80), (0, 90, 0, 100))
NEW_FACE = b64((10, 20, 30, 40), (1, 2, 3, 4), (0, 70, 0, 80), (1, 50, 0, 60), (0, 128, 0, 128), (0, 128, 0, 128))


def layouts(tmp_path):
    src = dna.build_layout("old", [("vanilla", old_layout(tmp_path / "old"))])
    dst = dna.build_layout("new", [("vanilla", new_layout(tmp_path / "new"))])
    return src, dst


# --------------------------------------------------------------------------- the layout builder
def test_genes_are_in_file_name_order_then_declaration_order(tmp_path):
    root = genes(tmp_path, {"02_b.txt": "morph_genes = { gene_b = { x = { index = 0 } } }\n",
                            "01_a.txt": "morph_genes = { gene_a1 = { x = { index = 0 } } gene_a2 = { } }\n"})
    lay = dna.build_layout("t", [("vanilla", root)])
    assert [g["name"] for g in lay.genes] == ["gene_a1", "gene_a2", "gene_b"]


def test_file_order_not_category_order(tmp_path):
    """Measured on the founding save: file order fits (0 impossible places), all-colour-genes-first does not (7)."""
    root = genes(tmp_path, {"01_m.txt": "morph_genes = { gene_m = { x = { index = 0 } } }\n",
                            "02_c.txt": "color_genes = { gene_c = { group = c } }\n"})
    assert [g["name"] for g in dna.build_layout("t", [("vanilla", root)]).genes] == ["gene_m", "gene_c"]


def test_a_later_file_of_the_same_name_replaces_the_earlier_whole(tmp_path):
    van = genes(tmp_path / "van", {"01_a.txt": "morph_genes = { gene_a1 = { } gene_a2 = { } }\n",
                                   "02_b.txt": "morph_genes = { gene_b = { } }\n"})
    mod = genes(tmp_path / "mod", {"01_a.txt": "morph_genes = { gene_m = { } }\n"})
    lay = dna.build_layout("t", [("vanilla", van), ("mod", mod)])
    assert [g["name"] for g in lay.genes] == ["gene_m", "gene_b"]
    assert next(g for g in lay.genes if g["name"] == "gene_m")["src"] == "mod"


def test_special_genes_are_not_stored_and_a_mod_adds_genes(tmp_path):
    van = old_layout(tmp_path / "van")
    assert [g["name"] for g in dna.build_layout("v", [("vanilla", van)]).genes] == \
        ["hair_color", "skin_color", "gene_a", "gene_b", "gene_gone"]
    mod = genes(tmp_path / "mod", {"05_mod.txt": "accessory_genes = { gene_hat = { h = { index = 0 } } }\n"})
    lay = dna.build_layout("v+m", [("vanilla", van), ("mod", mod)])
    assert lay.places == 6 and lay.length == len(base64.b64encode(bytes(24))) == 32
    assert dna.chars(104) == 556                     # vanilla 1.8.2 and 1.20: 104 genes, 556 characters


# --------------------------------------------------------------------------- the translation
def test_the_same_layout_is_the_identity(tmp_path):
    src, _ = layouts(tmp_path)
    plan = dna.build_plan(src, src)
    assert plan.identity and dna.translate(OLD_FACE, plan) == (OLD_FACE, "kept", 0)


def test_moved_genes_remapped_templates_defaulted_and_dropped_genes(tmp_path):
    src, dst = layouts(tmp_path)
    plan = dna.build_plan(src, dst)
    new, how, extra = dna.translate(OLD_FACE, plan)
    assert (new, how, extra) == (NEW_FACE, "translated", 0)
    assert plan.defaulted == ["gene_new", "gene_new2"] and plan.dropped == ["gene_gone"]
    assert plan.moved >= 2 and plan.remapped == 1                     # gene_a's t1/t2 renumbered


def test_a_template_the_target_lacks_falls_to_0(tmp_path):
    a = dna.build_layout("a", [("v", genes(tmp_path / "a", {"1.txt": "morph_genes = { g = { x = { index = 0 } "
                                                                       "y = { index = 1 } } }\n"}))])
    b = dna.build_layout("b", [("v", genes(tmp_path / "b", {"1.txt": "morph_genes = { g = { y = { index = 0 } } }\n"}))])
    plan = dna.build_plan(a, b)
    assert plan.templates_lost == 1
    assert dna.b64d(dna.translate(b64((1, 9, 0, 8)), plan)[0]) == bytes([0, 9, 0, 8])   # y -> 0; x (0) -> 0, lost


def test_colour_genes_are_copied_whole(tmp_path):
    src, dst = layouts(tmp_path)
    out = dna.b64d(dna.translate(OLD_FACE, dna.build_plan(src, dst))[0])
    assert out[:8] == bytes([10, 20, 30, 40, 1, 2, 3, 4])            # template bytes far past any index, kept


def test_a_longer_string_loses_its_tail_and_a_shorter_one_is_left(tmp_path):
    src, dst = layouts(tmp_path)
    plan = dna.build_plan(src, dst)
    longer = b64(*[(0, 1, 0, 1)] * 8)                                 # 8 places against the source's 5
    new, how, extra = dna.translate(longer, plan)
    assert how == "translated" and extra == 3 and len(new) == dst.length
    shorter = b64((0, 1, 0, 1))
    assert dna.translate(shorter, plan) == (shorter, "left as is: shorter than its layout", 0)
    already = NEW_FACE
    assert dna.translate(already, plan) == (already, "already target", 0)


# --------------------------------------------------------------------------- the whole save
META = b'meta_data={\n\tsave_game_version=8\n\tversion="1.8.1"\n\tportraits_version=3\n\tmeta_date=987.10.27\n}\n'


def char(cid: int, face: bytes, name: str = "A") -> bytes:
    return f'{cid}={{\n\tfirst_name="{name}"\n\tdna="'.encode() + face + b'"\n\tbirth=900.1.1\n}\n'


def whole_body(faces: dict[int, bytes]) -> bytes:
    return (b"living={\n" + char(1, faces[1]) + char(2, faces[2]) + b"}\n"
            b"dead_unprunable={\n" + char(3, faces[3]) + b"}\n"
            b"characters={\n\tdead_prunable={\n" + char(4, faces[4]) + b"\t}\n}\n"
            b'portraits={\n\tsomething={\n\t\tdna="' + OLD_FACE + b'"\n\t}\n}\n')


def test_the_whole_save_every_face_at_the_target_length_and_the_version_stamped(tmp_path):
    old, new = old_layout(tmp_path / "old"), new_layout(tmp_path / "new")
    shorter = b64((0, 1, 0, 1))
    save = sf.parse_save(build_ck3(meta=META, body=whole_body({1: OLD_FACE, 2: NEW_FACE, 3: OLD_FACE, 4: shorter})))
    st = dna.setup(save_meta=save.meta, game_dir=new, old_game_dir=old, target_version="1.20.1.2", user=tmp_path)
    ctx = RuleContext(game_dir=new, old_game_dir=old)
    ctx.state["dna_setup"] = st
    res = R19.run(save, ctx)
    g = save.gamestate
    assert g.count(b'dna="' + NEW_FACE + b'"') == 4                   # 1, 3, the one outside an entry, and 2 kept
    assert b'dna="' + shorter + b'"' in g                             # left, counted
    assert b"portraits_version=5" in g and b"portraits_version=3" not in g
    o = res.extra["outcomes"]
    assert o["translated"] == ["1", "3"] and o["already target"] == ["2"]
    assert o["left as is: shorter than its layout"] == ["4"]
    assert res.extra["other_dna"] == {"translated": 1}
    assert res.extra["portraits_version"] == {"from": 3, "to": 5}
    assert res.extra["plans"][0]["dropped"] == ["gene_gone"] and res.extra["layouts"]["target"]["genes"] == 6
    sf.write_save(save, tmp_path / "out.ck3")
    assert b"portraits_version=5" in sf.read_save(tmp_path / "out.ck3").meta      # both copies


def test_a_transplanted_character_is_read_in_the_reference_layout(tmp_path):
    """Characters R17 added come from the reference: their faces are in the reference's layout, never guessed by
    length (vanilla 1.8 and 1.20 are both 556 characters)."""
    old, new = old_layout(tmp_path / "old"), new_layout(tmp_path / "new")
    ref_mod = genes(tmp_path / "refmod", {"09_hat.txt": "accessory_genes = { gene_hat = { h = { index = 0 } } }\n"})
    (tmp_path / "mod").mkdir()
    (tmp_path / "mod" / "refmod.mod").write_text(f'name="r"\npath="{ref_mod.as_posix()}"\n', encoding="utf-8")
    ref_meta = b'meta_data={\n\tversion="1.20.1.2"\n\tportraits_version=5\n\tmods={ "mod/refmod.mod" }\n}\n'
    ref_face = b64((10, 20, 30, 40), (1, 2, 3, 4), (0, 70, 0, 80), (1, 50, 0, 60), (0, 1, 0, 2), (0, 3, 0, 4),
                   (0, 66, 0, 66))                                   # the new layout + gene_hat
    save = sf.parse_save(build_ck3(meta=META, body=whole_body({1: OLD_FACE, 2: ref_face, 3: OLD_FACE, 4: OLD_FACE})))
    st = dna.setup(save_meta=save.meta, game_dir=new, old_game_dir=old, reference_meta=ref_meta,
                   target_version="1.20.1.2", user=tmp_path)
    assert st.reference.places == 7 and st.portraits_version == 5 and st.portraits_why == "the reference save's"
    ctx = RuleContext(game_dir=new)
    ctx.state.update(dna_setup=st, transplanted_characters={"2"})
    res = R19.run(save, ctx)
    assert "2" in res.extra["outcomes"]["translated"]
    assert b'dna="' + b64((10, 20, 30, 40), (1, 2, 3, 4), (0, 70, 0, 80), (1, 50, 0, 60), (0, 1, 0, 2),
                          (0, 3, 0, 4)) + b'"' in save.gamestate      # gene_hat dropped, the rest kept in place


# --------------------------------------------------------------------------- the target: dlc_load.json, --portrait-mods
def test_the_target_is_the_launchers_enabled_gene_mods_in_load_order(tmp_path):
    van = new_layout(tmp_path / "game")
    m1 = genes(tmp_path / "m1", {"07_m1.txt": "morph_genes = { gene_m1 = { } }\n"})
    m2 = genes(tmp_path / "m2", {"08_m2.txt": "morph_genes = { gene_m2 = { } }\n"})
    plain = tmp_path / "plain"
    plain.mkdir()
    (tmp_path / "mod").mkdir()
    for name, d in (("m1", m1), ("m2", m2), ("plain", plain)):
        (tmp_path / "mod" / f"{name}.mod").write_text(f'name="{name}"\npath="{d.as_posix()}"\n', encoding="utf-8")
    (tmp_path / "dlc_load.json").write_text(json.dumps({"enabled_mods": ["mod/m2.mod", "mod/plain.mod", "mod/m1.mod",
                                                                        "mod/gone.mod"]}), encoding="utf-8")
    lay, came, notes = dna.target_layout(van, None, tmp_path)
    assert [label for label, _ in lay.spec] == ["vanilla", "m2", "m1"]          # gene-shipping only, in load order
    assert came == "the launcher's dlc_load.json (4 enabled mod(s))"
    assert notes == ["dlc_load.json enables mod/gone.mod, which is not found: left out of the target layout"]
    lay, came, _ = dna.target_layout(van, [str(m1)], tmp_path)                  # --portrait-mods overrides it
    assert [label for label, _ in lay.spec] == ["vanilla", "m1"] and came == "--portrait-mods"
    lay, came, _ = dna.target_layout(van, [], tmp_path)
    assert [label for label, _ in lay.spec] == ["vanilla"] and came == "--portrait-mods (empty: vanilla)"


def faces_game(tmp_path, name="CK3"):
    g = game(tmp_path, name=name)
    new_layout(g)
    return g


def old_save_with_faces(saves, faces: dict[int, bytes], name="Faces.ck3") -> Path:
    s = saves / name
    s.write_bytes(build_ck3(meta=TU.OLD_META, body=TU.OLD_BODY + TU.SEED + whole_body(faces)))
    return s


def test_the_plan_names_the_source_and_target_layouts(tmp_path, saves, capsys):
    g = faces_game(tmp_path)
    s = old_save_with_faces(saves, {1: OLD_FACE, 2: OLD_FACE, 3: OLD_FACE, 4: OLD_FACE})
    old = old_layout(game(tmp_path, "1.8.1", "Old"))                   # a game folder, with the old genes
    code, out, _ = run(capsys, "status", str(s), "--game-dir", str(g), "--old-game-dir", str(old), "--plain",
                       "--reference", "none")
    flat = " ".join(out.split())
    assert "FACES" in out
    assert "source: the save's (1.8.1, vanilla): 5 genes, 28 characters" in flat
    assert "target: the target's (vanilla): 6 genes, 32 characters" in flat
    assert "from: no dlc_load.json found: vanilla" in flat
    assert "portraits_version 5 (the built-in table for the 1.20 line)" in flat
    assert "R19 dna-layout runs to_1_20 needed: 5 faces in another gene layout, and portraits_version 3 -> 5" in flat


# --------------------------------------------------------------------------- the detector
def test_the_detector_needed_on_old_faces_done_after_r19(tmp_path):
    old, new = old_layout(tmp_path / "old"), new_layout(tmp_path / "new")
    save = sf.parse_save(build_ck3(meta=META, body=whole_body({1: OLD_FACE, 2: OLD_FACE, 3: OLD_FACE, 4: OLD_FACE})))
    st = dna.setup(save_meta=save.meta, game_dir=new, old_game_dir=old, target_version="1.20.1.2", user=tmp_path)
    env = D.Env(game_dir=new, dna=st)
    d = D.detect("R19", save.gamestate, env)
    assert d.line() == "needed: 5 faces in another gene layout, and portraits_version 3 -> 5"
    ctx = RuleContext(game_dir=new)
    ctx.state["dna_setup"] = st
    R19.run(save, ctx)
    after = D.detect("R19", save.gamestate, D.Env(game_dir=new, dna=st))
    assert after.line() == "done: none found" and after.notes == ["4 faces are already in the target layout; left as "
                                                                  "they are"]


def test_a_save_whose_only_off_length_faces_are_left_is_not_needed(tmp_path):
    new = new_layout(tmp_path / "new")
    meta5 = META.replace(b"portraits_version=3", b"portraits_version=5")
    shorter = b64((0, 1, 0, 1))
    save = sf.parse_save(build_ck3(meta=meta5, body=whole_body({1: NEW_FACE, 2: NEW_FACE, 3: shorter, 4: NEW_FACE})
                                   .replace(b'dna="' + OLD_FACE, b'dna="' + NEW_FACE)))
    st = dna.setup(save_meta=save.meta, game_dir=new, target_version="1.20.1.2", user=tmp_path)
    d = D.detect("R19", save.gamestate, D.Env(game_dir=new, dna=st))
    assert d.state == "done" and d.left == ["1 face shorter than its layout"]
    assert d.line() == "done: nothing it can fix; not fixable: 1 face shorter than its layout"


def test_no_dna_skips_r19_with_a_reason(tmp_path, saves, capsys):
    g = faces_game(tmp_path)
    s = old_save_with_faces(saves, {1: OLD_FACE, 2: OLD_FACE, 3: OLD_FACE, 4: OLD_FACE})
    code, out, _ = run(capsys, "status", str(s), "--game-dir", str(g), "--plain", "--reference", "none", "--no-dna")
    r19 = next(ln for ln in out.splitlines() if ln.startswith("  R19"))
    assert "skipped" in r19 and "turned off by --no-dna" in " ".join(out.split())
    assert "FACES" not in out


# --------------------------------------------------------------------------- --portraits-version is gone
@pytest.mark.parametrize("command", ["migrate", "status", "update", "check"])
def test_portraits_version_is_gone_from_every_command(command, capsys):
    with pytest.raises(SystemExit):
        cli.main([command, "-h"])
    helptext = capsys.readouterr().out
    assert "--portraits-version" not in helptext and "--no-dna" in helptext and "--portrait-mods" in helptext


def test_an_old_record_carrying_portraits_version_reads_with_one_note(tmp_path, saves, capsys):
    s = old_save_with_faces(saves, {1: OLD_FACE, 2: OLD_FACE, 3: OLD_FACE, 4: OLD_FACE})
    record.append_update("111", "Faces", {"date": "d", "tool": "ck3-save-updater 0.0.1",
                                          "inputs": {"portraits_version": 5, "transplant": "off"}})
    code, out, _ = run(capsys, "status", str(s), "--game-dir", str(faces_game(tmp_path)), "--plain",
                       "--reference", "none")
    flat = " ".join(out.split())
    assert code == 0 and flat.count("the record's portraits_version is no longer used; R19 sets it from the "
                                    "target") == 1
    assert "--portraits-version" not in flat


# --------------------------------------------------------------------------- lint's DNA row
def test_lint_expects_the_target_layouts_length(tmp_path):
    g = whole_body({1: NEW_FACE, 2: NEW_FACE, 3: NEW_FACE, 4: NEW_FACE}).replace(OLD_FACE, NEW_FACE)
    rows = lambda length: [f for f in L.lint_gamestate(g, known=L.load_game_data(None, None, [], dna_length=length))
                           .findings if f.check == "Unexpected DNA string length"]          # noqa: E731
    assert rows(32) == []                                               # the target layout: no reject
    assert rows(556) and rows(556)[0].count == 5                        # vanilla's 556: every face off it


def test_a_layout_with_no_genes_never_empties_the_faces(tmp_path):
    """A game folder without common/genes (a broken install): R19 leaves every face, saying why."""
    nogenes = tmp_path / "nogenes"
    nogenes.mkdir()
    save = sf.parse_save(build_ck3(meta=META, body=whole_body({1: OLD_FACE, 2: OLD_FACE, 3: OLD_FACE, 4: OLD_FACE})))
    before = save.gamestate
    res = R19.run(save, RuleContext(game_dir=nogenes))
    assert save.gamestate == before and "no genes found" in res.extra["skipped"]
    st = dna.setup(save_meta=save.meta, game_dir=nogenes, user=tmp_path)
    assert D.detect("R19", before, D.Env(game_dir=nogenes, dna=st)).state == "unknown"
