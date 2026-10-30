"""graph: the reference graph of a gamestate -- which entity points at which, by id -- and checks on it.

A node is an entity, ``(space, id)``: an entry of one of the databases a schema lists for that id space (the three
character sections are one space). An edge is one id-bearing field of an entry: ``(from node, field path, to
node)``, where the schema says which space the field points into. The schema is data: any object with
``SPACES`` (space -> database sections), ``TYPE_SPACE`` and ``classify(kind, path)``; the default is
``schema.py``, the host project's table.

Checks on one graph, each returning ``{"rows": [...], "counted": {...}}`` -- never a bare empty list, so "nothing
found" always says how much was looked at (the survival rule):

* ``dangling``           edges whose target is not an entity of its space (the "no id", ``NONES``, is legal);
* ``cycles``             cycles along one parent-like field (a title that is its own liege included);
* ``duplicates``         an id written under two section names of one space; a key written twice where keys are
                         unique (an id repeated under one section name is counted, not listed);
* ``primary_outranked``  rulers whose first domain title is of a lower tier than another title they hold;
* ``key_rule``           entities whose key, or the key of what they point at, breaks a stated pattern.

``join`` takes the subgraph reachable from one entity within a number of edges, as records; ``join_diff`` compares
the same subgraph in two saves through a translation of ids; ``aggregate`` sums many such diffs.
"""
from __future__ import annotations

import re
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Callable, Iterable, Iterator

from . import ids, text
from . import schema as default_schema

NONE = ids.NONE
NONES = ids.NONES
_NUM = re.compile(rb"^\d+$")
# a title key's tier, from its first letter; 1.20's hegemonies (h_) rank above empires
TIERS = {"b": 1, "c": 2, "d": 3, "k": 4, "e": 5, "h": 6}
DOMAIN = "landed_data/domain/*"
# the 1.20 game keys every mercenary company's title x_mc_<company id>
MERCENARY_TITLE_KEY = {"kind": "mercenary", "pattern": "x_mc_{id}", "via": "title"}

Node = tuple  # (space, id)


@dataclass(frozen=True)
class Edge:
    src: Node
    path: str
    dst: Node


@dataclass
class Graph:
    g: bytes
    schema: object
    loaded: set = field(default_factory=set)                 # spaces whose databases were read
    nodes: dict = field(default_factory=dict)                # node -> (section, text.Block)
    keys: dict = field(default_factory=dict)                 # node -> its depth-1 ``key=`` value
    edges: list = field(default_factory=list)                # every Edge, in file order
    out: dict = field(default_factory=dict)                  # node -> its Edges, in file order
    repeated: list = field(default_factory=list)             # (node, section) of an id already seen in its space
    unreadable: list = field(default_factory=list)           # nodes whose entry did not parse

    def section(self, node: Node) -> str | None:
        hit = self.nodes.get(node)
        return hit[0] if hit else None


# --------------------------------------------------------------------------- reading entries
def _unquote(v: bytes) -> bytes:
    return v[1:-1] if len(v) >= 2 and v[:1] == v[-1:] == b'"' else v


def _leaves(g: bytes, start: int, end: int, kind: str, schema, prefix: str = "") -> Iterator[tuple[str, bytes, str | None]]:
    """(field path, raw value, space or None) for every scalar under the body ``g[start:end]`` of an entry of
    ``kind``, depth first in file order. The numeric KEY of a child is yielded too, as ``<path>/#key``, when the
    schema says such keys are ids (``acceptance={ 12=50 }``). A typed ``identity=`` takes the space of its sibling
    ``type=``."""
    children = list(text.iter_children(g, start, end))
    typ = next((_unquote(g[c.value_start:c.value_end]).decode("utf-8", "replace")
                for c in children if c.key == b"type" and c.block is None), None)
    for c in children:
        seg = default_schema.norm_key(c.key, c.block is not None)
        path = f"{prefix}/{seg}" if prefix else seg
        if c.key is not None and c.key.isdigit():
            key_path = f"{prefix}/#key" if prefix else "#key"
            sp = schema.classify(kind, key_path)
            if sp is not None:
                yield key_path, c.key, sp
        if c.block is not None:
            yield from _leaves(g, *c.block.body, kind, schema, path)
            continue
        sp = schema.classify(kind, path)
        if sp == default_schema.TYPED:
            sp = schema.TYPE_SPACE.get(typ or "")
        yield path, _unquote(g[c.value_start:c.value_end]), sp


def _space(schema, sp) -> bool:
    return isinstance(sp, str) and sp in schema.SPACES


