"""savediff's key layer and id arithmetic (ck3_save_migrator/_vendor/savediff: keys.py, ids.py), case by case."""

from __future__ import annotations

from ck3_save_migrator._vendor.savediff import ids as IDS
from ck3_save_migrator._vendor.savediff import keys as K
from ck3_save_migrator._vendor.savediff import text as T

TITLES = "landed_titles/landed_titles"


def titles(*entries: str) -> bytes:
    return ("landed_titles={\n\tlanded_titles={\n" + "".join(entries) + "\t}\n\tindex=9\n}\n").encode()


def run(g: bytes, fn, *args):
    return fn(g, T.SectionIndex(g), *args)


# --------------------------------------------------------------------------- field_keys
def test_field_keys_reads_key_at_the_entrys_own_depth_after_a_nested_key():
    g = titles("0={\n\thistory={\n\t\tkey=x\n\t}\n\tkey=b_real\n}\n")
    assert run(g, K.field_keys, TITLES) == {0: "b_real"}


def test_field_keys_reads_key_at_the_entrys_own_depth_before_a_nested_key():
    g = titles("0={\n\tkey=b_real\n\thistory={\n\t\tkey=x\n\t}\n}\n")
    assert run(g, K.field_keys, TITLES) == {0: "b_real"}


def test_field_keys_leaves_out_an_entry_with_no_key_at_its_own_depth():
    g = titles("0={\n\thistory={\n\t\tkey=x\n\t}\n}\n", "1={\n\tkey=c_y\n}\n", "2={\n}\n")
    assert run(g, K.field_keys, TITLES) == {1: "c_y"}


def test_field_keys_quoted_and_bare_values_are_the_same():
    g = titles("0={\n\tkey=\"b_foo\"\n}\n", "1={\n\tkey=b_foo\n}\n")
    assert run(g, K.field_keys, TITLES) == {0: "b_foo", 1: "b_foo"}


def test_field_keys_reads_another_field_and_skips_freed_slots_and_named_children():
    g = titles("0={\n\tkey=a\n\tholder=7\n}\n", "3=none\n", "\tsub={\n\t\tholder=9\n\t}\n")
    assert run(g, K.field_keys, TITLES, b"holder") == {0: "7"}


def test_field_keys_of_an_absent_path_is_empty():
    assert run(titles(), K.field_keys, "nope/nothing") == {}


def test_field_keys_braces_in_strings_do_not_hide_the_key():
    g = titles("0={\n\tname=\"a { b\"\n\tkey=k_x\n}\n")
    assert run(g, K.field_keys, TITLES) == {0: "k_x"}


# --------------------------------------------------------------------------- entry_keys, union_keys, scalar_map
def test_entry_keys_are_the_numeric_blocks_only():
    g = b"living={\n1={\n}\n2={\n}\n12=none\n\tsub={\n\t}\n}\n"
    assert run(g, K.entry_keys, "living") == {1, 2}
    assert run(g, K.entry_keys, "dead") == set()


def test_union_keys_joins_the_character_sections():
    g = (b"living={\n1={\n}\n}\ndead_unprunable={\n2={\n}\n}\n"
         b"characters={\n\tdead_prunable={\n3={\n}\n\t}\n}\n")
    assert run(g, K.union_keys, ("living", "dead_unprunable", "characters/dead_prunable", "absent")) == {1, 2, 3}


def test_scalar_map_keeps_non_numeric_history_ids_whole():
    g = b"character_lookup={\nhan_1176=5\n188854bis=7\n12=3\n\t901=4\n}\n"
    assert run(g, K.scalar_map, "character_lookup") == {"han_1176": 5, "188854bis": 7, "12": 3, "901": 4}


def test_scalar_map_of_an_absent_section_is_empty():
    assert run(b"living={\n}\n", K.scalar_map, "character_lookup") == {}


# --------------------------------------------------------------------------- key_gaps
def test_key_gaps_splits_the_keys_want_holds_and_have_lacks():
    sets = {"ref": {1, 2, 3, 4, 5, 6, 7, 8, 9}, "ours": {1, 2}, "chain": {1}}
    out = K.key_gaps(sets, have="ours", want="ref", split={3, 4, 99})
    assert out["totals"] == {"ref": 9, "ours": 2, "chain": 1} and out["lacking"] == 7
    assert out["in_split"] == {"count": 2, "examples": [3, 4]}
    assert out["rest"] == {"count": 5, "examples": [5, 6, 7, 8, 9]}


