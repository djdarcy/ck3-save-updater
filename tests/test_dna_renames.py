"""R19's rename table (#40 S5): a gene renamed between portrait-mod builds is carried under its new name, but only
with --face-changes renames (default: 0.4.0's behaviour, the old gene dropped and the new one defaulted).

Synthetic layouts only; nothing reads a real install or save.
"""
from __future__ import annotations

from ck3_save_migrator import dna
from tests.test_dna import COLOR, genes

OLD = ("morph_genes = {\n\tgene_bs_head_round_shape = {\n\t\tvanilla_head_round_shape = { index = 0 }\n"
       "\t\thead_round_shape = { index = 1 }\n\t}\n\tgene_keep = { k = { index = 0 } }\n}\n")
NEW = ("morph_genes = {\n\tgene_keep = { k = { index = 0 } }\n\tgene_bs_head_shape = {\n"
       "\t\tvanilla_head_round_shape = { index = 0 }\n\t\thead_round_shape = { index = 1 }\n"
       "\t\thead_archetype_shape_01 = { index = 2 }\n\t}\n}\n")
FACE = bytes([10, 20, 30, 40, 1, 2, 3, 4, 1, 77, 0, 66, 0, 9, 0, 8])     # colour x2, round shape (1, 77), keep


def layouts(tmp_path):
    src = dna.build_layout("old", [("vanilla", genes(tmp_path / "o", {"00_c.txt": COLOR, "01_m.txt": OLD}))])
    dst = dna.build_layout("new", [("vanilla", genes(tmp_path / "n", {"00_c.txt": COLOR, "01_m.txt": NEW}))])
    return src, dst


def place(dst, name, out):
    p = [g["name"] for g in dst.genes].index(name)
    return tuple(out[p * 4: p * 4 + 4])


def test_without_renames_the_old_gene_is_dropped_and_the_new_one_defaulted(tmp_path):
    src, dst = layouts(tmp_path)
    plan = dna.build_plan(src, dst)
    assert "gene_bs_head_round_shape" in plan.dropped and "gene_bs_head_shape" in plan.defaulted
    assert place(dst, "gene_bs_head_shape", plan.apply(FACE)) == (0, 128, 0, 128)


def test_with_renames_the_value_and_template_are_carried_by_name(tmp_path):
    src, dst = layouts(tmp_path)
    plan = dna.build_plan(src, dst, dna.RENAMES)
    assert plan.renamed == ["gene_bs_head_round_shape"]
    assert "gene_bs_head_round_shape" not in plan.dropped and "gene_bs_head_shape" not in plan.defaulted
    assert place(dst, "gene_bs_head_shape", plan.apply(FACE)) == (1, 77, 0, 66)    # head_round_shape kept
    assert place(dst, "gene_keep", plan.apply(FACE)) == (0, 9, 0, 8)


def test_a_rename_never_applies_when_the_source_already_has_the_new_name(tmp_path):
    both = OLD.replace("gene_keep", "gene_bs_head_shape")
    src = dna.build_layout("old", [("vanilla", genes(tmp_path / "o", {"00_c.txt": COLOR, "01_m.txt": both}))])
    _, dst = layouts(tmp_path)
    plan = dna.build_plan(src, dst, dna.RENAMES)
    assert plan.renamed == []                          # the source's own gene_bs_head_shape wins; no double source


def test_a_rename_is_not_reported_when_the_target_lacks_the_new_name(tmp_path):
    src, dst = layouts(tmp_path)
    plan = dna.build_plan(src, dst, {"gene_bs_head_round_shape": "gene_not_in_target"})
    assert plan.renamed == [] and "gene_bs_head_round_shape" in plan.dropped


def test_the_face_changes_option_parses_known_names_and_refuses_others():
    import argparse
    import pytest
    from ck3_save_migrator import cli
    from ck3_save_migrator import record
    arg = lambda v: cli.face_changes_arg(argparse.Namespace(face_changes=v))  # noqa: E731
    assert arg(None) is None and arg("none") == [] and arg("") == [] and arg("renames") == ["renames"]
    assert arg("renames,merges,fallback") == ["renames", "merges", "fallback"]      # every switch R19 knows
    with pytest.raises(ValueError, match="not a known change"):
        arg("renames,colours")
    assert "face_changes" in record.INPUT_KEYS                 # a recorded run reproduces its face changes


def test_the_setup_applies_renames_only_when_the_switch_names_them(tmp_path):
    src, dst = layouts(tmp_path)
    off = dna.Setup(source=src, target=dst)
    on = dna.Setup(source=src, target=dst, face_changes=("renames",))
    assert off.plans()[0].renamed == [] and on.plans()[0].renamed == ["gene_bs_head_round_shape"]
    assert on.plans()[0].counts()["renamed"] == ["gene_bs_head_round_shape"]
