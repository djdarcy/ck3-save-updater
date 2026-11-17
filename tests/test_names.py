"""The generic list parser (names.parse_list, split_qualifier, norm). Design: the 01-57-40 DWP (multi-word names, S2)."""

from __future__ import annotations

import pytest

from ck3_save_migrator.names import Item, NameListError, norm, parse_list, split_qualifier

SITES = {"bodh gaya": "bodh_gaya", "jerusalem": "jerusalem", "iona": "iona", "rome": "rome"}


def resolver(table):
    def resolve(text):
        try:
            return table[text.lower()]
        except KeyError:
            raise LookupError(text) from None
    return resolve


site = resolver(SITES)


def texts(items):
    return [(i.sign, i.text) for i in items]


def test_commas_separate_multi_word_names():
    assert [i.text for i in parse_list("Bodh Gaya, Jerusalem, Iona")] == ["Bodh Gaya", "Jerusalem", "Iona"]


def test_without_commas_each_word_is_an_item():
    assert [i.text for i in parse_list("jerusalem rome iona")] == ["jerusalem", "rome", "iona"]


def test_empty_parts_and_blank_text_give_nothing():
    assert [i.text for i in parse_list(" a , b ,, ")] == ["a", "b"]
    assert parse_list("   ") == []


def test_a_resolver_fills_each_value_and_its_refusal_propagates():
    assert [i.value for i in parse_list("Jerusalem, Iona", resolve=site)] == ["jerusalem", "iona"]
    with pytest.raises(LookupError):
        parse_list("Jerusalem, Atlantis", resolve=site)


def test_signs_start_items_without_commas_and_are_taken_off():
    got = parse_list("+Christian Syncretism -Jewish Syncretism", modifiers=True)
    assert texts(got) == [("+", "Christian Syncretism"), ("-", "Jewish Syncretism")]


def test_signs_with_commas_and_an_unsigned_first_item():
    got = parse_list("Pilgrimage Attitude: Encouraged, -Jewish Syncretism, + Christian Syncretism", modifiers=True)
    assert texts(got) == [(None, "Pilgrimage Attitude: Encouraged"), ("-", "Jewish Syncretism"),
                          ("+", "Christian Syncretism")]


def test_a_sign_with_no_name_is_refused():
    with pytest.raises(NameListError, match="no name after it"):
        parse_list("+jerusalem, -", modifiers=True)


def test_without_modifiers_a_leading_dash_is_part_of_the_name():
    assert texts(parse_list("-x, y")) == [(None, "-x"), (None, "y")]


def test_longest_groups_words_into_the_one_reading_that_resolves():
    got = parse_list("bodh gaya jerusalem iona", resolve=site, longest=True)
    assert [(i.text, i.value) for i in got] == [("bodh gaya", "bodh_gaya"), ("jerusalem", "jerusalem"), ("iona", "iona")]


def test_longest_refuses_two_readings_and_asks_for_commas():
    both = resolver(dict(SITES, bodh="bodh_town", gaya="gaya_hill"))   # "bodh gaya" and "bodh" + "gaya" both resolve
    with pytest.raises(NameListError, match="more than one way.*commas"):
        parse_list("bodh gaya", resolve=both, longest=True)
    assert [i.value for i in parse_list("bodh gaya, iona", resolve=both)] == ["bodh_gaya", "iona"]   # commas settle it


def test_longest_names_the_words_nothing_answers_to():
    with pytest.raises(NameListError, match="nothing answers to 'atlantis'"):
        parse_list("jerusalem atlantis iona", resolve=site, longest=True)


def test_longest_inside_commas_groups_each_part_and_keeps_its_sign():
    got = parse_list("+bodh gaya iona, -rome", resolve=site, longest=True, modifiers=True)
    assert [(i.sign, i.value) for i in got] == [("+", "bodh_gaya"), ("+", "iona"), ("-", "rome")]


def test_longest_without_a_resolver_is_a_programming_error():
    with pytest.raises(ValueError):
        parse_list("a b", longest=True)


@pytest.mark.parametrize("text, want", [
    ("Pilgrimage Attitude: Encouraged", ("Pilgrimage Attitude", "Encouraged")),
    ("Encouraged", (None, "Encouraged")),
    (" : x", (None, "x")),
])
def test_split_qualifier(text, want):
    assert split_qualifier(text) == want


@pytest.mark.parametrize("a, b", [("Ise Jingū", "ise_jingu"), ("Gabrán", "GabrA_n"), ("Shafi'i", "shafii"),
                                  ("Ásatrú", "asatru")])
def test_norm_makes_a_display_name_and_its_key_equal(a, b):
    assert norm(a) == norm(b)


def test_items_are_plain_values():
    assert Item("x") == Item("x", None, None)
