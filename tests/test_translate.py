"""Tests for ck3_save_migrator.translate (R13) and its schema, on synthetic gamestates.

The id model under test (measured on real saves, see translate.py): an id is a 24-bit slot index plus an 8-bit
generation; a reference id translates by a join, by identity, or by an offset on the index that keeps the
generation. The last test runs the whole reference when the gitignored extracted gamestates are present.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

import pytest

from ck3_save_migrator import gamestate as gs
from ck3_save_migrator import idschema as S
from ck3_save_migrator import translate as T

G1 = 1 << 24          # generation 1


def char(i: int, body: str = "") -> str:
    return f"{i}={{\n\tfirst_name=\"P{i}\"\n{body}}}\n"


def gamestate(*, living="", dead="", prunable="", titles="", cultures="", lookup="", traits="",
              coa="", coa_next=None, title_index=None, dynasties="", houses="", extra="") -> bytes:
    parts = [
        f"traits_lookup={{ {traits} }}\n",
        f"character_lookup={{\n{lookup}}}\n",
        f"landed_titles={{\n\tlanded_titles={{\n{titles}\t}}\n" + (f"\tindex={title_index}\n" if title_index is not None else "") + "}\n",
        f"dynasties={{\n\tdynasty_house={{\n{houses}\t}}\n\tdynasties={{\n{dynasties}\t}}\n}}\n",
        f"living={{\n{living}}}\n",
        f"dead_unprunable={{\n{dead}}}\n",
        f"characters={{\n\tdead_prunable={{\n{prunable}\t}}\n}}\n",
        f"culture_manager={{\n\tcultures={{\n{cultures}\t}}\n}}\n",
        f"coat_of_arms={{\n\tcoat_of_arms_manager_database={{\n{coa}\t}}\n" + (f"\tnext_id={coa_next}\n" if coa_next is not None else "") + "}\n",
        extra,
    ]
    return "".join(parts).encode()


def title(i: int, key: str, body: str = "") -> str:
    return f"{i}={{\n\tkey={key}\n{body}}}\n"


def culture(i: int, template: str | None, name: str = "x") -> str:
    t = f"\t\t\tculture_template=\"{template}\"\n" if template else ""
    return f"{i}={{\n{t}\t\t\tname=\"{name}\"\n}}\n"


def entry(g: bytes, path: str, i: int) -> gs.Block:
    return dict(T.entries(g, path))[i]


# --------------------------------------------------------------------------- #
# the id model
# --------------------------------------------------------------------------- #
def test_index_and_generation_split_the_top_byte():
    i = 0x13003111
    assert T.index(i) == 0x3111 and T.generation(i) == 0x13


def test_offset_is_above_the_save_maximum_index_and_keeps_the_generation():
    save = gamestate(living=char(5) + char(G1 | 9))          # max index 9 (generation 1)
    ref = gamestate(living=char(0) + char(3 * G1 | 2))
    tr = T.Translator.build(save, ref)
    m = tr.spaces["character"]
    assert m.base == 10
    assert m.translate(0) == 10
    assert m.translate(3 * G1 | 2) == 3 * G1 | 12            # generation 3 kept, index 2 + 10


def test_the_three_character_sections_are_one_space():
    save = gamestate(living=char(4), dead=char(G1 | 40), prunable=char(2 * G1 | 70))
    ref = gamestate(living=char(1))
    assert T.Translator.build(save, ref).spaces["character"].base == 71


def test_translated_indices_never_meet_a_save_index():
    save_ids = [5, G1 | 9, 2 * G1 | 3, 4 * G1 | 100]
    save = gamestate(living="".join(char(i) for i in save_ids))
    ref_ids = list(range(0, 120)) + [7 * G1 | 50]
    ref = gamestate(living="".join(char(i) for i in ref_ids))
    m = T.Translator.build(save, ref).spaces["character"]
    out = [m.translate(i) for i in ref_ids]
    assert len(set(out)) == len(ref_ids)
    assert not {T.index(v) for v in out} & {T.index(i) for i in save_ids}


def test_overflow_of_the_slot_index_is_refused():
    save = gamestate(living=char(T.LOW - 5))
    ref = gamestate(living=char(10))
    with pytest.raises(T.TranslationError, match="24-bit"):
        T.Translator.build(save, ref)


def test_none_sentinel_passes_through():
    tr = T.Translator.build(gamestate(living=char(7)), gamestate(living=char(1)))
    assert tr.id("character", T.NONE) == T.NONE


def test_a_space_absent_from_the_save_keeps_its_ids():
    save = gamestate()
    ref = gamestate(extra="domiciles={\n\tdatabase={\n0={\n}\n1={\n}\n2={\n}\n\t}\n}\n")
    m = T.Translator.build(save, ref).spaces["domicile"]
    assert m.base == 0 and m.translate(2) == 2


def test_identity_spaces_keep_their_ids():
    save = gamestate(extra="provinces={\n1={\n}\n2={\n}\n}\n")
    ref = gamestate(extra="provinces={\n1={\n}\n2={\n}\n9999={\n}\n}\n")
    tr = T.Translator.build(save, ref)
    assert tr.id("province", 9999) == 9999 and tr.spaces["province"].identity


def test_a_repeated_entry_counts_once():
    ref = gamestate(dead=char(3) + char(4) + char(3) + char(4))      # 1.20 writes dead_unprunable twice
    assert [i for i, _ in T.entries(ref, "dead_unprunable")] == [3, 4]


# --------------------------------------------------------------------------- #
# joins
# --------------------------------------------------------------------------- #
def test_titles_join_by_key_but_runtime_x_titles_never_do():
    save = gamestate(titles=title(G1 | 4, "k_france") + title(9, "x_x_5"))
    ref = gamestate(titles=title(0, "k_france") + title(1, "x_x_5") + title(2, "k_new"))
    tr = T.Translator.build(save, ref)
    assert tr.id("title", 0) == G1 | 4                 # joined, generation of the save's object
    assert tr.id("title", 1) == 1 + 10                 # x_x_5 is a different title: offset
    assert tr.id("title", 2) == 2 + 10


def test_quoted_and_bare_keys_join():
    save = gamestate(titles=title(3, '"d_x"'))
    ref = gamestate(titles=title(0, "d_x"))
    assert T.Translator.build(save, ref).id("title", 0) == 3


def test_an_ambiguous_key_is_refused():
    save = gamestate(titles=title(1, "k_a") + title(2, "k_a"))
    with pytest.raises(T.TranslationError, match="names both"):
        T.Translator.build(save, gamestate(titles=title(0, "k_a")))


def test_two_reference_objects_joining_one_save_object_are_refused():
    save = gamestate(living=char(30), lookup="\t500=30\n\t501=30\n")
    ref = gamestate(living=char(7) + char(8), lookup="\t500=7\n\t501=8\n")
    with pytest.raises(T.TranslationError, match="join the same save object"):
        T.Translator.build(save, ref)


def test_a_nested_key_is_not_the_entry_key():
    save = gamestate(titles=title(3, "k_real"))
    ref = gamestate(titles="0={\n\tvariables={\n\t\tkey=k_fake\n\t}\n\tkey=k_real\n}\n")
    assert T.Translator.build(save, ref).id("title", 0) == 3


def test_cultures_join_by_template_and_campaign_cultures_never_do():
    save = gamestate(cultures=culture(0, "irish") + culture(1, None, "Anglo-Irish"))
    ref = gamestate(cultures=culture(0, "han") + culture(1, "irish"))
    tr = T.Translator.build(save, ref)
    assert tr.id("culture", 1) == 0                    # irish -> the save's irish
    assert tr.id("culture", 0) == 2                    # han is new: offset above the save's max (1)
    assert tr.spaces["culture"].join == {1: 0}


def test_characters_join_by_history_id():
    save = gamestate(living=char(G1 | 30), lookup="\t500=16777246\n")
    ref = gamestate(living=char(7) + char(8), lookup="\t500=7\n\t600=8\n")
    tr = T.Translator.build(save, ref)
    assert tr.id("character", 7) == G1 | 30
    assert tr.id("character", 8) == 8 + 31


def test_a_history_join_to_a_pruned_character_is_kept_and_reported():
    save = gamestate(living=char(12), lookup="\t500=9\n")              # 9 was pruned by the campaign
    ref = gamestate(living=char(7) + char(8, "\tfamily_data={\n\t\tchild={ 7 }\n\t}\n"), lookup="\t500=7\n")
    tr = T.Translator.build(save, ref)
    assert tr.spaces["character"].join_pruned == {7: 9}
    rep = T.RewriteReport()
    text = T.rewrite_entry(ref, entry(ref, "living", 8), "living", tr, rep)
    assert b"child={ 9 }" in text
    assert rep.to_pruned["character"] == 1


def test_a_join_never_writes_into_the_campaign():
    """A10b's invariant: a history-id join only redirects the reference's references to the save's id."""
    save = gamestate(living=char(30, "\tculture=0\n"), lookup="\t500=30\n")
    ref = gamestate(living=char(7, "\tculture=5\n") + char(8, "\tfamily_data={\n\t\tspouse=7\n\t}\n"),
                    lookup="\t500=7\n")
    before = hashlib.sha256(save).hexdigest()
    tr = T.Translator.build(save, ref)
    spouse = T.rewrite_entry(ref, entry(ref, "living", 8), "living", tr)
    assert b"spouse=30" in spouse                      # the reference's reference goes to the campaign's person
    assert hashlib.sha256(save).hexdigest() == before  # the campaign's entry is untouched
    assert 7 in tr.spaces["character"].join            # and the joined person is marked, so it is not copied


