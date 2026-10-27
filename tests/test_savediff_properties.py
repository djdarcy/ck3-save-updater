"""Properties of savediff (ck3_save_migrator/_vendor/savediff) over generated gamestates, standard library only.

Each property runs over CASES seeds of a ``random.Random``; a failure names its seed and prints the gamestate, so it
can be replayed with ``Random(seed)``. The generator writes the game's layout: tabs, closing braces on their own
lines, numeric databases with random ids, freed ``N=none`` slots, nested named blocks, anonymous list items, bare
values, quoted and unquoted scalars, and braces inside quoted strings.
"""

from __future__ import annotations

import random

from ck3_save_migrator._vendor.savediff import ids as IDS
from ck3_save_migrator._vendor.savediff import keys as K
from ck3_save_migrator._vendor.savediff import shape as S
from ck3_save_migrator._vendor.savediff import text as T

CASES = 250
NAMES = ["living", "units", "armies", "provinces", "dynasties", "variables", "misc", "ai", "wars", "secrets"]


# --------------------------------------------------------------------------- the generator
def entry(rng: random.Random, key: int) -> str:
    """A numeric database entry: scalars quoted or not, sometimes a nested block, sometimes a brace in a string."""
    lines = [f"\tflag={rng.choice(['yes', 'no'])}"]
    if rng.random() < 0.5:
        lines.append(f'\tname="{rng.choice(["a { b", "c } d", "plain", ""])}"')
    if rng.random() < 0.3:
        lines.append("\thistory={\n\t\tkey=nested\n\t\t1066.1.1=yes\n\t}")
    if rng.random() < 0.3:
        lines.append(f"\tlist={{ {' '.join(str(rng.randint(0, 99)) for _ in range(rng.randint(0, 4)))} }}")
    return f"{key}={{\n" + "\n".join(lines) + "\n}\n"


def database(rng: random.Random, n: int | None = None) -> dict:
    """A database as data: {"entries": {id: text}, "free": [ids], "tail": text}."""
    n = rng.randint(1, 12) if n is None else n
    ids = rng.sample(range(0, 5000), n + 3)
    entries = {i: entry(rng, i) for i in ids[:n]}
    free = ids[n:n + rng.randint(0, 3)]
    tail = rng.choice(["", "\tnext_id=7\n", '\tlabel="x"\n', "\t{\n\t\ta=1\n\t}\n"])
    return {"entries": entries, "free": free, "tail": tail}


def render_db(name: str, d: dict, order: list[int] | None = None) -> str:
    order = list(d["entries"]) if order is None else order
    body = "".join(d["entries"][i] for i in order) + "".join(f"{i}=none\n" for i in d["free"]) + d["tail"]
    return f"{name}={{\n{body}}}\n"


def other_section(rng: random.Random, name: str) -> str:
    """A section of named children: a nested database, scalars, anonymous items, bare values."""
    parts = []
    for c in rng.sample(["data", "list", "meta", "inner"], rng.randint(1, 3)):
        if c == "inner":
            parts.append("\tinner={\n" + "".join(f"{i}={{\n\t\tx=1\n\t}}\n" for i in rng.sample(range(99), 3))
                         + "\t}\n")
        elif c == "data":
            parts.append("\tdata={\n" + "".join("\t\t{\n\t\t\tflag=a\n\t\t}\n" for _ in range(rng.randint(0, 3)))
                         + "\t}\n")
        elif c == "list":
            parts.append(f"\tlist={{ {' '.join(str(rng.randint(0, 9)) for _ in range(rng.randint(0, 5)))} }}\n")
        else:
            parts.append('\tmeta={\n\t\tversion="1.20.1.2"\n\t\tsave_game_version=18\n\t}\n')
    parts.append(rng.choice(['\tlabel="x { y"\n', "\tcount=3\n", ""]))
    return f"{name}={{\n" + "".join(parts) + "}\n"


def gamestate(rng: random.Random) -> tuple[bytes, str, dict, list[str]]:
    """(gamestate, the database section's name, the database, the other sections' texts)."""
    names = rng.sample(NAMES, rng.randint(2, 4))
    db_name, d = names[0], database(rng)
    others = [other_section(rng, n) for n in names[1:]]
    return render(db_name, d, others), db_name, d, others


def render(db_name: str, d: dict, others: list[str], order=None) -> bytes:
    return (render_db(db_name, d, order) + "".join(others)).encode()


def check(prop, name: str):
    """Run ``prop(rng)`` for CASES seeds; collect failures with their seed and gamestate."""
    failures = []
    for seed in range(CASES):
        rng = random.Random(seed)
        try:
            prop(rng)
        except AssertionError as e:
            failures.append(f"{name}: seed {seed}: {e}")
        if len(failures) >= 3:
            break
    assert not failures, "\n\n".join(failures)


# --------------------------------------------------------------------------- P1 order
def test_p1_permuting_a_databases_entries_changes_no_count_key_or_kind():
    def prop(rng):
        g, name, d, others = gamestate(rng)
        order = list(d["entries"])
        rng.shuffle(order)
        g2 = render(name, d, others, order)
        a, b = S.shape(g)[name], S.shape(g2)[name]
        assert (a.count, a.keys, a.kinds) == (b.count, b.keys, b.kinds), f"\n{g.decode()}\n--- permuted:\n{g2.decode()}"
    check(prop, "P1")


