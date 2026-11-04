"""R19's follow-up (#39): --old-portrait-mods, the wrong-layout signal, the missing-mod note, and the target that
drops genes. Synthetic gene folders only, laid out as a Steam library so a Workshop id resolves:

  <tmp>/steamapps/common/CK3/game                 the installed game (the new layout's genes)
  <tmp>/steamapps/workshop/content/1158310/<id>   Workshop mods
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from ck3_save_migrator import dna
from ck3_save_migrator import detect as D
from ck3_save_migrator import record
from ck3_save_migrator import savefile as sf
from tests import test_update as TU
from tests.fixtures.make_ck3 import build_ck3, make_game_dir
from tests.test_dna import NEW_FACE, OLD_FACE, b64, genes, new_layout, old_layout, whole_body
from tests.test_update import run

saves = TU.saves
no_reference_from_the_environment = TU.no_reference_from_the_environment

HAT = "accessory_genes = { gene_hat = { h = { index = 0 } } }\n"


def steam(tmp_path) -> Path:
    g = make_game_dir(tmp_path / "steamapps" / "common" / "CK3" / "game")
    (g.parent / "launcher").mkdir(exist_ok=True)
    (g.parent / "launcher" / "launcher-settings.json").write_text(json.dumps({"rawVersion": "1.20.1.2"}))
    new_layout(g)
    return g


def workshop(tmp_path, wid: str, files: dict[str, str]) -> Path:
    return genes(tmp_path / "steamapps" / "workshop" / "content" / "1158310" / wid, files)


def meta(mods: list[str]) -> bytes:
    listed = " ".join(f'"{m}"' for m in mods)
    return (b'meta_data={\n\tsave_game_version=8\n\tversion="1.8.1"\n\tportraits_version=3\n\tmeta_date=987.10.27\n'
            b"\tmods={ " + listed.encode() + b" }\n}\n")


# --------------------------------------------------------------------------- precedence
def test_given_replaces_the_listed_mods_empty_is_vanilla_absent_uses_the_installed_builds(tmp_path):
    g = steam(tmp_path)
    workshop(tmp_path, "111", {"05_today.txt": HAT})                    # today's build of the listed mod
    own = genes(tmp_path / "own_build", {"05_old.txt": "morph_genes = { gene_old_build = { o = { index = 0 } } }\n"})
    m = meta(["mod/ugc_111.mod"])
    absent = dna.setup(save_meta=m, game_dir=g, user=tmp_path)
    assert [n for n, _ in absent.source.spec] == ["vanilla", "ugc_111"]
    assert "gene_hat" in [x["name"] for x in absent.source.genes]
    given = dna.setup(save_meta=m, game_dir=g, user=tmp_path, old_portrait_mods=[str(own)])
    assert [d for _, d in given.source.spec][1:] == [own]                 # replaces the listed mod
    assert "gene_hat" not in [x["name"] for x in given.source.genes]
    assert "gene_old_build" in [x["name"] for x in given.source.genes]
    empty = dna.setup(save_meta=m, game_dir=g, user=tmp_path, old_portrait_mods=[])
    assert [n for n, _ in empty.source.spec] == ["vanilla"]
    by_id = dna.setup(save_meta=meta([]), game_dir=g, user=tmp_path, old_portrait_mods=["111"])
    assert [n for n, _ in by_id.source.spec] == ["vanilla", "111"]        # a Workshop id resolves too
    assert dna.unresolved(["111", str(own), "999", str(tmp_path / "nope")], g) == ["999", str(tmp_path / "nope")]


def test_an_entry_resolving_to_nothing_is_refused_by_name_and_nothing_is_written(tmp_path, saves, capsys):
    g = steam(tmp_path)
    s = saves / "Faces.ck3"
    s.write_bytes(build_ck3(meta=TU.OLD_META, body=TU.OLD_BODY + TU.SEED + whole_body({i: OLD_FACE for i in (1, 2, 3, 4)})))
    before = sorted(p.name for p in saves.iterdir())
    code, out, err = run(capsys, "update", str(s), "--game-dir", str(g), "--reference", "none", "--no-lint",
                         "--old-portrait-mods", "999")
    assert code == 1 and 'REFUSED: --old-portrait-mods "999" is no installed Workshop mod and no folder' in err
    assert sorted(p.name for p in saves.iterdir()) == before
    code, _, err = run(capsys, "migrate", str(s), "--game-dir", str(g), "--reference", "none", "--no-lint",
                       "--old-portrait-mods", "999", "-o", str(tmp_path / "out.ck3"))
    assert code == 1 and '--old-portrait-mods "999" is no installed Workshop mod' in err
    assert not (tmp_path / "out.ck3").exists()


def has(out: str, text: str) -> bool:
    """``text`` in the plan's output, ignoring whitespace: the plan wraps a long path inside the path itself, so a
    temp folder longer than this machine's (CI's runneradmin) splits it across lines."""
    return "".join(text.split()) in "".join(out.split())


# --------------------------------------------------------------------------- FACES names each source mod
def test_faces_names_each_source_mod_and_its_origin(tmp_path, saves, capsys):
    g = steam(tmp_path)
    workshop(tmp_path, "111", {"05_today.txt": HAT})
    s = saves / "Faces.ck3"
    m = TU.OLD_META.replace(b"}\n", b'\tmods={ "mod/ugc_111.mod" "mod/ugc_222.mod" }\n}\n', 1)
    s.write_bytes(build_ck3(meta=m, body=TU.OLD_BODY + TU.SEED + whole_body({i: OLD_FACE for i in (1, 2, 3, 4)})))
    code, out, _ = run(capsys, "status", str(s), "--game-dir", str(g), "--reference", "none", "--plain")
    flat = " ".join(out.split())
    assert "source mod: ugc_111: the installed build of mod/ugc_111.mod" in flat
    assert "source mod: ugc_222: not installed" in flat
    own = old_layout(tmp_path / "own")
    code, out, _ = run(capsys, "status", str(s), "--game-dir", str(g), "--reference", "none", "--plain",
                       "--old-portrait-mods", str(own))
    assert has(out, f"source mod: own: --old-portrait-mods: {own}") and "not installed" not in out


# --------------------------------------------------------------------------- the record
def test_the_record_keeps_it_and_the_next_update_pre_fills_it(tmp_path, saves, capsys):
    g = steam(tmp_path)
    own = old_layout(tmp_path / "own")
    body = TU.OLD_BODY + TU.SEED + whole_body({i: OLD_FACE for i in (1, 2, 3, 4)})
    first = saves / "Faces.ck3"
    first.write_bytes(build_ck3(meta=TU.OLD_META, body=body))
    code, _, err = run(capsys, "update", str(first), "--game-dir", str(g), "--reference", "none", "--no-lint",
                       "--old-portrait-mods", str(own), "--wos-shape", "faith")
    assert code == 0, err
    assert record.read_record("111")["update"][-1]["inputs"]["old_portrait_mods"] == [str(own)]
    later = saves / "Faces_later.ck3"
    later.write_bytes(build_ck3(meta=TU.OLD_META, body=body))
    code, out, _ = run(capsys, "status", str(later), "--game-dir", str(g), "--reference", "none", "--plain")
    assert has(out, f"pre-filled: --old-portrait-mods {own}") and has(out, "(from the record of Faces)")
    assert has(out, f"source mod: own: --old-portrait-mods: {own}")
    for f in (own / "common" / "genes").iterdir():                      # the recorded folder vanishes
        f.unlink()
    (own / "common" / "genes").rmdir()
    (own / "common").rmdir()
    own.rmdir()
    code, out, _ = run(capsys, "status", str(later), "--game-dir", str(g), "--reference", "none", "--plain")
    assert code == 0 and has(out, f"the record of Faces has --old-portrait-mods {own}, which no longer exists; not used")
    assert not has(out, "pre-filled: --old-portrait-mods")


# --------------------------------------------------------------------------- transplanted characters
def test_transplanted_characters_keep_the_reference_layout_with_the_flag(tmp_path):
    g = steam(tmp_path)
    own = old_layout(tmp_path / "own")
    ref_meta = b'meta_data={\n\tversion="1.20.1.2"\n\tportraits_version=5\n}\n'
    st = dna.setup(save_meta=meta([]), game_dir=g, reference_meta=ref_meta, user=tmp_path, old_portrait_mods=[str(own)])
    assert own in [d for _, d in st.source.spec] and own not in [d for _, d in st.reference.spec]
    gstate = whole_body({1: OLD_FACE, 2: NEW_FACE, 3: OLD_FACE, 4: OLD_FACE})
    res = dna.plan_save(gstate, st, {"2"})
    assert "2" in res.outcomes["kept"]                                  # read in the reference's (= the target's)


# --------------------------------------------------------------------------- the wrong-layout signal
def test_a_template_index_the_source_gene_does_not_define_is_counted_apart(tmp_path):
    g = steam(tmp_path)
    src_root = old_layout(tmp_path / "src")
    st = dna.setup(save_meta=meta([]), game_dir=g, old_game_dir=src_root, user=tmp_path)
    bad = b64((10, 20, 30, 40), (1, 2, 3, 4), (5, 50, 1, 60), (0, 70, 9, 80), (0, 90, 0, 100))   # gene_a 5, gene_b 9
    gstate = whole_body({1: bad, 2: OLD_FACE, 3: OLD_FACE, 4: OLD_FACE})
    res = dna.plan_save(gstate, st)
    assert res.impossible == Counter({"gene_a": 1, "gene_b": 1})
    assert st.plans()[0].templates_lost == 0                            # apart from templates_lost
    d = D.detect("R19", gstate, D.Env(game_dir=g, dna=st))
    assert "2 template indexes the source layout does not define (gene_a, gene_b)" in d.notes
    assert ("the source layout is probably not the save's; give the save's own mod builds with --old-portrait-mods"
            in d.notes)
    good = whole_body({1: OLD_FACE, 2: OLD_FACE, 3: OLD_FACE, 4: OLD_FACE})
    assert not dna.plan_save(good, st).impossible
    assert not any("probably not the save's" in n for n in D.detect("R19", good, D.Env(game_dir=g, dna=st)).notes)


def test_a_handful_among_many_faces_is_reported_without_doubting_the_layout(tmp_path):
    """CONSEQUENCE: 4 (behaviour) -- a stand-in layout's one-template gap is not called the wrong layout (#40 S8)."""
    g = steam(tmp_path)
    st = dna.setup(save_meta=meta([]), game_dir=g, old_game_dir=old_layout(tmp_path / "src"), user=tmp_path)
    bad = b64((10, 20, 30, 40), (1, 2, 3, 4), (5, 50, 1, 60), (0, 70, 0, 80), (0, 90, 0, 100))   # gene_a 5 only
    from tests.test_dna import char
    gstate = b"living={\n" + char(1, bad) + b"".join(char(i, OLD_FACE) for i in range(2, 1001)) + b"}\n"
    res = dna.plan_save(gstate, st)
    assert sum(res.impossible.values()) == 1 and res.template_bytes >= 1000 and not res.wrong_layout
    notes = D.detect("R19", gstate, D.Env(game_dir=g, dna=st)).notes
    assert "1 template index the source layout does not define (gene_a)" in notes
    assert not any("probably not the save's" in n for n in notes)
    assert any(n.startswith("too few to doubt the source layout (1 of ") for n in notes)