def test_founding_houses_join_through_their_dynasty():
    save = gamestate(dynasties='5={\n\tkey=1000\n}\n',
                     houses='9={\n\tname="dynn_A"\n\tdynasty=5\n}\n' '11={\n\tname="dynn_B"\n\tdynasty=5\n}\n')
    ref = gamestate(dynasties='0={\n\tkey=1000\n}\n',
                    houses='0={\n\tname="dynn_A"\n\tdynasty=0\n}\n' '1={\n\tkey=house_x\n\tname="dynn_C"\n\tdynasty=0\n}\n')
    tr = T.Translator.build(save, ref)
    assert tr.id("dynasty", 0) == 5
    assert tr.id("house", 0) == 9                      # same dynasty (after its join), same name
    assert tr.id("house", 1) == 1 + 12                 # a keyed house the save lacks: offset


# --------------------------------------------------------------------------- #
# traits, counters
# --------------------------------------------------------------------------- #
def test_traits_translate_by_name_and_missing_names_are_appended():
    save = gamestate(traits="brave shy")
    ref = gamestate(traits="shy calm brave")
    tr = T.Translator.build(save, ref)
    assert tr.trait_map == {0: 1, 1: 2, 2: 0}
    assert tr.new_traits == ["calm"]


def test_counters_are_read_and_the_coat_counter_is_raised():
    coa = "0={\n\tpattern=\"x\"\n}\n" "39252={\n\tpattern=\"y\"\n}\n"
    save = gamestate(coa=coa, coa_next=39253, title_index=1849)
    ref = gamestate(coa="0={\n}\n7={\n}\n")
    tr = T.Translator.build(save, ref)
    assert tr.save_coa_next_id == 39253 and tr.save_title_index == 1849
    added = [tr.spaces["coat_of_arms"].translate(i) for i in (0, 7)]
    assert added == [39253, 39260]
    assert tr.coa_next_id(added) == 39261
    assert tr.coa_next_id([]) == 39253


