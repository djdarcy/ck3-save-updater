"""R19's known genes (#40; djdarcy 2026-11-03: "the smallest piece to make epe and cfp reusable for the future"): with
--face-changes known-genes, a face exactly a known build's appended genes longer than the save's layout is read with
those genes, from a names-only table shipped with the tool, and carried by name; every other face is read as before.

Synthetic layouts and a synthetic table only, except the last test, which reads the shipped table's names.
"""
from __future__ import annotations

import base64

import pytest

from ck3_save_migrator import dna
from tests.test_dna import COLOR, char, genes

OLD = "morph_genes = {\n\tgene_a = { a0 = { index = 0 } a1 = { index = 1 } }\n\tgene_last = { l0 = { index = 0 } }\n}\n"
TAIL = "morph_genes = {\n\tgene_t = {\n\t\tt0 = { index = 0 }\n\t\tt1 = { index = 1 }\n\t}\n}\n"
NEW = ("morph_genes = {\n\tgene_a = { a0 = { index = 0 } a1 = { index = 1 } }\n\tgene_last = { l0 = { index = 0 } }\n"
       "\tgene_t = {\n\t\tt0 = { index = 0 }\n\t\tt1 = { index = 1 }\n\t}\n\tgene_new = { n = { index = 0 } }\n}\n")
COL = (10, 20, 30, 40, 1, 2, 3, 4)
BASE = bytes([*COL, 1, 9, 0, 8, 0, 7, 0, 6])          # colour x2, gene_a, gene_last
LONG = BASE + bytes([1, 200, 1, 150])                   # ... and gene_t, the known build's appended gene


@pytest.fixture
def known(tmp_path, monkeypatch):
    genes(tmp_path / "known" / "tail", {"zz_t.txt": TAIL})
    monkeypatch.setattr(dna, "KNOWN_GENES", tmp_path / "known")
    monkeypatch.setattr(dna, "KNOWN_TAILS", [("tail", "gene_last")])
    src = dna.build_layout("old", [("vanilla", genes(tmp_path / "o", {"00_c.txt": COLOR, "01_m.txt": OLD}))])
    dst = dna.build_layout("new", [("vanilla", genes(tmp_path / "n", {"00_c.txt": COLOR, "01_m.txt": NEW}))])
    return src, dst


def t_of(dst, face: bytes) -> tuple:
    p = [g["name"] for g in dst.genes].index("gene_t")
    return tuple(face[p * 4: p * 4 + 4])


def faces_out(st, faces: dict[int, bytes]):
    g = b"living={\n" + b"".join(char(i, base64.b64encode(f)) for i, f in faces.items()) + b"}\n"
    res = dna.plan_save(g, st)
    return res, {e[0]: base64.b64decode(e[2]) for e in res.edits}


def test_a_face_with_the_known_genes_carries_them_and_a_shorter_face_is_read_as_before(known):
    """CONSEQUENCE: 6 (behaviour) -- the appended genes arrive by name; a face without them is untouched by the table."""
    src, dst = known
    st = dna.Setup(src, dst, face_changes=("known-genes",))
    res, out = faces_out(st, {1: BASE, 2: LONG})
    assert res.known_genes == 1 and not res.dropped_places
    long_out, base_out = sorted(out.items())[1][1], sorted(out.items())[0][1]
    assert t_of(dst, long_out) == (1, 200, 1, 150)
    assert t_of(dst, base_out) == (0, 128, 0, 128)            # no such gene in a face at the base length: the middle


def test_without_the_switch_the_appended_places_are_dropped(known):
    """CONSEQUENCE: 5 (behaviour) -- known-genes stays opt-in; 0.4.0's reading drops the extra places."""
    src, dst = known
    st = dna.Setup(src, dst)
    assert st.tail_plans() == {}
    res, out = faces_out(st, {1: LONG})
    assert res.known_genes == 0 and sum(res.dropped_places.values()) == 1
    assert t_of(dst, next(iter(out.values()))) == (0, 128, 0, 128)


def test_the_table_applies_only_after_the_gene_its_build_follows(known, monkeypatch):
    """CONSEQUENCE: 6 (behaviour) -- a different mod's longer faces are never read with another mod's genes."""
    src, dst = known
    monkeypatch.setattr(dna, "KNOWN_TAILS", [("tail", "gene_a")])        # the source does not end with gene_a
    assert dna.Setup(src, dst, face_changes=("known-genes",)).tail_plans() == {}


def test_the_shipped_table_holds_names_only_and_reads_as_epes_three_late_2022_genes():
    """CONSEQUENCE: 4 (behaviour) -- the table ships with the package and names the genes the faces carry."""
    d = dna.KNOWN_GENES / "epe_2022-12_tail"
    text = (d / "common" / "genes" / "zz_epe_2022_12_tail.txt").read_text(encoding="utf-8")
    assert "setting = {" not in text and "attribute =" not in text                 # none of EPE's own settings
    lay = dna.build_layout("t", [("t", d)])
    assert [g["name"] for g in lay.genes] == ["hair_aging", "gene_bs_eye_lower_lid_size", "gene_bs_eye_shape"]
    assert lay.genes[2]["tidx_by_name"] == {"vanilla_eye_shape": 0, "eye_shape_01": 1}