def build(g: bytes, index: text.SectionIndex | None = None, schema=default_schema,
          spaces: Iterable[str] | None = None) -> Graph:
    """The reference graph of ``g``. ``spaces`` limits which spaces' databases are read (all by default); edges
    into a space that was not read are kept, and the checks leave them unjudged and count them."""
    index = index or text.SectionIndex(g)
    want = set(schema.SPACES) if spaces is None else set(spaces)
    gr = Graph(g, schema)
    for space, sections in schema.SPACES.items():
        if space not in want:
            continue
        gr.loaded.add(space)
        for sec in sections:
            b = index.block(sec)
            if b is None:
                continue
            try:
                entries = [e for e in text.iter_entries(g, *b.body) if e.key and e.key.isdigit()]
            except text.SaveTextError:
                continue
            for e in entries:
                node = (space, int(e.key))
                if node in gr.nodes:
                    gr.repeated.append((node, sec))
                    continue
                gr.nodes[node] = (sec, e)
                mine = gr.out.setdefault(node, [])
                try:
                    for path, val, sp in _leaves(g, *e.body, sec, schema):
                        if path == "key" and node not in gr.keys:
                            gr.keys[node] = val.decode("utf-8", "replace")
                        if _space(schema, sp) and _NUM.match(val):
                            edge = Edge(node, path, (sp, int(val)))
                            gr.edges.append(edge)
                            mine.append(edge)
                except text.SaveTextError:
                    gr.unreadable.append(node)
    return gr


# --------------------------------------------------------------------------- checks
def dangling(gr: Graph) -> dict:
    """Edges whose target id is not an entity of its space. The game's "no id" (``NONES``: 4294967295, or
    18446744073709551615 where a field is 64 bits wide) is legal. An edge into a space that was not read is not
    judged, and counted as such."""
    rows, none, unjudged = [], 0, 0
    for e in gr.edges:
        if e.dst[1] in NONES:
            none += 1
        elif e.dst[0] not in gr.loaded:
            unjudged += 1
        elif e.dst not in gr.nodes:
            rows.append({"from": e.src, "section": gr.section(e.src), "field": e.path, "to": e.dst})
    return {"rows": rows, "counted": {"edges": len(gr.edges), "none": none, "not_judged": unjudged,
                                      "judged": len(gr.edges) - none - unjudged, "dangling": len(rows)}}


def _parents(gr: Graph, space: str, path: str) -> dict:
    parent = {}
    for node in gr.nodes:
        if node[0] != space:
            continue
        for e in gr.out.get(node, ()):
            if e.path == path and e.dst[0] == space and e.dst[1] not in NONES:
                parent[node] = e.dst
                break
    return parent


def cycles(gr: Graph, path: str, space: str = "title") -> dict:
    """Cycles along ``path`` (a parent-like field: each entity's first such edge is its parent) within ``space``;
    a self-loop is a cycle of one. Each cycle once, starting at its smallest id."""
    parent = _parents(gr, space, path)
    state: dict = {}                       # node -> 1 on the current walk, 2 done
    found = []
    for start in sorted(parent):
        walk = []
        node = start
        while node in parent and state.get(node) is None:
            state[node] = 1
            walk.append(node)
            node = parent[node]
        if state.get(node) == 1:           # closed a loop on this walk
            loop = walk[walk.index(node):]
            i = loop.index(min(loop))
            found.append(loop[i:] + loop[:i])
        for n in walk:
            state[n] = 2
    rows = [{"cycle": [n[1] for n in c], "keys": [gr.keys.get(n) for n in c]} for c in found]
    return {"rows": rows, "counted": {"entities": sum(1 for n in gr.nodes if n[0] == space),
                                      "with_parent": len(parent), "cycles": len(rows)}}


