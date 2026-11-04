"""R19's template fallback (#40 S4, the safety net): with --face-changes fallback, a source template the target gene
no longer names goes to the closest-named target template instead of index 0, and never lands on a "no_" template
(one that draws nothing) unless it was one itself. Without the switch, 0.4.0's behaviour: index 0.

Synthetic layouts only; nothing reads a real install or save.
"""
from __future__ import annotations

from ck3_save_migrator import dna
from tests.test_dna import COLOR, genes

OLD = ("morph_genes = {\n\tgene_beard = {\n\t\tno_beard = { index = 0 }\n\t\tbeard_full_old = { index = 1 }\n"
       "\t\tbeard_goatee = { index = 2 }\n\t\tbraids_xyz = { index = 3 }\n\t}\n"
       "\tgene_plain = {\n\t\tplain_a = { index = 0 }\n\t\tqqq_gone = { index = 1 }\n\t}\n}\n")
NEW = ("morph_genes = {\n\tgene_beard = {\n\t\tno_beard = { index = 0 }\n\t\tbeard_goatee = { index = 1 }\n"
       "\t\tbeard_full = { index = 2 }\n\t\tbeard_stubble = { index = 3 }\n\t}\n"
       "\tgene_plain = {\n\t\tplain_a = { index = 0 }\n\t\tplain_b = { index = 1 }\n\t}\n}\n")


def layouts(tmp_path):
    src = dna.build_layout("old", [("vanilla", genes(tmp_path / "o", {"00_c.txt": COLOR, "01_m.txt": OLD}))])
    dst = dna.build_layout("new", [("vanilla", genes(tmp_path / "n", {"00_c.txt": COLOR, "01_m.txt": NEW}))])
    return src, dst


def at(dst, name, out):
    p = [g["name"] for g in dst.genes].index(name)
    return tuple(out[p * 4: p * 4 + 4])


def face(beard, plain):
    return bytes([10, 20, 30, 40, 1, 2, 3, 4, *beard, *plain])


def test_with_fallback_a_lost_template_never_lands_on_a_no_template(tmp_path):
    """CONSEQUENCE: 6 (behaviour) -- a feature a mod renamed away is never erased to "draws nothing"."""
    src, dst = layouts(tmp_path)
    plan = dna.build_plan(src, dst, fallback=True)
    # braids_xyz has no close name; index 0 is no_beard, so the lowest-index drawing template, beard_goatee (1)
    assert ("gene_beard", "braids_xyz", "beard_goatee") in plan.fell_back
    assert at(dst, "gene_beard", plan.apply(face((3, 99, 0, 77), (0, 0, 0, 0)))) == (1, 99, 0, 77)


def test_with_fallback_a_lost_template_goes_to_the_closest_name(tmp_path):
    """CONSEQUENCE: 5 (behaviour) -- a renamed template keeps its look under the closest new name."""
    src, dst = layouts(tmp_path)
    plan = dna.build_plan(src, dst, fallback=True)
    assert ("gene_beard", "beard_full_old", "beard_full") in plan.fell_back
    # beard_full_old (1) -> beard_full (2); the kept name beard_goatee (2) -> (1) as before
    assert at(dst, "gene_beard", plan.apply(face((1, 99, 2, 77), (0, 0, 0, 0)))) == (2, 99, 1, 77)


def test_the_setup_applies_fallback_only_when_the_switch_names_it(tmp_path):
    """CONSEQUENCE: 5 (behaviour) -- fallback stays opt-in; 0.4.0's faces are the default."""
    src, dst = layouts(tmp_path)
    assert dna.Setup(src, dst).plans()[0].fell_back == []
    assert dna.Setup(src, dst, face_changes=("fallback",)).plans()[0].fell_back != []


def test_with_fallback_index_0_stays_where_it_draws_something(tmp_path):
    """CONSEQUENCE: 4 (behaviour) -- with no close name and a drawing index 0, the switch changes nothing."""
    src, dst = layouts(tmp_path)
    plan = dna.build_plan(src, dst, fallback=True)
    # qqq_gone: no close name, and plain_a (index 0) is not a "no_" template, so 0.4.0's index 0 stays
    assert not any(g == "gene_plain" for g, _, _ in plan.fell_back)
    assert at(dst, "gene_plain", plan.apply(face((0, 0, 0, 0), (1, 50, 1, 60)))) == (0, 50, 0, 60)


def test_closest_template_keeps_a_no_template_for_a_no_template():
    """CONSEQUENCE: 4 (behaviour) -- a face that had no beard keeps no beard."""
    assert dna.closest_template("no_beard_old", {"no_beard": 0, "beard_full": 1}) == "no_beard"


def test_without_fallback_a_lost_template_goes_to_index_0(tmp_path):
    """CONSEQUENCE: 4 (behaviour) -- without the switch the plan is 0.4.0's: a lost template goes to index 0."""
    src, dst = layouts(tmp_path)
    plan = dna.build_plan(src, dst)
    assert plan.fell_back == []
    assert at(dst, "gene_beard", plan.apply(face((1, 99, 3, 77), (1, 50, 0, 50)))) == (0, 99, 0, 77)