def test_the_report_counts_them_by_gene(tmp_path):
    from ck3_save_migrator.rules import REGISTRY, RuleContext
    g = steam(tmp_path)
    st = dna.setup(save_meta=meta([]), game_dir=g, old_game_dir=old_layout(tmp_path / "src"), user=tmp_path)
    bad = b64((10, 20, 30, 40), (1, 2, 3, 4), (5, 50, 1, 60), (0, 70, 0, 80), (0, 90, 0, 100))
    save = sf.parse_save(build_ck3(meta=meta([]), body=whole_body({1: bad, 2: OLD_FACE, 3: OLD_FACE, 4: OLD_FACE})))
    ctx = RuleContext(game_dir=g)
    ctx.state["dna_setup"] = st
    res = next(r for r in REGISTRY if r.id == "R19").run(save, ctx)
    assert res.extra["template_indexes_the_source_layout_does_not_define"] == {
        "count": 1, "of_template_bytes": 20, "wrong_layout": True, "by_gene": {"gene_a": 1}}


# --------------------------------------------------------------------------- the missing-mod note
def test_the_missing_mod_note_is_one_line_and_not_shown_with_the_flag(tmp_path):
    g = steam(tmp_path)
    m = meta(["mod/cfp_3.1.5.mod", "mod/ugc_1.mod", "mod/ugc_2.mod", "mod/ugc_3.mod", "mod/ugc_4.mod", "mod/ugc_5.mod"])
    st = dna.setup(save_meta=m, game_dir=g, user=tmp_path)
    lines = [n for n in st.notes if "is not installed" in n]
    assert lines == ["the save lists mod/cfp_3.1.5.mod (and 5 others), which is not installed; if it shipped portrait "
                     "genes, the faces R19 translates may come out wrong; give the save's own build with "
                     "--old-portrait-mods"]
    one = dna.setup(save_meta=meta(["mod/a.mod", "mod/b.mod"]), game_dir=g, user=tmp_path)
    assert any(n.startswith("the save lists mod/a.mod (and 1 other), which") for n in one.notes)
    flag = dna.setup(save_meta=m, game_dir=g, user=tmp_path, old_portrait_mods=[])
    assert not any("is not installed" in n for n in flag.notes)


# --------------------------------------------------------------------------- the target that drops genes
def test_the_target_dropping_genes_the_faces_use_is_said(tmp_path):
    g = steam(tmp_path)
    st = dna.setup(save_meta=meta([]), game_dir=g, old_game_dir=old_layout(tmp_path / "src"), user=tmp_path)
    assert ("the target layout drops 1 gene the faces use (gene_gone); set the launcher's playset to the mods you "
            "will play with, or give --portrait-mods") in st.notes
    same = dna.setup(save_meta=meta([]), game_dir=g, user=tmp_path)    # source = target: nothing dropped
    assert not any("drops" in n for n in same.notes)
