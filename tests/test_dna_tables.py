"""Built-in gene tables (0.4.29, #8/#40): R19 reads an old save's faces without the old game's or the old portrait
mods' builds, from names-only tables the package ships (djdarcy 2026-11-06: "we want to have our own builtin table
to make this easy for most users"). The flags stay, and win; an installed build and a table compete on the faces."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from ck3_save_migrator import dna
from ck3_save_migrator import savefile as sf
from tests.fixtures.make_ck3 import build_ck3
from tests.test_dna import COLOR, OLD_FACE, OLD_MORPH, SPECIAL, genes, whole_body
from tests.test_dna_old_mods import meta, steam, workshop

ROOT = Path(__file__).resolve().parents[1]


def _generator():
    spec = importlib.util.spec_from_file_location("gene_table", ROOT / "scripts" / "gene_table.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _table(root: Path, folder: str, build: Path, **prov) -> Path:
    _generator().write_table(build, root / folder, {"name": folder, "version": "1", **prov})
    return root / folder


def _use(monkeypatch, root: Path) -> None:
    monkeypatch.setitem(dna._CACHE, "_tables", dna.load_tables(root))


# --------------------------------------------------------------------------- the table is what R19 reads
def test_a_table_loads_to_exactly_what_its_build_loads(tmp_path):
    """Names only, yet the same genes: names, categories, template indexes, file and order. A template name defined
    twice keeps the later index (as R19 reads it), special genes stay (a later special gene of the same name takes
    an earlier gene's place), and a file left with no genes is still written (it replaces a same-named file)."""
    build = genes(tmp_path / "build", {
        "00_color.txt": COLOR,
        "01_morph.txt": "morph_genes = {\n\tgene_a = {\n\t\tt1 = { index = 0 blend = 3 }\n\t\tt1 = { index = 4 }\n"
                        "\t\tt2 = { index = 1 settings = { x = 1 } }\n\t}\n\tgene_b = { u1 = { index = 0 } }\n}\n",
        "02_special.txt": SPECIAL,
        "03_empty.txt": "# nothing here\n"})
    t = _table(tmp_path / "tables", "t", build)
    a, b = dna.load_genes([("x", build)]), dna.load_genes([("x", t)])
    assert list(a) == list(b)
    assert all((a[k]["cat"], a[k]["tidx_by_name"], a[k]["file"], a[k]["order"]) ==
               (b[k]["cat"], b[k]["tidx_by_name"], b[k]["file"], b[k]["order"]) for k in a)
    assert a["gene_a"]["tidx_by_name"] == {"t1": 4, "t2": 1}
    assert (t / "common" / "genes" / "03_empty.txt").is_file()
    text = (t / "common" / "genes" / "01_morph.txt").read_text(encoding="utf-8")
    assert "blend = 3" not in text and "settings = {" not in text         # names and indexes only


def test_the_shipped_tables_stand_in_for_the_founding_campaigns_builds():
    by = {t["folder"].name: t for t in dna.gene_tables()}
    assert set(by) >= {"vanilla_1.8.2", "cfp_3.1.11", "epe_1.6.0"}
    assert {"1.7", "1.8"} <= set(by["vanilla_1.8.2"]["game_lines"])
    assert "mod/cfp_3.1.5.mod" in by["cfp_3.1.11"]["stands_in"]
    assert by["epe_1.6.0"]["stands_in"] == ["mod/ugc_2507209632.mod"]
    layout = dna.build_layout("t", [(k, by[k]["folder"]) for k in ("vanilla_1.8.2", "cfp_3.1.11", "epe_1.6.0")])
    assert layout.places == 130 and sum(len(g["tidx_by_name"]) for g in layout.genes) == 426


# --------------------------------------------------------------------------- which build R19 reads
def test_a_listed_mod_not_installed_is_read_from_its_table_and_the_flag_wins(tmp_path, monkeypatch):
    g = steam(tmp_path)
    old = genes(tmp_path / "oldmod", {"01_morph.txt": OLD_MORPH})
    _table(tmp_path / "tables", "oldmod_1", old, stands_in=["mod/oldmod.mod"])
    _use(monkeypatch, tmp_path / "tables")
    st = dna.setup(save_meta=meta(["mod/oldmod.mod"]), game_dir=g, user=tmp_path)
    assert [n for n, _ in st.source.spec] == ["vanilla", "oldmod_1"]
    assert dict(st.source_mods)["oldmod"].startswith("not installed; read from the built-in table (oldmod_1 1, ")
    flagged = dna.setup(save_meta=meta(["mod/oldmod.mod"]), game_dir=g, user=tmp_path, old_portrait_mods=[])
    assert [n for n, _ in flagged.source.spec] == ["vanilla"]                  # --old-portrait-mods "" : vanilla


def test_the_old_games_genes_come_from_its_table_unless_old_game_dir_is_given(tmp_path, monkeypatch):
    g = steam(tmp_path)
    old_game = genes(tmp_path / "old_game", {"00_color.txt": COLOR, "01_morph.txt": OLD_MORPH})
    _table(tmp_path / "tables", "vanilla_1.8.2", old_game, game_line="1.7,1.8")
    _use(monkeypatch, tmp_path / "tables")
    st = dna.setup(save_meta=meta([]), game_dir=g, user=tmp_path)
    assert st.source.spec[0][1] == tmp_path / "tables" / "vanilla_1.8.2"
    assert not any("taken from the installed game" in n for n in st.notes)
    given = dna.setup(save_meta=meta([]), game_dir=g, user=tmp_path, old_game_dir=old_game)
    assert given.source.spec[0][1] == old_game


def _competing(tmp_path, monkeypatch, installed_morph: str, table_morph: str):
    """The save lists Workshop mod 777, installed with ``installed_morph``; a table stands in for it with
    ``table_morph``; the faces are OLD_FACE (they fit OLD_MORPH)."""
    g = steam(tmp_path)
    workshop(tmp_path, "777", {"01_morph.txt": installed_morph, "00_color.txt": COLOR, "02_special.txt": SPECIAL})
    src = genes(tmp_path / "t_build", {"01_morph.txt": table_morph, "00_color.txt": COLOR, "02_special.txt": SPECIAL})
    _table(tmp_path / "tables", "mod777_old", src, stands_in=["mod/ugc_777.mod"])
    _use(monkeypatch, tmp_path / "tables")
    save = sf.parse_save(build_ck3(meta=meta(["mod/ugc_777.mod"]),
                                   body=whole_body({1: OLD_FACE, 2: OLD_FACE, 3: OLD_FACE, 4: OLD_FACE})))
    return dna.setup(save_meta=save.meta, game_dir=g, user=tmp_path, gamestate=lambda: save.gamestate)


ONE_TEMPLATE = OLD_MORPH.replace("\t\tt2 = { index = 1 }\n", "")     # gene_a has no index 1: the faces' t2 is lost


def test_an_installed_build_that_reads_the_faces_worse_loses_to_the_table(tmp_path, monkeypatch):
    """djdarcy 2026-11-06: an installed portrait mod that has updated since the save reads its faces wrongly
    (51,153 undefined values on the founding save). The faces decide."""
    st = _competing(tmp_path, monkeypatch, installed_morph=ONE_TEMPLATE, table_morph=OLD_MORPH)
    assert st.source.spec[-1][0] == "mod777_old"
    assert st.source_choice.startswith("the built-in tables fit the save's faces better")
    assert st.source_choice in st.notes


def test_an_installed_build_that_fits_as_well_is_kept(tmp_path, monkeypatch):
    st = _competing(tmp_path, monkeypatch, installed_morph=OLD_MORPH, table_morph=ONE_TEMPLATE)
    assert st.source.spec[-1][0] == "ugc_777"
    assert st.source_choice.startswith("the installed builds fit the save's faces at least as well")


def test_installed_now_names_the_mods_current_build(tmp_path, monkeypatch):
    g = steam(tmp_path)
    w = workshop(tmp_path, "888", {"x.txt": COLOR})
    (w / "descriptor.mod").write_text('name="Some Faces"\nversion="9.9"\n', encoding="utf-8")
    old = genes(tmp_path / "oldmod", {"01_morph.txt": OLD_MORPH})
    _table(tmp_path / "tables", "faces_1", old, workshop="888", stands_in=["mod/faces_old.mod"])
    _use(monkeypatch, tmp_path / "tables")
    st = dna.setup(save_meta=meta(["mod/faces_old.mod"]), game_dir=g, user=tmp_path)
    assert dict(st.source_mods)["faces_old"].endswith("installed now: Some Faces 9.9 (Workshop 888)")
