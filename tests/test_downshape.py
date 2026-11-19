"""downshape: rows copied from a 1.21 reference, shaped to the 1.20 save they enter (goal F2, 2026-11-18).

Each case is a measured lesson: 1.21's type line, the fields that point into databases a 1.20 save lacks, the two
fields every 1.20 row has that a 1.21 row lacks (county development, holdings' buildings), and the stray brace a
pattern-based strip left on 2026-11-18 (a nested block must go whole, or not at all).
"""
import pytest

from ck3_save_migrator import downshape as D


def test_a_title_loses_its_type_line_and_the_1_21_fields():
    out = D.Shaped()
    t = (b"5={\n\ttype=title_type_default_static\tkey=c_y\n\ttrade_market=126\n\tconfederation=4294967295\n"
         b"\tholder=7\n\tvoting_session_ended=-5000.1.1\n}\n")
    assert D.title(t, out) == b"5={\n\tkey=c_y\n\tholder=7\n}\n"
    assert out.counts == {"title type": 1, "title fields": 3}


def test_a_nested_block_goes_whole_and_a_deeper_namesake_stays():
    # run 2026-11-18__02-07-42 was voided by stripping `nomad=` but not its block; here the block goes with it,
    # and a field of the same name one level down is not this depth's business
    t = b"1={\n\tkey=x\n\tnoble_family={\n\t\tmembers={ 1 2 }\n\t}\n\tlaws={\n\t\ttrade_market=3\n\t}\n}\n"
    s, n = D.drop_fields(t, (b"noble_family", b"trade_market"), 1)
    assert n == 1 and s == b"1={\n\tkey=x\n\tlaws={\n\t\ttrade_market=3\n\t}\n}\n"
    assert s.count(b"{") == s.count(b"}")


@pytest.mark.parametrize("value", [b"3", b'"two words"', b"-5000.1.1", b"{ 1 2 }", b"{\n\t\tx=1\n\t}"])
def test_a_dropped_field_goes_whole_whatever_its_value(value):
    # a word, a quoted string, a date, an inline block, a block over lines: the field and all of its value go, and
    # nothing around them moves (mutation sweep v0.6.32 round 2, R2M1: a quoted value cut before its closing quote)
    t = b"1={\n\tkey=x\n\ttrade_market=" + value + b"\n\tholder=7\n}\n"
    s, n = D.drop_fields(t, (b"trade_market",), 1)
    assert n == 1 and s == b"1={\n\tkey=x\n\tholder=7\n}\n"


def test_a_county_record_gets_development_from_prosperity():
    # the game's own conversion sets prosperity = development (all 3,469 counties of v17)
    out = D.Shaped()
    r = (b"c_dublin={\n\t\t\tprosperity=10\n\t\t\tprosperity_progress=22.975\n\t\t\topinion_of_liege=0\n"
         b"\t\t\tculture=176\n\t\t}\n")
    s = D.county_record(r, out)
    assert b"development=10" in s and b"development_progress=22.975" in s
    assert b"prosperity" not in s and b"opinion_of_liege" not in s and b"culture=176" in s


def test_a_character_loses_1_21_trade_fields_inside_landed_data_only():
    out = D.Shaped()
    c = (b"7={\n\tfirst_name=\"A\"\n\tlanded_data={\n\t\tdomain={ 5 }\n\t\ttrade_routes={ 1 2 }\n"
         b"\t\tgold_expenses=3\n\t}\n}\n")
    s = D.character(c, out)
    assert s == b"7={\n\tfirst_name=\"A\"\n\tlanded_data={\n\t\tdomain={ 5 }\n\t}\n}\n"


def test_a_character_loses_1_21_assembly_fields_inside_playable_data():
    # the 1.21 reference keeps assembly and major_assembly_member in playable_data (3 characters, measured
    # 2026-11-18 for mutation sweep v0.6.32 round 2, R2M3); a landed_data namesake is not this strip's business
    c = (b"8={\n\tlanded_data={\n\t\tdomain={ 6 }\n\t}\n\tplayable_data={\n\t\tassembly=12\n"
         b"\t\tmajor_assembly_member=yes\n\t\tprestige=4\n\t}\n}\n")
    s = D.character(c, D.Shaped())
    assert s == b"8={\n\tlanded_data={\n\t\tdomain={ 6 }\n\t}\n\tplayable_data={\n\t\tprestige=4\n\t}\n}\n"


REF = (b"districts={\n\tdatabase={\n\t\t6310={\n\t\t\tbuildings={ 900 }\n\t\t}\n\t\t6311={\n\t\t\tbuildings={ 901 }\n"
       b"\t\t}\n\t}\n}\nbuildings={\n\tdatabase={\n\t\t900={\n\t\t\ttype=tribe_01\n\t\t}\n\t\t901={\n"
       b"\t\t\ttype=the_great_wall_01\n\t\t}\n\t}\n}\n")