def test_key_gaps_examples_are_the_first_six_sorted():
    out = K.key_gaps({"a": set(), "b": set(range(20, 0, -1))}, have="a", want="b")
    assert out["rest"]["examples"] == [1, 2, 3, 4, 5, 6] and out["rest"]["count"] == 20
    assert out["in_split"] == {"count": 0, "examples": []}


# --------------------------------------------------------------------------- field_coverage / coverage_gaps
FAITHS = "religion/faiths"


def faiths(*entries: str) -> bytes:
    return ("religion={\n\tfaiths={\n" + "".join(entries) + "\t}\n}\n").encode()


def test_field_coverage_counts_a_second_key_written_on_the_same_line():
    # the game writes "faith_type=x\t\t\treligion=0" on one line; a reader by line start sees only the first
    g = faiths("0={\n\t\t\tfaith_type=a\t\t\treligion=0\n}\n", "1={\n\t\t\tfaith_type=b\t\t\treligion=0\n}\n")
    f = run(g, K.field_coverage, FAITHS)["fields"]
    assert f["religion"]["present"] == 2 and f["faith_type"]["present"] == 2


def test_field_coverage_an_empty_string_or_block_is_empty_not_missing():
    # F25's shape: the game's own re-save wrote faith_type="" for the faith the update left without one
    g = faiths('0={\n\tfaith_type=""\n\tholy_sites={ }\n}\n', "1={\n\tfaith_type=x\n\tholy_sites={ 3 }\n}\n")
    out = run(g, K.field_coverage, FAITHS)
    assert out["fields"]["faith_type"] == {"present": 2, "empty": 1, "missing_examples": [], "empty_examples": ["0"]}
    assert out["fields"]["holy_sites"]["empty"] == 1


def test_field_coverage_a_field_written_twice_is_empty_only_when_every_writing_is():
    g = faiths('0={\n\tdoctrine=""\n\tdoctrine="tenet_x"\n}\n', '1={\n\tdoctrine=""\n}\n')
    d = run(g, K.field_coverage, FAITHS)["fields"]["doctrine"]
    assert (d["present"], d["empty"], d["empty_examples"]) == (2, 1, ["1"])


def test_field_coverage_reads_depth_one_only_and_names_missing_entries():
    g = faiths("0={\n\tname=a\n\tchanges={\n\t\ttag=x\n\t}\n}\n", "1={\n\ttag=y\n}\n", "2={\n\tname=c\n}\n")
    out = run(g, K.field_coverage, FAITHS)
    assert out["entries"] == 3 and out["fields"]["tag"]["present"] == 1
    assert out["fields"]["tag"]["missing_examples"] == ["0", "2"]
    assert out["fields"]["name"]["missing_examples"] == ["1"]


def test_field_coverage_counts_unkeyed_entries_by_position_and_skips_freed_slots():
    g = b"opinions={\n\tactive_opinions={\n\t\t{\n\t\t\towner=1\n\t\t}\n\t\t{\n\t\t\ttarget=2\n\t\t}\n\t}\n}\n"
    out = run(g, K.field_coverage, "opinions/active_opinions")
    assert out["entries"] == 2 and out["fields"]["owner"]["missing_examples"] == ["#1"]
    g2 = faiths("0={\n\tname=a\n}\n", "1=none\n")
    assert run(g2, K.field_coverage, FAITHS)["entries"] == 1


def test_field_coverage_of_an_absent_path_has_no_entries():
    out = run(b"living={\n}\n", K.field_coverage, FAITHS)
    assert out["entries"] == 0 and out["fields"] == {}


def test_coverage_gaps_finds_a_field_the_witness_carries_and_most_of_ours_lack():
    # the majority gap a sibling comparison cannot see: contract_group on few of ours, on all of the reference's
    ours = faiths("0={\n\tname=a\n\tgroup=g\n}\n", "1={\n\tname=b\n}\n", "2={\n\tname=c\n}\n")
    ref = faiths("0={\n\tname=a\n\tgroup=g\n}\n", "1={\n\tname=b\n\tgroup=h\n}\n")
    rows = K.coverage_gaps(run(ours, K.field_coverage, FAITHS), run(ref, K.field_coverage, FAITHS))
    assert [(r["field"], r["missing"], r["missing_examples"]) for r in rows] == [("group", 2, ["1", "2"])]
    assert K.coverage_gaps(run(ours, K.field_coverage, FAITHS), run(ours, K.field_coverage, FAITHS)) == []


