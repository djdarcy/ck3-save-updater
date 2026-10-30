"""savediff: compare Paradox "Clausewitz" text saves by entity, not by line.

Two saves of one campaign can number the same character differently, and a gamestate is 200 MB or more, so a line
diff of two saves is the whole file. savediff compares them by what they hold: which sections exist and how many
entries each has (``shape``), which keys those entries carry and how one save's ids translate into another's
(``keys``, ``ids``), which entity points at which and whether those links hold (``graph``, with the id schema as
data in ``schema``), read from the raw text without a full parse (``text``). It never writes a save.

Any number of sides: every function takes named witnesses (``dict[str, ...]``, name -> save) and never assumes
particular names. Ids are never assumed to line up between witnesses: a translation between id spaces is always an
explicit step (``ids.offset_by_mode`` finds one, ``ids.translate`` applies it).

The survival rule: an empty result is a claim to verify. A comparison that finds no difference must still say
what it counted (the sections, the entries), so "nothing differs" can never come from "nothing was read". For
example ``shape.shape_rows`` always returns ``sections_counted``, one entry per section read.

The purity rule: this folder is vendored inside a host package until it becomes its own repository, and becoming
one must be a copy of this folder. So nothing here imports the host, the host's name appears nowhere in this
folder, every import is from the standard library or from inside this folder, and ``_VENDORED.md`` names every
file and records where each lifted piece came from. A test of the host enforces all of it.
"""
from __future__ import annotations

from . import graph, ids, keys, schema, shape, text
from .graph import (MERCENARY_TITLE_KEY, Edge, Graph, aggregate, build, cycles, dangling, duplicates, join,
                    join_diff, key_rule, offset_translator, primary_outranked)
from .ids import GEN, LOW, NONE, generation, make, offset_by_mode, slot, translate
from .keys import entry_keys, field_keys, key_gaps, scalar_map, union_keys
from .shape import Shape, shape_rows
from .text import SaveTextError, SectionIndex, locate, strip_text_header

__all__ = [
    "graph", "ids", "keys", "schema", "shape", "text",
    "MERCENARY_TITLE_KEY", "Edge", "Graph", "aggregate", "build", "cycles", "dangling", "duplicates", "join",
    "join_diff", "key_rule", "offset_translator", "primary_outranked",
    "GEN", "LOW", "NONE", "generation", "make", "offset_by_mode", "slot", "translate",
    "entry_keys", "field_keys", "key_gaps", "scalar_map", "union_keys",
    "Shape", "shape_rows",
    "SaveTextError", "SectionIndex", "locate", "strip_text_header",
]