def duplicates(g: bytes, index: text.SectionIndex | None = None, schema=default_schema,
               unique_keys: Iterable[tuple[str, str]] = (("title", "key"),)) -> dict:
    """An id written more than once in one space (in one database, or across the databases of one space), and a
    depth-1 ``field=`` value written more than once where ``unique_keys`` says it is unique (title ``key=``).
    A top-level section the game writes twice is read once (its first block).

    An id written more than once under ONE section name only is a repeat, not a duplicate: 1.20 writes every
    ``dead_unprunable`` entry twice. Repeats are counted (``"<space> repeats"``: the copies beyond the first), not
    listed. An id under two different section names (``living`` and ``dead_unprunable``) is still a duplicate."""
    index = index or text.SectionIndex(g)
    rows, counted = [], Counter()
    for space, sections in schema.SPACES.items():
        seen: dict[int, list[str]] = {}
        for sec in sections:
            b = index.block(sec)
            if b is None:
                continue
            try:
                for e in text.iter_entries(g, *b.body):
                    if e.key and e.key.isdigit():
                        seen.setdefault(int(e.key), []).append(sec)
                        counted[space] += 1
            except text.SaveTextError:
                continue
        if counted[space]:
            counted[f"{space} repeats"] = sum(len(s) - 1 for s in seen.values() if len(set(s)) == 1)
        rows += [{"what": "id", "space": space, "id": i, "sections": secs} for i, secs in sorted(seen.items())
                 if len(set(secs)) > 1]
    for space, fld in unique_keys:
        byval: dict[str, list[int]] = {}
        for sec in schema.SPACES.get(space, ()):
            b = index.block(sec)
            if b is None:
                continue
            for e in text.iter_entries(g, *b.body):
                if not (e.key and e.key.isdigit()):
                    continue
                for c in text.iter_children(g, *e.body):
                    if c.key == fld.encode() and c.block is None:
                        v = _unquote(g[c.value_start:c.value_end]).decode("utf-8", "replace")
                        byval.setdefault(v, []).append(int(e.key))
                        break
        rows += [{"what": fld, "space": space, "value": v, "ids": sorted(i)} for v, i in sorted(byval.items())
                 if len(i) > 1]
        counted[f"{space} {fld}"] = sum(len(i) for i in byval.values())
    return {"rows": rows, "counted": dict(counted)}


def tier(key: str | None) -> int | None:
    """A title key's tier from its first letter (b=1 ... e=5, h=6); None for a key without one (``x_x_762``)."""
    if not key or len(key) < 2 or key[1] != "_":
        return None
    return TIERS.get(key[0])


def primary_outranked(gr: Graph) -> dict:
    """Rulers whose PRIMARY title (the first id of ``landed_data/domain``) is of a lower tier than another title in
    that domain. A primary title without a tier letter, or whose key is unknown, is not judged (counted)."""
    rows, rulers, unjudged = [], 0, 0
    for node in sorted(n for n in gr.nodes if n[0] == "character"):
        dom = [e.dst for e in gr.out.get(node, ()) if e.path == DOMAIN and e.dst[0] == "title"]
        if not dom:
            continue
        rulers += 1
        first = tier(gr.keys.get(dom[0]))
        if first is None:
            unjudged += 1
            continue
        higher = [(t[1], gr.keys.get(t), tier(gr.keys.get(t))) for t in dom[1:]
                  if (tier(gr.keys.get(t)) or 0) > first]
        if higher:
            rows.append({"character": node[1], "primary": (dom[0][1], gr.keys.get(dom[0]), first),
                         "outranked_by": higher})
    return {"rows": rows, "counted": {"rulers": rulers, "not_judged": unjudged, "outranked": len(rows)}}


def key_rule(gr: Graph, kind: str, pattern: str, via: str | None = None) -> dict:
    """Entities of space ``kind`` whose key -- or, with ``via``, the key of the entity their ``via`` field points
    at -- does not match ``pattern`` (a regular expression with ``{id}`` standing for the entity's own id).
    ``MERCENARY_TITLE_KEY`` is the first rule: a company's title is keyed ``x_mc_<company id>``."""
    rows, n = [], 0
    for node in sorted(x for x in gr.nodes if x[0] == kind):
        n += 1
        expected = pattern.format(id=node[1])
        target = node
        if via is not None:
            edge = next((e for e in gr.out.get(node, ()) if e.path == via), None)
            if edge is None:
                rows.append({"entity": node[1], "target": None, "key": None, "expected": expected, "why": f"no {via}"})
                continue
            target = edge.dst
            if target not in gr.nodes:
                rows.append({"entity": node[1], "target": target[1], "key": None, "expected": expected,
                             "why": f"{via} {target[1]} does not exist"})
                continue
        key = gr.keys.get(target)
        if key is None or not re.fullmatch(expected, key):
            rows.append({"entity": node[1], "target": target[1], "key": key, "expected": expected,
                         "why": "no key" if key is None else "key differs"})
    return {"rows": rows, "counted": {"entities": n, "broken": len(rows)}}


# --------------------------------------------------------------------------- joins
def record(gr: Graph, node: Node) -> dict | None:
    """``{field path: {"space": space or None, "values": [raw values in file order]}}`` for one entity."""
    hit = gr.nodes.get(node)
    if hit is None:
        return None
    sec, e = hit
    rec: dict = {}
    for path, val, sp in _leaves(gr.g, *e.body, sec, gr.schema):
        slot = rec.setdefault(path, {"space": sp if _space(gr.schema, sp) else None, "values": []})
        slot["values"].append(val.decode("utf-8", "replace"))
    return rec


