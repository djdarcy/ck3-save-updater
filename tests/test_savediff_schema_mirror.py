"""The vendored id schema (ck3_save_migrator/_vendor/savediff/schema.py) is a copy of the host's idschema.py.

savediff may not import the host, so it carries its own copy; this host-side test is what keeps the copy honest:
every table equal, and ``classify`` / ``norm_key`` giving the same answer on every path either table lists. When
the host's schema changes, this fails until the copy is updated (and _VENDORED.md says so).
"""

from __future__ import annotations

import pytest

from ck3_save_migrator import idschema as HOST
from ck3_save_migrator._vendor.savediff import schema as COPY

TABLES = ["PLAIN", "TYPED", "TRAIT", "REVIEW", "SPACES", "IDENTITY", "KIND_SPACE", "TYPE_SPACE", "FIELDS",
          "PLAIN_FIELDS"]


@pytest.mark.parametrize("name", TABLES)
def test_every_table_equals_the_hosts(name):
    assert getattr(COPY, name) == getattr(HOST, name)


def _paths():
    for kind, table in HOST.FIELDS.items():
        for path in table:
            yield kind, path
    for kind, plain in HOST.PLAIN_FIELDS.items():
        for path in plain:
            yield kind, path
    # paths no table lists, a typed identity, a "?" pattern, a family alias
    yield "living", "alive_data/inventory/equipped/weapon"
    yield "landed_titles/landed_titles", "some/new/field"
    yield "triggered_event", "scope/list/[]/identity"
    yield "dead_unprunable", "alive_data/gold/value"
    yield "nothing/here", "x"


def test_classify_agrees_on_every_listed_path():
    pairs = list(_paths())
    assert len(pairs) > 300
    differ = [(k, p, COPY.classify(k, p), HOST.classify(k, p)) for k, p in pairs
              if COPY.classify(k, p) != HOST.classify(k, p)]
    assert differ == []


NORM_CASES = [(None, True), (None, False), (b"", False), (b"123", True), (b"1066.1.1", False), (b"-5000.1.1", True),
              (b"holder", False)]


@pytest.mark.parametrize("key,is_block", NORM_CASES)
def test_norm_key_agrees(key, is_block):
    assert COPY.norm_key(key, is_block) == HOST.norm_key(key, is_block)
