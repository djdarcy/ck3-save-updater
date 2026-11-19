"""carry_1_21.carry_baronies: give back the baronies the game's 1.21 conversion moved to a new county's holder.

A synthetic 1.21-shaped re-save, its 1.20 witness and a synthetic 1.21 title tree. Each case is a lesson the real
re-save of v17 taught (DWP 2026-11-18__02-48-50, addenda ~12:15 and ~12:25, and the game runs at 11:58, 12:08, 12:18):
the conversion's signature, government= inside landed_data, and contract ids whose low 24 bits are the index.
"""
import re

import pytest

from ck3_save_migrator import carry_1_21 as C
from ck3_save_migrator import gamestate as gs


@pytest.fixture
def game(tmp_path):
    c = tmp_path / "game" / "common"
    (c / "landed_titles").mkdir(parents=True)
    (c / "governments").mkdir(parents=True)
    (c / "landed_titles" / "00_titles.txt").write_text(
        "d_x = {\n\tc_new = {\n\t\tb_capital = { }\n\t\tb_moved = { }\n\t\tb_second = { }\n\t}\n\tc_far = {\n\t\tb_far = { }\n\t}\n"
        "\tc_home = {\n\t\tb_stay = { }\n\t}\n}\n", encoding="utf-8")
    (c / "governments" / "00_government_types.txt").write_text(
        "feudal_government = {\n}\nrepublic_government = {\n}\n", encoding="utf-8")
    return tmp_path


def title(i, key, holder):
    return f"\t\t{i}={{\n\t\t\ttype=title_type_default_static\tkey={key}\n\t\t\tholder={holder}\n\t\t}}\n"


def char(i, landed, extra=""):
    return f"\t{i}={{\n\t\tfirst_name=\"x\"\n\t\tlanded_data={{\n{landed}\t\t}}\n{extra}\t}}\n"


def resave(contracts=None, far_holder=500, second=False):
    contracts = contracts or {0x07000005: (300, 200, "levels={ 6 }"), 0x01000006: (200, 900, "levels={ 1 }")}
    return ("meta_data={\n\tdate=987.10.27\n}\nlanded_titles={\n\tlanded_titles={\n"
            + title(10, "c_new", 200) + title(11, "b_moved", 200) + title(12, "b_stay", 300)
            + title(13, "c_far", far_holder) + title(14, "b_far", 200) + title(15, "c_home", 300)
            + (title(16, "b_second", 200) if second else "")
            + "\t}\n}\nliving={\n"
            + char(100, "\t\t\tlaws={ x }\n")                                    # stripped: no domain, no government
            + char(101, "\t\t\tlaws={ x }\n")
            + char(200, f"\t\t\tdomain={{ 10 11 14{' 16' if second else ''} }}\n\t\t\tgovernment=feudal_government\n",
                   "\t\tvassal_contracts={ 117440517 }\n")
            + char(300, "\t\t\tdomain={ 12 15 }\n\t\t\tgovernment=republic_government\n")
            + char(500, "\t\t\tdomain={ 13 }\n\t\t\tgovernment=feudal_government\n")
            + char(900, "\t\t\tdomain={ 99 }\n\t\t\tgovernment=feudal_government\n")
            + "}\nvassal_contracts={\n\tdatabase={\n"
            + "".join(f"\t\t{k}={{\n\t\t\tvassal={v}\n\t\t\tliege={li}\n\t\t\tdate=1.1.1\n\t\t\t{lv}\n\t\t}}\n"
                      for k, (v, li, lv) in contracts.items())
            + "\t}\n}\n").encode()


def witness(gov100="republic_government", second=False):
    return ("meta_data={\n\tdate=987.10.27\n}\nlanded_titles={\n\tlanded_titles={\n"
            + title(11, "b_moved", 100) + title(12, "b_stay", 300) + title(14, "b_far", 101)
            + (title(16, "b_second", 300) if second else "")
            + "\t}\n}\nliving={\n"
            + char(100, f"\t\t\tdomain={{ 11 }}\n\t\t\tgovernment={gov100}\n\t\t\trealm_capital=11\n")
            + char(101, "\t\t\tdomain={ 14 }\n\t\t\tgovernment=republic_government\n")
            + char(300, "\t\t\tdomain={ 12 }\n\t\t\tgovernment=republic_government\n")
            + "}\n").encode()


def run(game, g=None, w=None):
    return C.carry_baronies(g or resave(), w or witness(), C.barony_counties(game), C.defined_governments(game))


def living(g, i):
    e = {e.key.decode(): e for e in gs.iter_entries(g, *gs.locate(g, "living").body) if e.key}[str(i)]
    return g[e.open:e.close]


def holder(g, key):
    for e in gs.iter_entries(g, *gs.locate(g, "landed_titles/landed_titles").body):
        body = g[e.open:e.close]
        if re.search(rb"\bkey=" + key.encode() + rb"\b", body):
            return re.search(rb"\bholder=(\d+)", body).group(1).decode()