def test_a_holding_district_in_its_real_shape_gives_its_primary_and_a_second_pass_changes_nothing():
    # the 1.21 reference's 6,732 holding districts list the primary building first in every case, then any other
    # buildings, then empty slots as 4294967295 (measured 2026-11-18 for mutation sweep v0.6.32, M6 "the last entry",
    # and M5: a shaped holding already has its buildings list, so shaping it again must change nothing)
    ref = (b"districts={\n\tdatabase={\n\t\t6400={\n\t\t\tbuildings={ 910 911 4294967295 }\n\t\t}\n\t}\n}\n"
           b"buildings={\n\tdatabase={\n\t\t910={\n\t\t\ttype=temple_02\n\t\t}\n\t\t911={\n"
           b"\t\t\ttype=temple_reliquary_2\n\t\t}\n\t}\n}\n")
    p = D.Provinces(ref, {"77": 3})
    prov = (b"77={\n\tholding={\n\t\ttype=church_holding\n\t\tdistricts={ 6400 }\n\t\tholding_district=6400\n"
            b"\t\tregular_district_slot_limit=2\n\t}\n}\n")
    s = p.province("77", prov, D.Shaped())
    bl = s[s.index(b"buildings={"):]
    assert bl.count(b"type=temple_02") == 1 and b"temple_reliquary_2" not in s
    assert p.province("77", s, D.Shaped()) == s


def test_a_holding_gets_a_1_20_buildings_list_from_its_districts():
    p = D.Provinces(REF, {"9537": 4})
    out = D.Shaped()
    prov = (b"9537={\n\tprovince_size_value=300\n\tprovince_size_level=3\n\tholding={\n\t\ttype=tribal_holding\n"
            b"\t\tdistricts={ 6310 6311 }\n\t\tholding_district=6310\n\t\tgreat_district=6311\n"
            b"\t\tgreat_district_type=the_great_wall_01_district\n\t\tregular_district_slot_limit=2\n\t}\n}\n")
    s = p.province("9537", prov, out)
    assert b"province_size" not in s and b"district" not in s
    assert s.count(b"{") == s.count(b"}")
    bl = s[s.index(b"buildings={"):]
    assert bl.count(b"type=tribe_01") == 1 and bl.count(b"{\n\t\t\t\t}") == 3      # 4 slots, the main one filled
    assert b"great_building_type=the_great_wall_01" in s and b"type=the_great_wall_01\n" in s
    assert out.counts["holding buildings derived"] == 1


def test_the_field_lists_from_the_baselines_equal_the_measured_ones():
    # the collab's round 3 measured these by hand; the shipped baselines now give them (F7, refactor row 5)
    assert set(D.TITLE_FIELDS) == {b"trade_market", b"confederation", b"voting_session_ended", b"noble_family",
                                   b"company_progression", b"ruler_uses_title_name"}
    assert set(D.PROVINCE_FIELDS) == {b"province_size_value", b"province_size_level"}
    assert set(D.DOMICILE_FIELDS) == {b"move_cooldown", b"acumen"}
    from ck3_save_migrator.baselines import added_fields
    assert added_fields("1.20.1.2", "0.0.0", "provinces") == ()          # a missing baseline gives nothing


def test_a_built_duchy_capital_wonder_comes_back_as_its_1_20_block():
    ref = REF.replace(b"type=the_great_wall_01", b"type=theodosian_walls_01")
    p = D.Provinces(ref, {"496": 4})
    s = p.province("496", b"496={\n\tholding={\n\t\ttype=castle_holding\n\t\tholding_district=6310\n"
                          b"\t\tduchy_capital_district=6311\n\t}\n}\n", D.Shaped())
    assert b"duchy_capital_building={\n\t\t\t\ttype=theodosian_walls_01" in s and b"duchy_capital_district" not in s


def test_the_measured_slot_table_beats_the_holding_types_usual_count():
    # a castle usually has 4 slots in 1.20, but the table measured from the 1.20 reference says this province has 2
    # (mutation sweep v0.6.32 round 2, R2M4: the only other fixture's table value equalled the usual count)
    p = D.Provinces(REF, {"501": 2})
    prov = b"501={\n\tholding={\n\t\ttype=castle_holding\n\t\tholding_district=6310\n\t}\n}\n"
    s = p.province("501", prov, D.Shaped())
    bl = s[s.index(b"buildings={"):s.index(b"\n\t\t\t}", s.index(b"buildings={")) + 5]
    assert bl.count(b"type=tribe_01") == 1 and bl.count(b"{\n\t\t\t\t}") == 1      # 2 slots, the main one filled


def test_a_province_the_table_lacks_takes_its_holding_types_usual_slots():
    p = D.Provinces(REF, {})
    s = p.province("99999", b"99999={\n\tholding={\n\t\ttype=city_holding\n\t\tholding_district=6310\n\t}\n}\n",
                   D.Shaped())
    bl = s[s.index(b"buildings={"):]
    assert bl.count(b"{\n\t\t\t\t}") == 2                                           # city: 3 slots, 1 filled
