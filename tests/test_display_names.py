"""The game's display names in lookups (names.NameBook; faith_lookup and faith_rules finders), on a fake game
folder so no installed game is needed. Design: the 01-57-40 DWP (multi-word names, S2), unit U2."""

from __future__ import annotations

import pytest

from ck3_save_migrator import faith_lookup as F
from ck3_save_migrator import faith_rules as R
from ck3_save_migrator import names as N
from tests.test_edit_doctrines import GAME as RULES_FILES

LOC = {
    "religion/religion_l_english.yml":
        'l_english:\n holy_site_ise_jingu_name: "Ise Jingū" # 伊勢神宮\n holy_site_iona_name:0 "Iona"\n'
        ' holy_site_carthage_name: "Carthage"\n holy_site_carthage_adoptionist_name: "Carthage"\n'
        ' holy_site_bordeaux_name: "$c_bordeaux$"\n c_bordeaux: "Bordeaux"\n'
        ' asatru: "Ásatrú"\n shafii: "Shafi\'i"\n adoptionist_rite: "$adoptionist$"\n adoptionist: "Adoptionism"\n',
    "religion/doctrines_l_english.yml":
        'l_english:\n tenet_christian_syncretism_name: "Christian Syncretism"\n'
        ' tenet_jewish_syncretism_name: "Jewish Syncretism"\n tenet_gnosticism_name: "$gnosis$"\n gnosis: "$gn2$"\n'
        ' gn2: "Gnosticism"\n doctrine_pilgrimage_encouraged_name: "Encouraged"\n'
        ' doctrine_pilgrimage_forbidden_name: "Forbidden"\n doctrine_funeral_sky_burial_name: "Encouraged"\n'
        ' doctrine_pilgrimage_name: "Pilgrimage Attitude"\n doctrine_funeral_name: "Funeral"\n',
}
SAVE = (b'religion={\n\tholy_sites={\n\t\t0={\n\t\t\tholy_site_type=ise_jingu\n\t\t}\n'
        b'\t\t1={\n\t\t\tholy_site_type=iona\n\t\t}\n\t\t2={\n\t\t\tholy_site_type=carthage\n\t\t}\n'
        b'\t\t3={\n\t\t\tholy_site_type=carthage_adoptionist\n\t\t}\n\t\t4={\n\t\t\tholy_site_type=bordeaux\n\t\t}\n\t}\n}\n'
        b'rites={\n\tdatabase={\n\t\t100={\n\t\t\trite_type=asatru\n\t\t\tfaith=9\n\t\t}\n'
        b'\t\t16={\n\t\t\trite_type=shafii\n\t\t\tfaith=50\n\t\t}\n'
        b'\t\t18={\n\t\t\trite_type=adoptionist_rite\n\t\t\tfaith=8\n\t\t}\n\t}\n}\n'
        b'faiths={\n\tdatabase={\n\t\t9={\n\t\t\treligion=3\n\t\t\ttag="dynamic_faith_9"\n'
        b'\t\t\tname="\xc3\x81satr\xc3\xba Reformed"\n\t\t}\n\t}\n}\n')


@pytest.fixture()
def game(tmp_path):
    root = tmp_path / "game"
    for rel, text in {**{f"localization/english/{k}": v for k, v in LOC.items()}, **RULES_FILES}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return root


def test_the_book_reads_names_resolving_references_and_ignoring_comments(game):
    b = N.NameBook(game)
    assert b.display("holy_site_ise_jingu_name") == "Ise Jingū"
    assert b.display("holy_site_iona_name") == "Iona"                    # the ":0" form
    assert b.display("holy_site_bordeaux_name") == "Bordeaux"            # one reference
    assert b.display("tenet_gnosticism_name") == "Gnosticism"            # two levels of reference
    assert b.display("no_such_key") is None and b.display(None) is None


def test_no_book_without_a_game_folder(tmp_path):
    assert N.book(None) is None and N.book(tmp_path) is None


@pytest.mark.parametrize("typed", ["Ise Jingū", "Ise Jingu", "ise jingu", "ise_jingu", "0"])
def test_a_holy_site_by_the_name_the_game_shows_with_or_without_accents(game, typed):
    assert F.find_holy_site(SAVE, typed, book=N.NameBook(game)) == "0"


def test_a_shared_holy_site_name_is_refused_with_both_and_settled_by_the_faith_s_own_sites(game):
    b = N.NameBook(game)
    with pytest.raises(LookupError, match=r"'Carthage' names 2: Carthage \(carthage, 2\), Carthage "
                                          r"\(carthage_adoptionist, 3\); write the one you mean"):
        F.find_holy_site(SAVE, "Carthage", book=b)
    assert F.find_holy_site(SAVE, "Carthage", book=b, prefer=["1", "3"]) == "3"


def test_without_a_game_folder_keys_still_match_and_a_miss_says_why(game):
    assert F.find_holy_site(SAVE, "Ise Jingu") == "0"                       # the type, folded
    with pytest.raises(LookupError, match="need the game folder: set CK3_GAME_DIR"):
        F.find_holy_site(SAVE, "Bordeaux Cathedral")


@pytest.mark.parametrize("typed", ["Ásatrú", "asatru"])
def test_a_rite_by_its_display_name_and_labelled_by_it(game, typed):
    b = N.NameBook(game)
    r = F.find_rite(SAVE, typed, book=b)
    assert r.id == "100" and F.rite_name(r, b) == "Ásatrú" and F.rite_name(r) == "asatru"


def test_a_rite_whose_display_name_is_not_its_key_is_found_only_through_the_book(game):
    assert F.find_rite(SAVE, "Adoptionism", book=N.NameBook(game)).id == "18"
    with pytest.raises(LookupError):
        F.find_rite(SAVE, "Adoptionism")                                     # the key is adoptionist_rite


def test_a_save_s_own_accented_name_is_found_typed_without_accents():
    assert F.find_faith(SAVE, "Asatru Reformed").id == "9"                 # no key spells it; only folding can


def test_a_tenet_and_a_qualified_doctrine_by_their_display_names(game):
    b, rules = N.NameBook(game), R.load(str(game))
    assert R.find_belief(rules, "Christian Syncretism", b) == "tenet_christian_syncretism"
    assert R.find_belief(rules, "Pilgrimage Attitude: Encouraged", b) == "doctrine_pilgrimage_encouraged"
    assert R.find_belief(rules, "doctrine_pilgrimage: encouraged", b) == "doctrine_pilgrimage_encouraged"
    assert R.belief_name(rules, "doctrine_pilgrimage_encouraged", b) == "Pilgrimage Attitude: Encouraged"


def test_a_doctrine_name_two_groups_share_is_refused_listing_the_qualified_forms(game):
    b, rules = N.NameBook(game), R.load(str(game))
    with pytest.raises(LookupError, match=r"'Encouraged' names 2: Funeral: Encouraged \(doctrine_funeral_sky_burial\), "
                                          r"Pilgrimage Attitude: Encouraged \(doctrine_pilgrimage_encouraged\)"):
        R.find_belief(rules, "Encouraged", b)


def test_an_unknown_group_is_refused(game):
    with pytest.raises(LookupError, match="no doctrine group 'Pilgrimage Mood'"):
        R.find_belief(R.load(str(game)), "Pilgrimage Mood: Encouraged", N.NameBook(game))
