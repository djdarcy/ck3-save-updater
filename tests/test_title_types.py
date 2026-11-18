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


def test_a_second_run_changes_nothing(ref):
    once = C.type_titles(save(title(1, "c_nf_yamato", '""')), ref).gamestate
    assert C.type_titles(once, ref).gamestate == once