def test_a_moved_barony_goes_back_to_its_witness_holder_as_the_county_holders_vassal(game):
    r = run(game)
    g = r.gamestate
    assert [(k, h, li) for k, h, li, _ in r.carried] == [("b_moved", "100", "200")]
    assert holder(g, "b_moved") == "100"
    b100 = living(g, 100)
    assert re.search(rb"domain=\{ 11 \}", b100)
    assert C.gov_of_landed(g, {e.key.decode(): e for e in gs.iter_entries(g, *gs.locate(g, "living").body)
                               if e.key}["100"]) == "republic_government"     # 1.21 keeps it inside landed_data
    assert b"realm_capital=11" in b100
    assert re.search(rb"domain=\{ 10 14 \}", living(g, 200))                  # out of the county holder's domain
    rows = [g[e.open:e.close] for e in gs.iter_entries(g, *gs.locate(g, "vassal_contracts/database").body)]
    new = [x for x in rows if b"vassal=100" in x]
    assert len(new) == 1 and b"liege=200" in new[0]
    assert b"levels={ 6 }" in new[0]       # what the game writes for a republic vassal of a feudal liege


def test_a_new_contract_takes_a_fresh_low_24_bit_index(game):
    # max+1 of the whole id (0x07000006) would reuse index 6, held by 0x01000006: the game dropped every such row
    g = run(game).gamestate
    ids = [int(e.key) for e in gs.iter_entries(g, *gs.locate(g, "vassal_contracts/database").body)]
    assert len({i & 0xFFFFFF for i in ids}) == len(ids)
    new = ids[-1]
    assert new & 0xFFFFFF == 7
    listed = re.search(rb"vassal_contracts=\{([^}]*)\}", living(g, 200)).group(1).split()
    assert sorted(listed) == sorted([b"117440517", str(new).encode()])     # the liege lists it (order is free)


def test_only_the_conversions_signature_is_carried(game):
    # b_far's holder 200 does not hold its county (c_far: 500), so it was not the conversion's hand-over: left alone
    r = run(game)
    assert "b_far" not in [k for k, *_ in r.carried]
    assert holder(r.gamestate, "b_far") == "200"


def test_a_government_1_21_does_not_define_is_reported_not_written(game):
    r = run(game, w=witness(gov100="merchant_republic_government"))
    assert not r.carried and r.gamestate == resave()
    assert r.skipped == [("b_moved", "100", "the witness government merchant_republic_government is not defined "
                                            "in 1.21")]


def test_a_holder_who_kept_other_land_gets_the_barony_into_the_domain_they_have(game):
    # 16 such holders in djdarcy's re-save of v17: 300 still holds b_stay and c_home, and lost b_second to 200
    r = run(game, g=resave(second=True), w=witness(second=True))
    g = r.gamestate
    assert ("b_second", "300", "200", "kept their own liege: holds other land") in r.carried
    assert holder(g, "b_second") == "300"
    assert re.search(rb"domain=\{ 12 15 16 \}", living(g, 300))
    assert re.search(rb"domain=\{ 10 14 \}", living(g, 200))      # gave b_moved and b_second, in one edit
    assert len(re.findall(rb"\bgovernment=", living(g, 300))) == 1


def test_a_barony_key_with_an_apostrophe_is_read_whole(tmp_path):
    # 1.21 has b_mansa'l-kharaz and b_ka'abir; `[\w-]+` read them as b_mansa and b_ka, so R37 skipped them (F7)
    c = tmp_path / "game" / "common" / "landed_titles"
    c.mkdir(parents=True)
    (c / "t.txt").write_text("c_x = {\n\tb_ka'abir = { }\n}\n", encoding="utf-8")
    assert C.barony_counties(tmp_path) == {"b_ka'abir": "c_x"}
    g = resave().replace(b"key=b_moved", b"key=b_mo'ved")
    rows = {k for _, k, _, _ in C._title_rows(g)}
    assert "b_mo'ved" in rows


def test_a_holder_who_died_in_the_conversion_is_skipped_and_named(game):
    # the old holder must be alive in the 1.21 save the barony goes back into, not only in the witness
    # (mutation sweep v0.6.32, M11: checking the witness instead would reach for him in the 1.21 save and fail)
    g = resave().replace(b"\t100={\n\t\tfirst_name=\"x\"\n\t\tlanded_data={\n\t\t\tlaws={ x }\n\t\t}\n\t}\n", b"", 1)
    r = run(game, g=g)
    assert ("b_moved", "100", "the old holder is not alive in the 1.21 save") in r.skipped
    assert holder(r.gamestate, "b_moved") == "200"


def test_a_capital_the_old_holder_no_longer_holds_is_not_written_back(game):
    # his 1.20 realm_capital (b_stay, 12) is not among the baronies carried back to him, so the first carried one
    # becomes his capital: a capital must be a title he holds (mutation sweep v0.6.32 round 2, R2M8)
    w = witness().replace(b"realm_capital=11", b"realm_capital=12")
    r = run(game, w=w)
    assert re.search(rb"\brealm_capital=11\b", living(r.gamestate, 100))
    assert not re.search(rb"\brealm_capital=12\b", living(r.gamestate, 100))


def test_a_second_run_changes_nothing(game):
    once = run(game).gamestate
    assert run(game, g=once).gamestate == once
