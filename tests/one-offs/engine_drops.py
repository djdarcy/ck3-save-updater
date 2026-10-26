"""What the engine drops on load: vassal contracts and council tasks in our output that its own re-save lacks.

Inputs: our output as loaded (kind 02) and the game's re-save of it (any kind). Ids survive a re-save, so a
missing id is a drop. For each dropped record: its parties (contract: liege, vassal; task: court_owner,
councillor and the task type), whether each party exists and is alive in the re-save, and whether it sits
above the campaign's id range (carried) or inside it. Split threshold = the first carried character id.
Also: the same counts for records the engine KEPT, so a pattern can be told from the base rate.
Usage: python -I engine_drops.py <ours.ck3> <resaved.ck3> <first-carried-character-id>
"""
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shape_diff import load  # noqa: E402
from ck3_save_migrator import gamestate as gs, translate as T  # noqa: E402

ours, res = load(sys.argv[1]), load(sys.argv[2])
split = int(sys.argv[3])


def living(g):
    b = gs.locate(g, "living")
    return set(int(x) for x in re.findall(rb"(?m)^\t*(\d+)=\{", g[b.open:b.close]))


ALIASES = {"vassal_contracts/database": ("vassal_contracts/database", "vassal_contracts/active")}


def recs(g, path):
    out = {}
    for p in ALIASES.get(path, (path,)):           # 1.8 saves keep contracts under active, 1.20 under database
        try:
            out.update({i: g[e.start:e.end] for i, e in T.entries(g, p)})
        except Exception:  # noqa: BLE001
            pass
    return out


def field(body, name):
    m = re.search(rb"[\n\t]" + name + rb"=\"?([\w.]+)", body)
    return m and m.group(1).decode()


