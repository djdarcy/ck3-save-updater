"""savediff's reference graph (ck3_save_migrator/_vendor/savediff/graph.py), case by case.

The cases reproduce three defects found in a migrated save: a ruler whose primary title was a barony beside its
county (the game later made the county its own de facto liege and froze climbing the liege chain); mercenary
company titles keyed ``x_mc_1821...`` where the game keys them ``x_mc_<company id>``, and a company left pointing
at a destroyed title; and two saves of one company compared link by link through translated ids.
"""

from __future__ import annotations

from ck3_save_migrator._vendor.savediff import graph as G
from ck3_save_migrator._vendor.savediff import text as T

NONE = 4294967295


# --------------------------------------------------------------------------- building gamestates
def entry(i: int, *lines: str) -> str:
    return f"{i}={{\n" + "".join(f"\t{ln}\n" for ln in lines) + "}\n"


def save(*, chars: str = "", titles: str = "", companies: str = "", regiments: str = "", extra: str = "") -> bytes:
    return (f"living={{\n{chars}}}\n"
            f"landed_titles={{\n\tlanded_titles={{\n{titles}\t}}\n\tindex=99\n}}\n"
            f"mercenary_company_manager={{\n\tmercenary_companies={{\n{companies}\t}}\n}}\n"
            f"armies={{\n\tregiments={{\n{regiments}\t}}\n}}\n" + extra).encode()


def ruler(i: int, *domain: int, extra: str = "") -> str:
    return entry(i, 'first_name="R"', "landed_data={", f"\tdomain={{ {' '.join(map(str, domain))} }}", "}", extra)


def title(i: int, key: str, *lines: str) -> str:
    return entry(i, f"key={key}", *lines)


# --------------------------------------------------------------------------- the builder
def test_build_reads_nodes_keys_and_edges_by_the_schema():
    g = save(chars=ruler(1, 10), titles=title(10, '"c_a"', "holder=1", f"de_jure_liege={NONE}"),
             companies=entry(5, "title=10", "regiments={ 30 }", "size=3"), regiments=entry(30, "owner=1"))
    gr = G.build(g)
    assert set(gr.nodes) == {("character", 1), ("title", 10), ("mercenary", 5), ("regiment", 30)}
    assert gr.keys[("title", 10)] == "c_a"
    got = {(e.src, e.path, e.dst) for e in gr.edges}
    assert got == {(("character", 1), "landed_data/domain/*", ("title", 10)),
                   (("title", 10), "holder", ("character", 1)),
                   (("title", 10), "de_jure_liege", ("title", NONE)),
                   (("mercenary", 5), "title", ("title", 10)),
                   (("mercenary", 5), "regiments/*", ("regiment", 30)),
                   (("regiment", 30), "owner", ("character", 1))}


def test_build_follows_typed_identities_and_numeric_keys_that_are_ids():
    g = save(chars=entry(1), titles=title(10, "c_a", "var={", "\ttype=char", "\tidentity=1", "}",
                                          "num={", "\ttype=value", "\tidentity=77", "}"),
             extra="culture_manager={\n\tcultures={\n" + entry(3, "acceptance={", "\t4=50", "}") + entry(4)
             + "\t}\n}\n")
    gr = G.build(g)
    assert G.Edge(("culture", 3), "acceptance/#key", ("culture", 4)) in gr.edges
    assert not any(e.path.endswith("acceptance/#") for e in gr.edges)          # the 50 is a value, not an id
    assert G.Edge(("title", 10), "var/identity", ("character", 1)) in gr.edges
    assert not any(e.path == "num/identity" for e in gr.edges)                 # type=value carries a number


def test_build_limited_to_some_spaces_leaves_the_other_edges_unjudged():
    g = save(chars=ruler(1, 10), titles=title(10, "c_a", "holder=1"))
    gr = G.build(g, spaces=["title"])
    d = G.dangling(gr)
    assert d["rows"] == [] and d["counted"]["not_judged"] == 1 and set(gr.nodes) == {("title", 10)}


# --------------------------------------------------------------------------- primary_outranked
def test_a_barony_first_domain_beside_its_county_is_flagged():
    g = save(chars=ruler(1, 10, 11) + ruler(2, 12, 13),
             titles=title(10, "b_cashel", "holder=1") + title(11, "c_cashel", "holder=1")
             + title(12, "d_munster", "holder=2") + title(13, "c_cork", "holder=2"))
    out = G.primary_outranked(G.build(g))
    assert out["rows"] == [{"character": 1, "primary": (10, "b_cashel", 1), "outranked_by": [(11, "c_cashel", 2)]}]
    assert out["counted"] == {"rulers": 2, "not_judged": 0, "outranked": 1}