def test_coverage_gaps_reports_an_empty_field_and_a_field_absent_from_all_of_ours():
    ours = faiths('0={\n\tfaith_type=""\n}\n', "1={\n\tfaith_type=x\n}\n")
    ref = faiths("0={\n\tfaith_type=x\n\teminent_holy_sites={ 1 }\n}\n")
    rows = {r["field"]: r for r in K.coverage_gaps(run(ours, K.field_coverage, FAITHS),
                                                    run(ref, K.field_coverage, FAITHS))}
    assert (rows["faith_type"]["missing"], rows["faith_type"]["empty"], rows["faith_type"]["empty_examples"]) == (0, 1, ["0"])
    assert (rows["eminent_holy_sites"]["missing"], rows["eminent_holy_sites"]["missing_examples"]) == (2, ["0", "1"])


def test_coverage_gaps_ignores_a_field_below_the_threshold_and_an_empty_side():
    # rite_type on 150/152 reference rites, absent on the two made in play: under 0.99 it is no gap
    ref = faiths(*(f"{i}={{\n\trite_type=r\n}}\n" for i in range(98)), "98={\n\tname=x\n}\n", "99={\n\tname=y\n}\n")
    ours = faiths("0={\n\tname=z\n}\n")
    cov = lambda g: run(g, K.field_coverage, FAITHS)
    assert K.coverage_gaps(cov(ours), cov(ref), threshold=0.99) == []
    assert [r["field"] for r in K.coverage_gaps(cov(ours), cov(ref), threshold=0.9)] == ["rite_type"]
    assert K.coverage_gaps(cov(b"religion={\n}\n"), cov(ref)) == []      # nothing to compare with
    assert K.coverage_gaps(cov(ours), cov(b"religion={\n}\n")) == []


def test_database_paths_finds_sections_and_their_children_with_enough_entries():
    g = (b"living={\n" + b"".join(b"%d={\n\tx=1\n}\n" % i for i in range(3)) + b"}\n"
         + faiths(*(f"{i}={{\n\tname=a\n}}\n" for i in range(3))) + b"small={\n0={\n}\n}\n")
    assert K.database_paths(g, T.SectionIndex(g), min_entries=3) == ["living", "religion/faiths"]


# --------------------------------------------------------------------------- ids
def test_slot_generation_make():
    i = 0x03ABCDEF
    assert (IDS.slot(i), IDS.generation(i)) == (0xABCDEF, 3) and IDS.make(0xABCDEF, 3) == i
    assert IDS.NONE == 0xFFFFFFFF and IDS.LOW == 0xFFFFFF and IDS.GEN == 0xFF000000


def test_translate_shifts_the_slot_and_keeps_the_generation():
    assert IDS.translate(IDS.make(5, 2), 1000) == IDS.make(1005, 2)
    assert IDS.translate(IDS.make(1005, 2), -1000) == IDS.make(5, 2)


def test_offset_by_mode_with_nothing_shared_is_none():
    assert IDS.offset_by_mode({"a": 1}, {"b": 2}) == (None, set())
    assert IDS.offset_by_mode({}, {}) == (None, set())


def test_offset_by_mode_ignores_keys_whose_generations_differ():
    # +10 twice at one generation; +1 three times, but each across two generations (a freed slot reused):
    # counted, the +1s would win
    a = {"x": IDS.make(1, 0), "y": IDS.make(2, 0), "z": IDS.make(3, 1), "w": IDS.make(9, 2), "u": IDS.make(30, 0)}
    b = {"x": IDS.make(11, 0), "y": IDS.make(12, 0), "z": IDS.make(4, 0), "w": IDS.make(10, 0), "u": IDS.make(31, 3)}
    assert IDS.offset_by_mode(a, b) == (10, {"x", "y"})
    assert IDS.offset_by_mode({"z": IDS.make(3, 1)}, {"z": IDS.make(4, 0)}) == (None, set())


def test_offset_by_mode_takes_the_most_common_offset_not_the_largest():
    a = {k: IDS.make(i, 0) for i, k in enumerate("abcdef")}
    b = {"a": IDS.make(100, 0), "b": IDS.make(101, 0), "c": IDS.make(102, 0), "d": IDS.make(5003, 0), "e": IDS.make(4, 0)}
    assert IDS.offset_by_mode(a, b) == (100, {"a", "b", "c"})


def test_offset_by_mode_breaks_a_tie_with_the_smallest_offset():
    a = {"a": IDS.make(10, 0), "b": IDS.make(20, 0), "c": IDS.make(30, 0), "d": IDS.make(40, 0)}
    b = {"b": IDS.make(25, 0), "a": IDS.make(17, 0), "d": IDS.make(45, 0), "c": IDS.make(37, 0)}   # +7 twice, +5 twice
    assert IDS.offset_by_mode(a, b) == (5, {"b", "d"})
    assert IDS.offset_by_mode(dict(reversed(a.items())), dict(reversed(b.items()))) == (5, {"b", "d"})