# --------------------------------------------------------------------------- #
# the rewriter
# --------------------------------------------------------------------------- #
REF_PERSON = (
    "\tculture=1\n\trite=4\n\tdynasty_house=0\n\ttraits={ 0 2 }\n\tskill={ 5 6 7 8 9 10 }\n"
    "\tfamily_data={\n\t\tprimary_spouse=2\n\t\tchild={ 3 4294967295 }\n\t}\n"
    "\tcourt_data={\n\t\temployer=2\n\t}\n"
    "\tlanded_data={\n\t\tdomain={ 0 }\n\t\trealm_capital=0\n\t}\n"
    "\talive_data={\n\t\tlocation={ location=12000 }\n\t\tvariables={\n\t\t\tdata={ {\n"
    "\t\t\t\tflag=x\n\t\t\t\tdata={\n\t\t\t\t\ttype=char\n\t\t\t\t\tidentity=3\n\t\t\t\t}\n\t\t\t}\n"
    " {\n\t\t\t\tflag=y\n\t\t\t\tdata={\n\t\t\t\t\ttype=value\n\t\t\t\t\tidentity=77\n\t\t\t\t}\n\t\t\t}\n }\n"
    "\t\t}\n\t}\n"
)


def rewrite_fixture():
    save = gamestate(living=char(20), titles=title(4, "k_old"), cultures=culture(0, "irish"),
                     traits="brave shy", houses='5={\n\tkey=house_s\n}\n')
    ref = gamestate(living=char(1, REF_PERSON) + char(2) + char(3), titles=title(0, "k_new"),
                    cultures=culture(0, "han") + culture(1, "irish"), traits="shy calm brave",
                    houses='0={\n\tkey=house_r\n}\n')
    return save, ref