def test_a_primary_title_of_equal_or_higher_tier_is_not_flagged():
    g = save(chars=ruler(1, 10, 11) + ruler(2, 12, 13, 14),
             titles=title(10, "c_a", "holder=1") + title(11, "c_b", "holder=1")
             + title(12, "d_a", "holder=2") + title(13, "c_c", "holder=2") + title(14, "b_c", "holder=2"))
    out = G.primary_outranked(G.build(g))
    assert out["rows"] == [] and out["counted"] == {"rulers": 2, "not_judged": 0, "outranked": 0}


def test_a_primary_title_without_a_tier_letter_is_not_judged():
    g = save(chars=ruler(1, 10, 11), titles=title(10, "x_x_762") + title(11, "k_ireland"))
    out = G.primary_outranked(G.build(g))
    assert out["rows"] == [] and out["counted"] == {"rulers": 1, "not_judged": 1, "outranked": 0}


def test_a_hegemony_outranks_an_empire():
    g = save(chars=ruler(1, 10, 11), titles=title(10, "e_india") + title(11, "h_india"))
    assert G.primary_outranked(G.build(g))["rows"][0]["outranked_by"] == [(11, "h_india", 6)]


# --------------------------------------------------------------------------- cycles
def test_a_title_that_is_its_own_de_facto_liege_is_a_cycle():
    g = save(titles=title(11, "c_a", "de_facto_liege=11") + title(12, "d_a"))
    out = G.cycles(G.build(g), "de_facto_liege")
    assert out["rows"] == [{"cycle": [11], "keys": ["c_a"]}]
    assert out["counted"] == {"entities": 2, "with_parent": 1, "cycles": 1}


def test_a_two_title_cycle_is_found_once_and_a_tail_into_it_is_not_a_cycle():
    # the tail's ids are smaller than the cycle's, so the walk starts on the tail and must not report it
    g = save(titles=title(20, "k_a", "de_jure_liege=21") + title(21, "e_a", "de_jure_liege=20")
             + title(2, "d_a", "de_jure_liege=20") + title(3, "c_a", "de_jure_liege=2"))
    out = G.cycles(G.build(g), "de_jure_liege")
    assert out["rows"] == [{"cycle": [20, 21], "keys": ["k_a", "e_a"]}]
    assert G.cycles(G.build(g), "de_facto_liege")["rows"] == []


def test_a_self_liege_and_a_two_title_cycle_in_one_graph_are_both_found():
    g = save(titles=title(11, "c_a", "de_facto_liege=11") + title(20, "k_a", "de_facto_liege=21")
             + title(21, "e_a", "de_facto_liege=20") + title(30, "d_b", "de_facto_liege=20"))
    out = G.cycles(G.build(g), "de_facto_liege")
    assert out["rows"] == [{"cycle": [11], "keys": ["c_a"]}, {"cycle": [20, 21], "keys": ["k_a", "e_a"]}]
    assert out["counted"] == {"entities": 4, "with_parent": 4, "cycles": 2}


def test_a_liege_chain_without_a_loop_has_no_cycle():
    g = save(titles=title(1, "b_a", "de_jure_liege=2") + title(2, "c_a", "de_jure_liege=3") + title(3, "d_a"))
    out = G.cycles(G.build(g), "de_jure_liege")
    assert out["rows"] == [] and out["counted"]["with_parent"] == 2


# --------------------------------------------------------------------------- dangling and key_rule
def test_a_company_whose_title_does_not_exist_is_dangling_and_none_is_legal():
    g = save(titles=title(10, "x_mc_5"), companies=entry(5, "title=10") + entry(6, "title=99")
             + entry(7, f"title={NONE}"))
    out = G.dangling(G.build(g))
    assert out["rows"] == [{"from": ("mercenary", 6), "section": "mercenary_company_manager/mercenary_companies",
                            "field": "title", "to": ("title", 99)}]
    assert out["counted"]["none"] == 1 and out["counted"]["judged"] == 2


def test_a_company_title_must_be_keyed_x_mc_and_its_own_id():
    g = save(titles=title(10, "x_mc_1821") + title(11, "x_mc_6") + title(12, "x_mc_77"),
             companies=entry(5, "title=10") + entry(6, "title=11") + entry(7, "title=99") + entry(8, "size=1")
             + entry(77, "title=12"))
    out = G.key_rule(G.build(g), **G.MERCENARY_TITLE_KEY)
    assert out["rows"] == [
        {"entity": 5, "target": 10, "key": "x_mc_1821", "expected": "x_mc_5", "why": "key differs"},
        {"entity": 7, "target": 99, "key": None, "expected": "x_mc_7", "why": "title 99 does not exist"},
        {"entity": 8, "target": None, "key": None, "expected": "x_mc_8", "why": "no title"}]
    assert out["counted"] == {"entities": 5, "broken": 3}