def join(gr: Graph, kind: str, id_: int, depth: int) -> dict:
    """The subgraph reachable from ``(kind, id_)`` along edges, within ``depth`` edges: ``{"root", "depth",
    "nodes": {node: {"depth": d, "section": s, "record": record or None}}, "edges": [...]}``. A target that is
    not an entity is a node with ``record`` None; "no id" targets (``NONES``) are not followed."""
    root = (kind, id_)
    seen = {root: 0}
    queue = deque([root])
    edges = []
    while queue:
        node = queue.popleft()
        d = seen[node]
        if d >= depth:
            continue
        for e in gr.out.get(node, ()):
            if e.dst[1] in NONES:
                continue
            edges.append(e)
            if e.dst not in seen:
                seen[e.dst] = d + 1
                queue.append(e.dst)
    nodes = {n: {"depth": d, "section": gr.section(n), "record": record(gr, n)}
             for n, d in sorted(seen.items(), key=lambda x: (x[1], x[0]))}
    return {"root": root, "depth": depth, "nodes": nodes, "edges": edges}


def offset_translator(offsets: dict[str, int]) -> Callable[[str, int], int]:
    """A translation of ids from save A to save B: ``ids.translate`` by ``offsets[space]`` for the spaces listed,
    the identity elsewhere; a "no id" (``NONES``, either width) stays as it is."""
    def tr(space: str, i: int) -> int:
        return i if i in NONES or space not in offsets else ids.translate(i, offsets[space])
    return tr


def _translated(slot: dict, translate) -> list[str]:
    if slot["space"] is None:
        return slot["values"]
    return [str(translate(slot["space"], int(v))) if v.isdigit() else v for v in slot["values"]]


def join_diff(a: dict, b: dict, translate: Callable[[str, int], int]) -> dict:
    """The same subgraph in two saves, compared node by node: each node of ``a`` is paired with the node of ``b``
    its id translates to, and each field of the pair is compared after translating ``a``'s id values. Rows:
    ``how`` is "only in A" / "only in B" / "differs" for a field, "node only in A" / "node only in B" for a node."""
    rows = []
    paired_b = set()
    fields = 0
    for na, ia in a["nodes"].items():
        nb = (na[0], translate(na[0], na[1]))
        ib = b["nodes"].get(nb)
        if ib is None:
            rows.append({"kind": na[0], "a": na[1], "b": nb[1], "field": None, "how": "node only in A",
                         "value_a": None, "value_b": None})
            continue
        paired_b.add(nb)
        ra, rb = ia["record"] or {}, ib["record"] or {}
        if (ia["record"] is None) != (ib["record"] is None):
            rows.append({"kind": na[0], "a": na[1], "b": nb[1], "field": None,
                         "how": "node only in A" if ib["record"] is None else "node only in B",
                         "value_a": None, "value_b": None})
            continue
        for path in sorted(set(ra) | set(rb)):
            fields += 1
            row = {"kind": na[0], "a": na[1], "b": nb[1], "field": path}
            if path not in rb:
                rows.append({**row, "how": "only in A", "value_a": ra[path]["values"], "value_b": None})
            elif path not in ra:
                rows.append({**row, "how": "only in B", "value_a": None, "value_b": rb[path]["values"]})
            else:
                va = _translated(ra[path], translate)
                if va != rb[path]["values"]:
                    rows.append({**row, "how": "differs", "value_a": va, "value_b": rb[path]["values"]})
    for nb in b["nodes"]:
        if nb not in paired_b:
            rows.append({"kind": nb[0], "a": None, "b": nb[1], "field": None, "how": "node only in B",
                         "value_a": None, "value_b": None})
    return {"rows": rows, "counted": {"nodes_a": len(a["nodes"]), "nodes_b": len(b["nodes"]),
                                      "paired": len(paired_b), "fields_compared": fields}}


def aggregate(diffs: Iterable[dict], examples: int = 3) -> dict:
    """Many ``join_diff`` results summed by (kind, field, how): how many rows, in how many of the diffs, and the
    first few rows as examples -- so a difference every pair shares stands out."""
    by: dict = {}
    n = 0
    for d in diffs:
        n += 1
        hit_here = set()
        for r in d["rows"]:
            k = (r["kind"], r["field"], r["how"])
            slot = by.setdefault(k, {"kind": k[0], "field": k[1], "how": k[2], "rows": 0, "pairs": 0,
                                     "examples": []})
            slot["rows"] += 1
            if k not in hit_here:
                slot["pairs"] += 1
                hit_here.add(k)
            if len(slot["examples"]) < examples:
                slot["examples"].append(r)
    rows = sorted(by.values(), key=lambda s: (-s["pairs"], -s["rows"], str(s["kind"]), str(s["field"]), s["how"]))
    return {"rows": rows, "counted": {"diffs": n, "groups": len(rows)}}
