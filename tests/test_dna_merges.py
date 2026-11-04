"""R19's merge table (#40 S5b): a gene folded into another between portrait-mod builds is carried into the gene it
joined, as that gene's new template, but only where the joined gene is at weight 0 for that allele, and only with
--face-changes merges (default: 0.4.0's behaviour, the old gene dropped).

Synthetic layouts only; nothing reads a real install or save.
"""
from __future__ import annotations

from ck3_save_migrator import dna
from tests.test_dna import COLOR, genes

OLD = ("morph_genes = {\n\tgene_bs_eye_fold_shape = {\n\t\teye_fold_shape_neg = { index = 0 }\n"
       "\t\teye_fold_shape_pos = { index = 1 }\n\t}\n\tgene_bs_eye_fold_2 = {\n"
       "\t\tvanilla_eye_fold_2 = { index = 0 }\n\t\teye_fold_2 = { index = 1 }\n\t}\n}\n")
NEW = ("morph_genes = {\n\tgene_bs_eye_fold_shape = {\n\t\teye_fold_shape_neg = { index = 0 }\n"
       "\t\teye_fold_shape_pos = { index = 1 }\n\t\teye_fold_shape_neg_02 = { index = 2 }\n"
       "\t\teye_fold_shape_02_neg = { index = 3 }\n\t}\n}\n")


def layouts(tmp_path):
    src = dna.build_layout("old", [("vanilla", genes(tmp_path / "o", {"00_c.txt": COLOR, "01_m.txt": OLD}))])
    dst = dna.build_layout("new", [("vanilla", genes(tmp_path / "n", {"00_c.txt": COLOR, "01_m.txt": NEW}))])
    return src, dst


def face(fold, fold2):
    """colour x2, then gene_bs_eye_fold_shape and gene_bs_eye_fold_2 as (t, v, t, v)."""
    return bytes([10, 20, 30, 40, 1, 2, 3, 4, *fold, *fold2])


def fold_of(dst, out):
    p = [g["name"] for g in dst.genes].index("gene_bs_eye_fold_shape")
    return tuple(out[p * 4: p * 4 + 4])


def test_a_merge_never_overwrites_a_set_weight_or_carries_an_unset_one(tmp_path):
    """CONSEQUENCE: 6 (behaviour) -- a face's own eye fold is never replaced by the old gene's value."""
    src, dst = layouts(tmp_path)
    plan = dna.build_plan(src, dst, merges=dna.MERGES)
    # dominant already has a fold (weight 40): kept; recessive fold_2 at weight 0: nothing to carry
    assert fold_of(dst, plan.apply(face((1, 40, 0, 0), (1, 200, 1, 0)))) == (1, 40, 0, 0)
    # the old gene's empty template (vanilla_eye_fold_2) carries nothing either
    assert fold_of(dst, plan.apply(face((0, 0, 0, 0), (0, 200, 0, 200)))) == (0, 0, 0, 0)


def test_with_merges_the_old_value_lands_on_the_new_template_where_the_gene_is_unset(tmp_path):
    """CONSEQUENCE: 5 (behaviour) -- the old gene's value arrives on today's template at the same weight."""
    src, dst = layouts(tmp_path)
    plan = dna.build_plan(src, dst, merges=dna.MERGES)
    assert plan.merged == ["gene_bs_eye_fold_2"] and "gene_bs_eye_fold_2" not in plan.dropped
    # both alleles at weight 0: each takes eye_fold_shape_neg_02 (index 2), value scaled by 1 / 0.95
    assert fold_of(dst, plan.apply(face((0, 0, 1, 0), (1, 95, 1, 190)))) == (2, 100, 2, 200)
    # the scale never passes 255
    assert fold_of(dst, plan.apply(face((0, 0, 0, 0), (1, 250, 1, 250)))) == (2, 255, 2, 255)


def test_the_setup_applies_merges_only_when_the_switch_names_them(tmp_path):
    """CONSEQUENCE: 5 (behaviour) -- merges stay opt-in; 0.4.0's faces are the default."""
    src, dst = layouts(tmp_path)
    assert dna.Setup(src, dst).plans()[0].merged == []
    assert dna.Setup(src, dst, face_changes=("renames",)).plans()[0].merged == []
    assert dna.Setup(src, dst, face_changes=("merges",)).plans()[0].merged == ["gene_bs_eye_fold_2"]


def test_without_merges_the_old_gene_is_dropped(tmp_path):
    """CONSEQUENCE: 4 (behaviour) -- without the switch the plan is 0.4.0's: the old gene reported dropped."""
    src, dst = layouts(tmp_path)
    plan = dna.build_plan(src, dst)
    assert "gene_bs_eye_fold_2" in plan.dropped and plan.merged == []
    assert fold_of(dst, plan.apply(face((0, 0, 1, 0), (1, 200, 1, 95)))) == (0, 0, 1, 0)
