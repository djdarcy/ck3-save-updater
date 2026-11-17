"""Faith, rite and holy-site lookups (ck3_save_migrator/faith_lookup.py), on a small 1.20-shaped save."""

from __future__ import annotations

import pytest

from ck3_save_migrator import faith_lookup as F

G = (b'faiths={\n\tdatabase={\n'
     b'\t\t12={\n\t\t\tfaith_type=christian_faith\t\t\treligion=8\n\t\t\tmain_rite=1\n\t\t\tholy_sites={ 0 1 }\n'
     b'\t\t\teminent_holy_sites={ 0 }\n\t\t\ttag="catholic"\n\t\t\tdoctrine=special_doctrine_is_christian_faith\n'
     b'\t\t\tdoctrine=doctrine_pilgrimage_forbidden\n\t\t}\n'
     b'\t\t103={\n\t\t\tfaith_type=christian_faith\n\t\t\treligion=8\n\t\t\tmain_rite=152\n\t\t\tholy_sites={ 0 1 4 15 }\n'
     b'\t\t\teminent_holy_sites={ 0 1 }\n\t\t\ttag="dynamic_faith_103"\n\t\t\tname="Way of Scarcity"\n'
     b'\t\t\ttenet=tenet_gnosticism\n\t\t\ttenet=tenet_jewish_syncretism\n'
     b'\t\t\tdoctrine=special_doctrine_is_christian_faith\n\t\t\tdoctrine=doctrine_pilgrimage_forbidden\n\t\t}\n'
     b'\t\t50={\n\t\t\tfaith_type=sunni\n\t\t\treligion=19\n\t\t\tmain_rite=13\n\t\t\ttag="sunni"\n\t\t}\n'
     b'\t}\n}\n'
     b'rites={\n\tdatabase={\n'
     b'\t\t13={\n\t\t\trite_type=hanafi\n\t\t\tfaith=50\n\t\t\ttag="hanafi"\n\t\t\tname="Hanafi"\n\t\t}\n'
     b'\t\t16={\n\t\t\trite_type=shafii\n\t\t\tfaith=50\n\t\t\ttag="shafii"\n\t\t\tname="Shafi\'i"\n\t\t}\n'
     b'\t\t152={\n\t\t\tfaith=103\n\t\t\ttag="dynamic_rite_153"\n\t\t\tname="Way of Scarcity"\n\t\t}\n'
     b'\t}\n}\n'
     b'religion={\n\tholy_sites={\n\t\t0={\n\t\t\tholy_site_type=jerusalem\n\t\t}\n\t\t1={\n\t\t\tholy_site_type=rome\n\t\t}\n'
     b'\t\t15={\n\t\t\tbarony=12\n\t\t\tholy_site_type=iona\n\t\t}\n\t}\n}\n')


def test_a_faith_is_found_by_id_tag_or_name_ignoring_case_and_punctuation():
    for key in ("103", "dynamic_faith_103", "Way of Scarcity", "way-of-scarcity"):
        assert F.find_faith(G, key).id == "103"
    f = F.find_faith(G, "sunni")
    assert (f.id, f.religion, f.main_rite) == ("50", "19", "13")


def test_a_faith_s_fields_are_read():
    w = F.find_faith(G, "103")
    assert (w.religion, w.main_rite, w.holy_sites, w.eminent) == ("8", "152", ["0", "1", "4", "15"], ["0", "1"])
    assert w.tenets == ["tenet_gnosticism", "tenet_jewish_syncretism"]
    assert w.doctrines == ["special_doctrine_is_christian_faith", "doctrine_pilgrimage_forbidden"]


def test_a_rite_is_found_by_id_tag_name_or_rite_type_with_its_faith():
    for key in ("16", "shafii", "Shafi'i", "SHAFII"):
        r = F.find_rite(G, key)
        assert (r.id, r.faith) == ("16", "50")


def test_a_holy_site_is_found_by_id_or_type_whatever_its_key_order():
    assert F.find_holy_site(G, "iona") == "15" and F.find_holy_site(G, "0") == "0"


def test_an_unknown_name_is_refused_with_the_nearest_names():
    with pytest.raises(LookupError, match="nearest: Way of Scarcity"):
        F.find_faith(G, "Way of Scarsity")
    with pytest.raises(LookupError, match="no holy site 'constantinople'"):
        F.find_holy_site(G, "constantinople")


def test_a_name_two_entries_share_is_refused_and_the_ids_given():
    # rite 152 and faith 103 share "Way of Scarcity", but within one table a shared name must not pick one silently
    g = G.replace(b'tag="hanafi"\n\t\t\tname="Hanafi"', b'tag="hanafi"\n\t\t\tname="Shafi\'i"')
    with pytest.raises(LookupError, match=r"names 2: Shafi'i \(13\), Shafi'i \(16\); write the one you mean"):
        F.find_rite(g, "Shafi'i")


def test_religion_doctrines_are_those_every_faith_of_the_religion_carries():
    assert F.religion_doctrines(G, "8") == {"special_doctrine_is_christian_faith", "doctrine_pilgrimage_forbidden"}
    assert F.religion_doctrines(G, "99") == set()