def test_a_company_title_key_that_only_starts_with_the_expected_key_is_broken():
    g = save(titles=title(10, "x_mc_77"), companies=entry(7, "title=10"))
    out = G.key_rule(G.build(g), **G.MERCENARY_TITLE_KEY)
    assert [(r["entity"], r["key"], r["why"]) for r in out["rows"]] == [(7, "x_mc_77", "key differs")]


def test_key_rule_on_the_entity_itself():
    g = save(titles=title(1, "c_a") + title(2, "x_x_2") + entry(3, "holder=1"))
    out = G.key_rule(G.build(g), "title", r"[bcdkeh]_.+")
    assert [(r["entity"], r["why"]) for r in out["rows"]] == [(2, "key differs"), (3, "no key")]


# --------------------------------------------------------------------------- duplicates
def test_an_id_written_twice_in_one_space_and_a_title_key_written_twice():
    g = save(chars=entry(1) + entry(2) + entry(1),
             titles=title(10, "c_a") + title(11, '"c_a"') + title(12, "c_b"),
             extra="dead_unprunable={\n" + entry(2) + "}\n")
    out = G.duplicates(g)
    assert {"what": "id", "space": "character", "id": 1, "sections": ["living", "living"]} in out["rows"]
    assert {"what": "id", "space": "character", "id": 2, "sections": ["living", "dead_unprunable"]} in out["rows"]
    assert {"what": "key", "space": "title", "value": "c_a", "ids": [10, 11]} in out["rows"]
    assert len(out["rows"]) == 3 and out["counted"]["character"] == 4 and out["counted"]["title key"] == 3


def test_a_repeated_id_keeps_its_first_entry_in_the_graph():
    gr = G.build(save(chars=entry(1, 'first_name="A"') + entry(1, 'first_name="B"')))
    assert gr.repeated == [(("character", 1), "living")]
    assert G.record(gr, ("character", 1))["first_name"]["values"] == ["A"]


# --------------------------------------------------------------------------- the survival rule
def test_every_check_says_what_it_counted_even_on_an_empty_save():
    gr = G.build(save())
    for out in (G.dangling(gr), G.cycles(gr, "de_jure_liege"), G.duplicates(gr.g), G.primary_outranked(gr),
                G.key_rule(gr, **G.MERCENARY_TITLE_KEY)):
        assert out["rows"] == [] and out["counted"] and all(isinstance(v, int) for v in out["counted"].values())


# --------------------------------------------------------------------------- join and join_diff
def company_save(off_c: int = 0, off_t: int = 0, off_r: int = 0, size: int = 100, size0: int = 50) -> bytes:
    c, t, r = 1 + off_c, (20 + off_t, 21 + off_t), (30 + off_r, 31 + off_r)
    return save(chars=ruler(c, t[0], t[1]),
                titles=title(t[0], "x_mc_5", f"holder={c}") + title(t[1], "c_home", f"holder={c}"),
                companies=entry(5, f"title={t[0]}", f"county={t[1]}", f"regiments={{ {r[0]} {r[1]} }}"),
                regiments=entry(r[0], f"owner={c}", f"size={size0}") + entry(r[1], f"owner={c}", f"size={size}"))


def test_join_takes_what_is_reachable_within_depth():
    gr = G.build(company_save())
    j1 = G.join(gr, "mercenary", 5, 1)
    assert set(j1["nodes"]) == {("mercenary", 5), ("title", 20), ("title", 21), ("regiment", 30), ("regiment", 31)}
    j2 = G.join(gr, "mercenary", 5, 2)
    assert ("character", 1) in j2["nodes"] and j2["nodes"][("character", 1)]["depth"] == 2
    assert j2["nodes"][("regiment", 31)]["record"]["size"] == {"space": None, "values": ["100"]}
    assert j2["nodes"][("mercenary", 5)]["record"]["regiments/*"] == {"space": "regiment", "values": ["30", "31"]}


def test_join_keeps_a_missing_target_as_a_node_without_a_record():
    gr = G.build(save(companies=entry(5, "title=99")))
    j = G.join(gr, "mercenary", 5, 3)
    assert j["nodes"][("title", 99)] == {"depth": 1, "section": None, "record": None}


def test_join_does_not_follow_the_none_id():
    gr = G.build(save(companies=entry(5, f"county={NONE}", "size=2")))
    j = G.join(gr, "mercenary", 5, 2)
    assert list(j["nodes"]) == [("mercenary", 5)] and j["edges"] == []
    assert j["nodes"][("mercenary", 5)]["record"]["county"] == {"space": "title", "values": [str(NONE)]}


