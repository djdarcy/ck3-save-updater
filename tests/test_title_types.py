"""carry_1_21.type_titles: the title types the game's 1.21 conversion leaves empty (S8).

The game writes type="" on titles a fresh 1.21 game types, and fails to read each back on load (djdarcy's re-save of
v17: 2,016 titles, one "Failed to read key reference" each). The rules come from the reference: a key pattern whose
titles all share one type, or a government whose titles all share one type other than the default.
"""
import pytest

from ck3_save_migrator import carry_1_21 as C


def title(i, key, typ, holder=None):
    h = f"\t\t\tholder={holder}\n" if holder else ""
    return f"\t\t{i}={{\n\t\t\ttype={typ}\tkey={key}\n{h}\t\t}}\n"


def char(i, gov):
    return f"\t{i}={{\n\t\tlanded_data={{\n\t\t\tgovernment={gov}\n\t\t}}\n\t}}\n"


def save(titles, chars=""):
    return (f"landed_titles={{\n\tlanded_titles={{\n{titles}\t}}\n}}\nliving={{\n{chars}}}\n").encode()


@pytest.fixture
def ref():
    t = "".join(title(i, f"c_nf_fam{i}", "title_type_noble_family") for i in range(12))
    t += "".join(title(100 + i, f"x_d_{i}", "title_type_mercenary_company", 900 + i) for i in range(12))
    t += "".join(title(200 + i, f"x_q_{i}", "title_type_default_static" if i % 2 else "title_type_nomad")
                 for i in range(12))                                           # a pattern with two types: no rule
    t += "".join(title(300 + i, f"d_few_{i}", "title_type_cardinal") for i in range(3))   # under the floor
    return save(t, "".join(char(900 + i, "mercenary_government") for i in range(12)))


def test_an_empty_type_is_filled_by_key_pattern_or_holder_government(ref):
    g = save(title(1, "c_nf_yamato", '""') + title(2, "x_mc_7", '""', 50) + title(3, "b_kept", "title_type_default_static"),
             char(50, "mercenary_government"))
    r = C.type_titles(g, ref)
    assert sorted(r.typed) == [("c_nf_yamato", "title_type_noble_family", "key pattern c_nf_"),
                               ("x_mc_7", "title_type_mercenary_company", "holder's government mercenary_government")]
    assert b"type=title_type_noble_family\tkey=c_nf_yamato" in r.gamestate
    assert b"type=title_type_default_static\tkey=b_kept" in r.gamestate          # a set type is never touched


def test_a_type_already_set_is_kept_even_where_a_rule_would_give_another(ref):
    g = save(title(1, "c_nf_odd", "title_type_default_static"))
    r = C.type_titles(g, ref)
    assert r.typed == [] and r.unknown == [] and r.gamestate == g


def test_only_a_deciding_rule_fills_a_type_and_only_an_empty_one():
    # a government whose reference titles are all the default decides nothing: typing by it would be a guess
    # ("reported, never guessed"); and a title with no type= line at all is not the conversion's empty mark
    # (mutation sweep v0.6.32 round 2: R2M9 dropped the default exclusion, R2M10 read a missing type as empty)
    ref = save("".join(title(400 + i, f"d_k{i}_x", "title_type_default_static", 950 + i) for i in range(12)),
               "".join(char(950 + i, "feudal_government") for i in range(12)))
    g = save(title(1, "c_plain", '""', 60) + "\t\t2={\n\t\t\tkey=c_old\n\t\t}\n", char(60, "feudal_government"))
    r = C.type_titles(g, ref)
    assert r.typed == [] and r.unknown == ["c_plain"] and r.gamestate == g


def test_what_no_rule_decides_stays_empty_and_is_reported(ref):
    g = save(title(1, "x_q_9", '""') + title(2, "d_few_9", '""') + title(3, "x_mc_8", '""'))   # x_mc_8: unheld
    r = C.type_titles(g, ref)
    assert not r.typed and r.gamestate == g
    assert sorted(r.unknown) == ["d_few_9", "x_mc_8", "x_q_9"]


def test_empty_key_cooldowns_are_dropped_and_named_ones_kept():
    g = (b"living={\n\t1={\n\t\tlanded_data={\n\t\t\tdecision_cooldowns={\n\t\t\t\t=978.3.5\n"
         b"\t\t\t\thold_court_decision=986.3.5\n\t\t\t\t=1000.9.11\n\t\t\t}\n\t\t}\n\t}\n}\n")
    out, n = C.drop_empty_cooldowns(g)
    assert n == 2
    assert out == (b"living={\n\t1={\n\t\tlanded_data={\n\t\t\tdecision_cooldowns={\n"
                   b"\t\t\t\thold_court_decision=986.3.5\n\t\t\t}\n\t\t}\n\t}\n}\n")
    assert C.drop_empty_cooldowns(out) == (out, 0)
    # an empty-key date outside decision_cooldowns is not this rule's business
    other = b"history={\n\t=867.1.1\n}\n"
    assert C.drop_empty_cooldowns(other) == (other, 0)


def prov(i, value, level):
    return f"\t{i}={{\n\t\tprovince_size_value={value}\n\t\tprovince_size_level={level}\n\t}}\n"


def test_a_province_size_is_raised_to_the_references_and_never_lowered():
    g = f"provinces={{\n{prov(28, 100, 1)}{prov(29, 500, 5)}{prov(30, 100, 1)}}}\n".encode()
    ref = f"provinces={{\n{prov(28, 300, 3)}{prov(29, 200, 2)}{prov(30, 100, 1)}}}\n".encode()
    out, raised = C.carry_province_size(g, ref)
    assert raised == [("28", 1, 3)]
    assert out == f"provinces={{\n{prov(28, 300, 3)}{prov(29, 500, 5)}{prov(30, 100, 1)}}}\n".encode()
    assert C.carry_province_size(out, ref) == (out, [])


def test_a_second_run_changes_nothing(ref):
    once = C.type_titles(save(title(1, "c_nf_yamato", '""')), ref).gamestate
    assert C.type_titles(once, ref).gamestate == once
