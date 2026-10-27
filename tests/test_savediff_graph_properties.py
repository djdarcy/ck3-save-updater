"""Properties of savediff's reference graph over generated gamestates (standard library only).

Each property runs over CASES seeds; a failure names its seed and prints the gamestate, so ``random.Random(seed)``
replays it. The generator writes titles with random tiers and lieges (self lieges, cycles, ``NONE`` and missing
ids included), rulers with random domains, mercenary companies with good, bad and missing titles, and regiments.
"""

from __future__ import annotations

import random

from ck3_save_migrator._vendor.savediff import graph as G

CASES = 220
NONE = 4294967295


def entry(i: int, lines: list[str]) -> str:
    return f"{i}={{\n" + "".join(f"\t{ln}\n" for ln in lines) + "}\n"


def world(rng: random.Random) -> dict:
    """A save as data: {database: {id: [lines]}}, so a test can reorder or extend it before writing it."""
    t_ids = rng.sample(range(1, 400), rng.randint(2, 14))
    c_ids = rng.sample(range(1, 400), rng.randint(1, 8))
    m_ids = rng.sample(range(1, 60), rng.randint(0, 5))
    r_ids = rng.sample(range(1, 400), rng.randint(0, 6))

    def some_title():
        return rng.choice(t_ids + [NONE, 999, rng.choice(t_ids)])

    titles = {}
    for i in t_ids:
        key = rng.choice("bcdkehx") + "_" + rng.choice(["a", "b", "x_12", "mc_7"])
        lines = [f'key={key}' if rng.random() < 0.5 else f'key="{key}"']
        for f in ("de_jure_liege", "de_facto_liege"):
            if rng.random() < 0.7:
                lines.append(f"{f}={i if rng.random() < 0.1 else some_title()}")
        if rng.random() < 0.5:
            lines.append(f"holder={rng.choice(c_ids + [NONE])}")
        titles[i] = lines
    chars = {}
    for i in c_ids:
        dom = rng.sample(t_ids, rng.randint(0, min(3, len(t_ids))))
        landed = ["landed_data={", f"\tdomain={{ {' '.join(map(str, dom))} }}", "}"] if dom else []
        chars[i] = ['first_name="R"'] + landed
    companies = {i: [f"title={some_title()}"] + ([f"regiments={{ {' '.join(map(str, r_ids))} }}"] if r_ids else [])
                 for i in m_ids}
    regiments = {i: [f"owner={rng.choice(c_ids + [NONE])}", f"size={rng.randint(1, 99)}"] for i in r_ids}
    return {"living": chars, "titles": titles, "companies": companies, "regiments": regiments}


def write(w: dict, orders: dict | None = None) -> bytes:
    orders = orders or {}

    def body(name):
        return "".join(entry(i, w[name][i]) for i in orders.get(name, list(w[name])))
    return (f"living={{\n{body('living')}}}\n"
            f"landed_titles={{\n\tlanded_titles={{\n{body('titles')}\t}}\n}}\n"
            f"mercenary_company_manager={{\n\tmercenary_companies={{\n{body('companies')}\t}}\n}}\n"
            f"armies={{\n\tregiments={{\n{body('regiments')}\t}}\n}}\n").encode()


def checks(g: bytes) -> dict:
    """Every check's result, rows put in a canonical order (a check may list rows in file order)."""
    gr = G.build(g)
    out = {"dangling": G.dangling(gr), "jure": G.cycles(gr, "de_jure_liege"), "facto": G.cycles(gr, "de_facto_liege"),
           "dup": G.duplicates(g), "primary": G.primary_outranked(gr), "mc": G.key_rule(gr, **G.MERCENARY_TITLE_KEY)}
    return {k: (sorted(map(repr, v["rows"])), v["counted"]) for k, v in out.items()}


def check(prop, name: str):
    failures = []
    for seed in range(CASES):
        try:
            prop(random.Random(seed))
        except AssertionError as e:
            failures.append(f"{name}: seed {seed}: {e}")
        if len(failures) >= 3:
            break
    assert not failures, "\n\n".join(failures)


def test_p7_permuting_database_order_never_changes_a_checks_result():
    def prop(rng):
        w = world(rng)
        g = write(w)
        orders = {name: rng.sample(list(db), len(db)) for name, db in w.items()}
        g2 = write(w, orders)
        assert checks(g) == checks(g2), f"\n{g.decode()}\n--- reordered:\n{g2.decode()}"
    check(prop, "P7")


def test_p8_adding_an_unrelated_entity_never_changes_a_join():
    def prop(rng):
        w = world(rng)
        roots = [("mercenary", i) for i in w["companies"]] + [("title", i) for i in w["titles"]]
        root = rng.choice(roots)
        depth = rng.randint(0, 4)
        before = G.join(G.build(write(w)), *root, depth)
        # a new ruler and a new title nothing reachable from the root points at; the ruler points INTO the world
        new_c = max(list(w["living"]) + [0]) + 1000
        new_t = max(list(w["titles"]) + [0]) + 1000
        reachable = {n[1] for n in before["nodes"] if n[0] == "character"}
        if new_c in reachable:
            return
        w["titles"][new_t] = ["key=c_new", f"holder={new_c}", f"de_jure_liege={rng.choice(list(w['titles']))}"]
        w["living"][new_c] = ['first_name="N"', "landed_data={",
                              f"\tdomain={{ {new_t} {rng.choice(list(w['titles']))} }}", "}"]
        g2 = write(w)
        after = G.join(G.build(g2), *root, depth)
        assert after == before, f"root {root} depth {depth}\n{g2.decode()}"
    check(prop, "P8")