def test_join_diff_against_a_translated_twin_names_the_one_field_that_differs():
    a = G.join(G.build(company_save()), "mercenary", 5, 3)
    b = G.join(G.build(company_save(500, 1000, 100, size=90)), "mercenary", 5, 3)
    tr = G.offset_translator({"character": 500, "title": 1000, "regiment": 100})
    out = G.join_diff(a, b, tr)
    assert out["rows"] == [{"kind": "regiment", "a": 31, "b": 131, "field": "size", "how": "differs",
                            "value_a": ["100"], "value_b": ["90"]}]
    assert out["counted"]["paired"] == len(a["nodes"]) == len(b["nodes"]) == 6


def test_join_diff_of_identical_twins_is_empty_but_counted():
    a = G.join(G.build(company_save()), "mercenary", 5, 3)
    b = G.join(G.build(company_save(500, 1000, 100)), "mercenary", 5, 3)
    out = G.join_diff(a, b, G.offset_translator({"character": 500, "title": 1000, "regiment": 100}))
    assert out["rows"] == [] and out["counted"]["fields_compared"] > 10


def test_join_diff_without_the_translation_sees_every_link_differ():
    a = G.join(G.build(company_save()), "mercenary", 5, 1)
    b = G.join(G.build(company_save(500, 1000, 100)), "mercenary", 5, 1)
    out = G.join_diff(a, b, G.offset_translator({}))
    hows = {(r["kind"], r["field"], r["how"]) for r in out["rows"]}
    assert ("mercenary", "title", "differs") in hows and ("title", None, "node only in A") in hows
    assert ("title", None, "node only in B") in hows


def test_join_diff_sees_a_reordered_domain_because_the_first_title_is_the_primary():
    a = G.join(G.build(save(chars=ruler(1, 20, 21), titles=title(20, "c_a") + title(21, "b_a"))), "character", 1, 1)
    b = G.join(G.build(save(chars=ruler(1, 1021, 1020), titles=title(1020, "c_a") + title(1021, "b_a"))),
               "character", 1, 1)
    out = G.join_diff(a, b, G.offset_translator({"title": 1000}))
    assert [(r["kind"], r["field"], r["how"], r["value_a"], r["value_b"]) for r in out["rows"]] == [
        ("character", "landed_data/domain/*", "differs", ["1020", "1021"], ["1021", "1020"])]


def test_the_none_id_translates_to_itself_so_two_none_links_agree():
    tr = G.offset_translator({"title": 1000})
    assert tr("title", NONE) == NONE and tr("title", 5) == 1005 and tr("character", 5) == 5
    a = G.join(G.build(save(companies=entry(5, f"county={NONE}"))), "mercenary", 5, 1)
    b = G.join(G.build(save(companies=entry(5, f"county={NONE}"))), "mercenary", 5, 1)
    assert G.join_diff(a, b, tr)["rows"] == []


def test_join_diff_reports_fields_only_on_one_side():
    a = G.join(G.build(save(companies=entry(5, "size=1", "flag=yes"))), "mercenary", 5, 1)
    b = G.join(G.build(save(companies=entry(5, "size=1", "culture_name=x"))), "mercenary", 5, 1)
    out = G.join_diff(a, b, G.offset_translator({}))
    assert [(r["field"], r["how"]) for r in out["rows"]] == [("culture_name", "only in B"), ("flag", "only in A")]


def test_aggregate_makes_a_difference_every_pair_shares_stand_out():
    tr = G.offset_translator({"character": 500, "title": 1000, "regiment": 100})
    diffs = []
    for size in (90, 80, 100):
        a = G.join(G.build(company_save()), "mercenary", 5, 3)
        b = G.join(G.build(company_save(500, 1000, 100, size=size)), "mercenary", 5, 3)
        diffs.append(G.join_diff(a, b, tr))
    agg = G.aggregate(diffs)
    assert agg["counted"] == {"diffs": 3, "groups": 1}
    (top,) = agg["rows"]
    assert (top["kind"], top["field"], top["how"], top["rows"], top["pairs"]) == ("regiment", "size", "differs", 2, 2)
    assert len(top["examples"]) == 2


def test_aggregate_counts_pairs_apart_from_rows():
    tr = G.offset_translator({"character": 500, "title": 1000, "regiment": 100})
    a = G.join(G.build(company_save()), "mercenary", 5, 3)
    both = G.join(G.build(company_save(500, 1000, 100, size=90, size0=40)), "mercenary", 5, 3)   # two rows
    one = G.join(G.build(company_save(500, 1000, 100, size=90)), "mercenary", 5, 3)              # one row
    (top,) = G.aggregate([G.join_diff(a, both, tr), G.join_diff(a, one, tr)])["rows"]
    assert (top["field"], top["rows"], top["pairs"]) == ("size", 3, 2)


def test_the_text_index_can_be_shared():
    g = company_save()
    idx = T.SectionIndex(g)
    assert set(G.build(g, idx).nodes) == set(G.build(g).nodes)