def test_a_block_with_mixed_spaces_is_translated_field_by_field():
    save, ref = rewrite_fixture()
    tr = T.Translator.build(save, ref)
    rep = T.RewriteReport()
    out = T.rewrite_entry(ref, entry(ref, "living", 1), "living", tr, rep).decode()
    assert out.startswith("22={")                      # own key: character, base 21
    assert "\tculture=0\n" in out                      # irish joined
    assert "\trite=4\n" in out                         # identity space
    assert "dynasty_house=6\n" in out                  # house: offset above 5
    assert "traits={ 1 0 }" in out                     # shy->1, brave->0
    assert "skill={ 5 6 7 8 9 10 }" in out             # plain
    assert "primary_spouse=23" in out and "employer=23" in out
    assert "child={ 24 4294967295 }" in out            # none kept
    assert "domain={ 5 }" in out and "realm_capital=5" in out   # title base 5
    assert "location=12000" in out                     # province identity
    assert "type=char\n\t\t\t\t\tidentity=24" in out   # typed reference translated
    assert "type=value\n\t\t\t\t\tidentity=77" in out  # a typed number is not an id
    assert not rep.unlisted and not rep.unknown_types


def test_only_the_id_tokens_change():
    save, ref = rewrite_fixture()
    tr = T.Translator.build(save, ref)
    e = entry(ref, "living", 1)
    before = ref[e.start:e.end]
    after = T.rewrite_entry(ref, e, "living", tr)
    tok = re.compile(rb"\d+")
    assert tok.sub(b"N", before) == tok.sub(b"N", after)


def test_an_unknown_field_is_reported_not_passed_silently():
    save = gamestate(living=char(2))
    ref = gamestate(living=char(0, "\tbrand_new_field=17\n\tmass=3\n"))
    tr = T.Translator.build(save, ref)
    rep = T.RewriteReport()
    out = T.rewrite_entry(ref, entry(ref, "living", 0), "living", tr, rep)
    assert b"brand_new_field=17" in out
    assert rep.unlisted == {("living", "brand_new_field"): 1}


def test_an_unknown_reference_type_is_reported():
    save = gamestate(living=char(2))
    ref = gamestate(living=char(0, "\tv={\n\t\ttype=martian\n\t\tidentity=5\n\t}\n"))
    rep = T.RewriteReport()
    T.rewrite_entry(ref, entry(ref, "living", 0), "living", T.Translator.build(save, ref), rep)
    assert rep.unknown_types == {"martian": 1}


def test_numeric_keys_that_are_ids_are_translated():
    save = gamestate(cultures=culture(0, "irish") + culture(1, "welsh"))
    ref = gamestate(cultures=culture(0, "han") + '1={\n\t\t\tculture_template="irish"\n\t\t\tacceptance={\n'
                    '\t\t\t\t0=35\n\t\t\t\t1=50\n\t\t\t}\n}\n')
    tr = T.Translator.build(save, ref)
    out = T.rewrite_entry(ref, entry(ref, "culture_manager/cultures", 1), "culture_manager/cultures", tr)
    assert out.startswith(b"0={")                      # irish joined: its own key goes to the save's id
    assert b"2=35" in out and b"0=50" in out           # han -> 2 (offset), irish -> 0 (join); values kept


def test_keep_removes_references_to_objects_that_will_not_exist():
    save, ref = rewrite_fixture()
    tr = T.Translator.build(save, ref)
    rep = T.RewriteReport()
    gone = {("character", 3), ("title", 0)}           # child 3 and the domain title are not transplanted

    def keep(space, ref_id, path):
        return (space, ref_id) not in gone

    out = T.rewrite_entry(ref, entry(ref, "living", 1), "living", tr, rep, keep=keep).decode()
    assert out.startswith("22={")                      # the entry's own id is never removed
    assert "child={ 4294967295 }" in out               # list item removed, the 'none' kept
    assert "domain={ }" in out and "realm_capital" not in out   # list item and key=value line removed
    assert "flag=x" not in out and "flag=y" in out     # the variable carrying the refused typed reference goes
    assert "primary_spouse=23" in out                  # kept references still translated
    assert rep.dropped == {("living", "family_data/child/*"): 1, ("living", "landed_data/domain/*"): 1,
                           ("living", "landed_data/realm_capital"): 1,
                           ("living", "alive_data/variables/data/[]/data/identity"): 1}
    gs.iter_children(out.encode(), 0, len(out))        # still well-formed text