# --------------------------------------------------------------------------- P2 additivity
def test_p2_adding_k_entries_adds_k_and_freeing_k_moves_k_to_free():
    def prop(rng):
        g, name, d, others = gamestate(rng)
        before = S.shape(g)[name]
        k = rng.randint(1, 5)
        used = set(d["entries"]) | set(d["free"])
        fresh = [i for i in rng.sample(range(5000, 9000), k) if i not in used]
        added = {**d, "entries": {**d["entries"], **{i: entry(rng, i) for i in fresh}}}
        g_add = render(name, added, others)
        after = S.shape(g_add)[name]
        assert after.count == before.count + len(fresh), f"added {fresh}:\n{g_add.decode()}"
        if len(d["entries"]) > 1:
            j = rng.randint(1, len(d["entries"]) - 1)        # keep one entry, so the section stays keyed
            gone = rng.sample(list(d["entries"]), j)
            freed = {**d, "entries": {i: t for i, t in d["entries"].items() if i not in gone},
                     "free": d["free"] + gone}
            g_free = render(name, freed, others)
            s = S.shape(g_free)[name]
            assert s.count == before.count - j, f"freed {gone}:\n{g_free.decode()}"
            assert s.kinds["free"] == before.kinds["free"] + j, f"freed {gone}:\n{g_free.decode()}"
    check(prop, "P2")


# --------------------------------------------------------------------------- P3 offset recovery
def test_p3_offset_by_mode_recovers_the_offset_and_exactly_the_shifted_keys():
    def prop(rng):
        n = rng.randint(3, 40)
        keys = [f"t_{i}" for i in range(n)]
        a = {k: IDS.make(rng.randint(0, 100_000), rng.randint(0, 3)) for k in keys}
        d = rng.randint(-50_000, 5_000_000)
        while any(not 0 <= IDS.slot(i) + d <= IDS.LOW for i in a.values()):
            d = rng.randint(0, 5_000_000)
        shifted = set(rng.sample(keys, n // 2 + 1))                       # a strict majority
        b = {}
        for k in keys:
            if k in shifted:
                b[k] = IDS.translate(a[k], d)
            elif rng.random() < 0.3:
                continue                                                   # a key b lacks
            elif rng.random() < 0.3:                                       # the same offset, another generation
                b[k] = IDS.make(IDS.slot(a[k]) + d, (IDS.generation(a[k]) + 1) % 256)
            else:                                                          # another offset (never d)
                s = rng.randint(0, IDS.LOW)
                while s - IDS.slot(a[k]) == d:
                    s = rng.randint(0, IDS.LOW)
                b[k] = IDS.make(s, IDS.generation(a[k]))
        for x in range(rng.randint(0, 5)):
            b[f"extra_{x}"] = rng.randint(0, IDS.LOW)                         # keys only b has
        state = f"a={a}\nb={b}\nd={d}"
        assert IDS.offset_by_mode(a, b) == (d, shifted), state
    check(prop, "P3")


# --------------------------------------------------------------------------- P4 round trip
def test_p4_make_and_translate_round_trip():
    def prop(rng):
        i = rng.randint(0, 0xFFFFFFFF)
        assert IDS.make(IDS.slot(i), IDS.generation(i)) == i, f"i={i:#x}"
        d = rng.randint(-IDS.slot(i), IDS.LOW - IDS.slot(i))                   # the shifted slot stays in 24 bits
        assert IDS.translate(IDS.translate(i, d), -d) == i, f"i={i:#x} d={d}"
        assert IDS.generation(IDS.translate(i, d)) == IDS.generation(i), f"i={i:#x} d={d}"
    check(prop, "P4")


# --------------------------------------------------------------------------- P5 the gap partition
def test_p5_the_two_parts_of_key_gaps_partition_want_minus_have():
    def prop(rng):
        def rs():
            return set(rng.sample(range(60), rng.randint(0, 40)))
        sets = {"have": rs(), "want": rs(), "other": rs()}
        split = rs() if rng.random() < 0.8 else None
        out = K.key_gaps(sets, have="have", want="want", split=split)
        lack = sets["want"] - sets["have"]
        inside = lack & (split or set())
        state = f"sets={sets} split={split} out={out}"
        assert out["lacking"] == len(lack), state
        assert out["in_split"]["count"] + out["rest"]["count"] == len(lack), state
        assert out["in_split"]["count"] == len(inside), state
        assert out["in_split"]["examples"] == sorted(inside)[:6], state
        assert out["rest"]["examples"] == sorted(lack - inside)[:6], state
        assert out["totals"] == {n: len(s) for n, s in sets.items()}, state
    check(prop, "P5")


# --------------------------------------------------------------------------- P6 quote style
def test_p6_quoting_or_unquoting_key_values_leaves_field_keys_unchanged():
    def prop(rng):
        n = rng.randint(1, 15)
        ids = rng.sample(range(1, 3000), n)
        keys = {i: rng.choice("bcdkeh") + "_" + "".join(rng.choice("abcxyz-'") for _ in range(rng.randint(1, 8)))
                for i in ids}
        nested = {i: rng.random() < 0.3 for i in ids}

        def g(quote) -> bytes:
            body = ""
            for i in ids:
                h = "\thistory={\n\t\tkey=old\n\t}\n" if nested[i] else ""
                v = f'"{keys[i]}"' if quote(i) else keys[i]
                body += f"{i}={{\n{h}\tkey={v}\n\tholder=3\n}}\n"
            return ("landed_titles={\n\tlanded_titles={\n" + body + "\t}\n}\n").encode()

        mixed = {i: rng.random() < 0.5 for i in ids}
        outs = [K.field_keys(x, T.SectionIndex(x), "landed_titles/landed_titles")
                for x in (g(lambda i: False), g(lambda i: True), g(lambda i: mixed[i]))]
        assert outs[0] == outs[1] == outs[2] == keys, f"keys={keys}\n{g(lambda i: mixed[i]).decode()}"
    check(prop, "P6")