live_res = living(res)
for path, fields in (("vassal_contracts/database", (b"liege", b"vassal")),
                     ("council_task_manager/active", (b"court_owner", b"councillor", b"type", b"position"))):
    a, b = recs(ours, path), recs(res, path)
    dropped = [i for i in a if i not in b]
    kept = [i for i in a if i in b]
    print(f"\n== {path}: ours {len(a)}, re-save {len(b)}, dropped {len(dropped)}, kept {len(kept)}")
    for label, ids in (("dropped", dropped), ("kept", kept)):
        c = Counter()
        for i in ids:
            body = a[i]
            for f in fields:
                v = field(body, f)
                if f in (b"type", b"position"):
                    if label == "dropped":
                        c[(f.decode(), v)] += 1
                    continue
                if v is None or not v.isdigit():
                    c[(f.decode(), "absent")] += 1
                    continue
                n = int(v)
                side = "carried" if (n & 0xFFFFFF) >= split else "campaign"     # the slot; generations survive
                state = "none" if n == T.NONE else ("alive" if n in live_res else "not alive in re-save")
                c[(f.decode(), side, state)] += 1
        print(f"  {label}:")
        for k, n in c.most_common(14):
            print(f"    {n:>6}  {k}")
    for i in dropped[:3]:
        print("  example dropped:", a[i][:300].decode("utf-8", "replace").replace("\n", " "))
    if path.startswith("vassal_contracts"):
        # two hypotheses: a vassal holds one contract (duplicates dropped); a contract no character points at
        per_vassal = Counter(field(a[i], b"vassal") for i in a)
        dup = Counter("vassal has 2+ contracts" if per_vassal[field(a[i], b"vassal")] > 1 else "sole contract"
                      for i in dropped)
        dupk = Counter("vassal has 2+ contracts" if per_vassal[field(a[i], b"vassal")] > 1 else "sole contract"
                       for i in kept)
        named = set(int(x) for x in re.findall(rb"\n\t+liege_contract=(\d+)", ours))
        nm = Counter("named by a character" if i in named else "named by no character" for i in dropped)
        nmk = Counter("named by a character" if i in named else "named by no character" for i in kept)
        print("  dropped:", dict(dup), dict(nm))
        print("  kept   :", dict(dupk), dict(nmk))
        print("  liege_contract= lines in ours:", len(named))
        # the realm link: one of the vassal's titles has a de facto liege title the contract's liege holds
        tit = {i: ours[e.start:min(e.end, e.start + 4096)] for i, e in T.entries(ours, "landed_titles/landed_titles")}
        holder = {i: int(m.group(1)) for i, b_ in tit.items() if (m := re.search(rb"\n\tholder=(\d+)", b_))}
        dfl = {i: int(m.group(1)) for i, b_ in tit.items() if (m := re.search(rb"\n\tde_facto_liege=(\d+)", b_))}
        held: dict[int, list[int]] = {}
        for t, h in holder.items():
            held.setdefault(h, []).append(t)

        def link(i):
            v, lg = int(field(a[i], b"vassal")), int(field(a[i], b"liege"))
            ts = held.get(v, [])
            if not ts:
                return "vassal holds no title"
            if any(holder.get(dfl.get(t)) == lg for t in ts):
                return "realm link holds"
            libs = {holder.get(dfl[t]) for t in ts if t in dfl}
            return "de facto liege is someone else" if libs - {None} else "vassal's titles have no de facto liege"
        print("  dropped:", dict(Counter(link(i) for i in dropped)))
        print("  kept   :", dict(Counter(link(i) for i in kept)))

        def lv(i):
            m = re.search(rb"levels=\{([^}]*)\}", a[i])
            return m.group(1).strip().decode() if m else "none"

        def yr(i):
            d = field(a[i], b"date")
            return "987" if d and d.startswith("987") else ("pre-987" if d else "no date")
        print("  dropped levels:", Counter(lv(i) for i in dropped).most_common(6), Counter(yr(i) for i in dropped))
        print("  kept levels   :", Counter(lv(i) for i in kept).most_common(6), Counter(yr(i) for i in kept))
        # follow-up (director 04:30): after the engine's load, is each dropped vassal still the liege's vassal?
        rt = {i: res[e.start:min(e.end, e.start + 4096)] for i, e in T.entries(res, "landed_titles/landed_titles")}
        rh = {i: int(m.group(1)) for i, b_ in rt.items() if (m := re.search(rb"\n\tholder=(\d+)", b_))}
        rd = {i: int(m.group(1)) for i, b_ in rt.items() if (m := re.search(rb"\n\tde_facto_liege=(\d+)", b_))}
        rheld: dict[int, list[int]] = {}
        for t, h in rh.items():
            rheld.setdefault(h, []).append(t)
        vas_with_contract = {field(b_, b"vassal") for b_ in b.values()}

        def after(i):
            v, lg = int(field(a[i], b"vassal")), int(field(a[i], b"liege"))
            ts = rheld.get(v, [])
            if not ts:
                state = "vassal holds no title in re-save"
            elif any(rh.get(rd.get(t)) == lg for t in ts):
                state = "still under the same liege"
            elif any(t in rd for t in ts):
                state = "under another liege"
            else:
                state = "independent (no de facto liege)"
            return state + (", has another contract" if str(v) in vas_with_contract else ", no contract")
        print("  dropped, in the re-save:", dict(Counter(after(i) for i in dropped)))
        print("  kept (control), in the re-save:", dict(Counter(after(i) for i in kept)))
        # where did the dropped vassals' titles go? (their titles in ours -> the holder in the re-save)
        where = Counter()
        tiers = Counter()
        sample = []
        for i in dropped:
            v, lg = int(field(a[i], b"vassal")), int(field(a[i], b"liege"))
            for t in held.get(v, []):
                nh = rh.get(t)
                k = "now the liege's" if nh == lg else ("unheld" if nh is None else (
                    "kept by the vassal" if nh == v else "someone else's"))
                where[k] += 1
                key = re.search(rb"\n\tkey=\"?([\w\-']+)", tit[t])
                tiers[(key.group(1)[:2].decode() if key else "?", k)] += 1
                if len(sample) < 6:
                    sample.append((key and key.group(1).decode(), v, lg, nh))
        print("  dropped vassals' titles, holder in the re-save:", dict(where))
        print("  by tier:", dict(tiers))
        print("  sample (title, vassal, liege, holder after):", sample)

if True:
    # council tasks: the same ids in and out; does the engine change who owns them?
    a, b = recs(ours, "council_task_manager/active"), recs(res, "council_task_manager/active")
    ch = Counter()
    for i in a.keys() & b.keys():
        x, y = field(a[i], b"court_owner"), field(b[i], b"court_owner")
        if x != y:
            side = "carried" if x and x.isdigit() and (int(x) & 0xFFFFFF) >= split else "campaign"
            ch[(side, "court_owner changed" if y else "court_owner removed")] += 1
    print("\n== council tasks whose owner the engine changed:", dict(ch))