def test_keep_sees_the_field_path():
    save, ref = rewrite_fixture()
    tr = T.Translator.build(save, ref)
    seen = []

    def keep(space, ref_id, path):
        seen.append((space, path))
        return path != "landed_data/realm_capital"     # the same title, kept in domain, refused as capital

    out = T.rewrite_entry(ref, entry(ref, "living", 1), "living", tr, keep=keep).decode()
    assert "domain={ 5 }" in out and "realm_capital" not in out
    assert ("title", "landed_data/domain/*") in seen


def test_a_removed_item_takes_the_translations_inside_it_along():
    """A refused typed reference removes its whole list item; another id inside that item must not be edited
    as well (overlapping edits would corrupt the text)."""
    save = gamestate(living=char(20))
    ref = gamestate(living=char(1, "\talive_data={\n\t\tvariables={\n\t\t\tlist={ {\n"
                                   "\t\t\t\titem={ type=char identity=3 }\n"
                                   "\t\t\t\textra={ type=char identity=2 }\n\t\t\t}\n }\n\t\t}\n\t}\n")
                    + char(2) + char(3))
    tr = T.Translator.build(save, ref)
    out = T.rewrite_entry(ref, entry(ref, "living", 1), "living", tr, keep=lambda sp, i, path: i != 3)
    assert b"identity" not in out and b"extra" not in out
    assert out.startswith(b"22={") and out.count(b"{") == out.count(b"}")


def test_keep_on_a_numeric_key_removes_that_child():
    save = gamestate(cultures=culture(0, "irish"))
    ref = gamestate(cultures=culture(0, "han") + '1={\n\t\t\tculture_template="irish"\n\t\t\tacceptance={\n'
                    '\t\t\t\t0=35\n\t\t\t\t1=50\n\t\t\t}\n}\n')
    tr = T.Translator.build(save, ref)
    out = T.rewrite_entry(ref, entry(ref, "culture_manager/cultures", 1), "culture_manager/cultures", tr,
                          keep=lambda sp, i, path: not (sp == "culture" and i == 0))
    assert b"35" not in out and b"0=50" in out


def test_references_lists_every_id_by_space():
    _, ref = rewrite_fixture()
    refs = {(path, sp, i) for path, sp, i in T.references(ref, entry(ref, "living", 1), "living")}
    assert refs == {("culture", "culture", 1), ("rite", "rite", 4), ("dynasty_house", "house", 0),
                    ("family_data/primary_spouse", "character", 2), ("family_data/child/*", "character", 3),
                    ("court_data/employer", "character", 2), ("landed_data/domain/*", "title", 0),
                    ("landed_data/realm_capital", "title", 0), ("alive_data/location/location", "province", 12000),
                    ("alive_data/variables/data/[]/data/identity", "character", 3)}
    # traits, skills, the 'none' child and the typed *value* (identity=77) are not references


def test_schema_wildcard_and_typed_rules():
    assert S.classify("living", "alive_data/inventory/equipped/trinket_3") == "artifact"
    assert S.classify("dead_unprunable", "family_data/child/*") == "character"
    assert S.classify("living", "alive_data/anything/identity") == S.TYPED
    assert S.classify("living", "skill/*") == S.PLAIN
    assert S.classify("living", "no_such_field") is None
    assert S.KIND_SPACE["ai/ai_strategies"] == "character"


# --------------------------------------------------------------------------- #
# the whole reference (when the gitignored data is present)
# --------------------------------------------------------------------------- #
ROOT = Path(__file__).resolve().parents[1]
SAVE_GS = ROOT / "private" / "data" / "extracted" / "987_r1-r12_wos-faith" / "gamestate"
REF_GS = ROOT / "private" / "data" / "extracted" / "ref_1_20_987_10_27" / "gamestate"


@pytest.mark.skipif(os.environ.get("CK3_REAL_SAVES") != "1" or not (SAVE_GS.exists() and REF_GS.exists()),
                    reason="opt-in (CK3_REAL_SAVES=1, about 3 minutes); needs the gitignored extracted gamestates")
def test_whole_reference_translates_without_collision():
    save, ref = SAVE_GS.read_bytes(), REF_GS.read_bytes()
    tr = T.Translator.build(save, ref)
    for sp, m in tr.spaces.items():
        r_ids = T.space_ids(ref, sp)
        out = {i: m.translate(i) for i in r_ids}
        assert len(set(out.values())) == len(out), sp
        s_idx = {i & T.LOW for i in T.space_ids(save, sp)}
        assert not {v & T.LOW for i, v in out.items() if i not in m.join and v != i} & s_idx, sp
        assert all(v < T.NONE for v in out.values()), sp
