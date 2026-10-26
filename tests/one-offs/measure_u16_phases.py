"""U16 measurement (director, 2026-10-25): where a full migrate spends its time, and whether a resident model or an
on-disk index sidecar of the save would cut it or only move it.

Runs ONE shape (faith) of the full pipeline in-process -- read, R1-R12, R15/R14/R16/R17, R7, lint, write -- with
wrappers on the functions that touch the whole gamestate, so it reports:
  (1) time per phase: read+inflate, each rule (its own time, and inside it: section-index builds, edit splices),
      lint per check, the write split into serialize+deflate / verify / atomic replace;
  (2) PASSES over the whole gamestate: section-index builds, edit splices (each rebuilds the whole bytes), lint's
      full-save scans, and the bytes copies the write makes;
  (3) per rule: parse (everything that is not the splice) vs splice;
  (4) an on-disk index cache of the INPUT, keyed by its sha256: the top-level section index plus every numbered
      database's entry offsets -- its build time, pickled size, load time, and what it could remove.

Usage: python -I tests/one-offs/measure_u16_phases.py <save.ck3> <reference.ck3> <game dir> <old game dir> <out.ck3>
"""
import hashlib
import pickle
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import lint as L  # noqa: E402
from ck3_save_migrator import rules as R  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402
from ck3_save_migrator import translate as T  # noqa: E402

acc = defaultdict(float)      # name -> seconds
cnt = defaultdict(int)        # name -> calls (passes)
current = ["setup"]


def wrap(obj, name, label, big=None):
    """Wrap obj.name; count a call as a full-gamestate pass when ``big`` says so (or always)."""
    fn = getattr(obj, name)

    def inner(*a, **k):
        t = time.perf_counter()
        try:
            return fn(*a, **k)
        finally:
            dt = time.perf_counter() - t
            acc[(current[0], label)] += dt
            if big is None or big(a, k):
                cnt[(current[0], label)] += 1
    setattr(obj, name, inner)


def is_big(a, k):
    return any(isinstance(x, (bytes, bytearray)) and len(x) > 50_000_000 for x in list(a) + list(k.values()))


def main():
    save_p, ref_p, game, old_game, out_p = sys.argv[1:6]
    wrap(gs, "_top_index", "section index build", big=lambda a, k: not any(d is a[0] for d, _ in gs._TOP_INDEX))
    wrap(gs.EditPass, "apply", "splice (whole bytes rebuilt)")
    wrap(L.SectionIndex, "__init__", "lint SectionIndex walk")
    for name in [n for n in dir(L) if n.startswith("check_")]:
        wrap(L, name, f"lint {name}")
    wrap(sf.CK3Save, "to_bytes", "serialize + deflate")
    wrap(sf, "verify_bytes", "verify (re-parse)")

    t0 = time.perf_counter()
    current[0] = "read"
    t = time.perf_counter()
    save = sf.read_save(save_p)
    acc[("read", "read + inflate")] = time.perf_counter() - t
    g_in = save.gamestate
    print(f"gamestate {len(g_in) / 1e6:.0f} MB")

    ctx = R.RuleContext(game_dir=Path(game), reference=Path(ref_p), wos_shape="faith",
                        old_game_dir=Path(old_game))
    rules = R.select("R1,R2,R3,R4,R5,R6,R11,R8,R10,R9,R12,R15,R14,R16,R7")
    rule_time = {}
    for r in rules:
        current[0] = r.id
        t = time.perf_counter()
        R.run_rules(save, [r], ctx)
        rule_time[r.id] = time.perf_counter() - t

    current[0] = "lint"
    t = time.perf_counter()
    data = L.load_game_data(Path(game), sf.read_save(ref_p).gamestate, [])
    acc[("lint", "load game data")] = time.perf_counter() - t
    t = time.perf_counter()
    L.lint_gamestate(save.gamestate, known=data)
    lint_total = time.perf_counter() - t

    current[0] = "write"
    t = time.perf_counter()
    sf.write_save(save, out_p, force=True)
    write_total = time.perf_counter() - t
    total = time.perf_counter() - t0

    # ---- report ----
    print(f"\n(1)+(3) TIME BY PHASE (total {total:.0f}s)")
    print(f"  {'phase':34} {'seconds':>8} {'index builds':>13} {'splices':>8} {'splice s':>9} {'parse s':>8}")
    print(f"  {'read + inflate':34} {acc[('read', 'read + inflate')]:8.1f}")
    for r in rules:
        ib = acc[(r.id, "section index build")]
        sp = acc[(r.id, "splice (whole bytes rebuilt)")]
        print(f"  {r.id + ' ' + r.name:34} {rule_time[r.id]:8.1f} {cnt[(r.id, 'section index build')]:>6} "
              f"{ib:5.1f}s {cnt[(r.id, 'splice (whole bytes rebuilt)')]:>8} {sp:9.1f} {rule_time[r.id] - sp:8.1f}")
    print(f"  {'lint: load game data':34} {acc[('lint', 'load game data')]:8.1f}")
    print(f"  {'lint: checks':34} {lint_total:8.1f}")
    for (ph, label), s in sorted(acc.items(), key=lambda x: -x[1]):
        if ph == "lint" and label.startswith("lint check_"):
            print(f"      {label[5:]:30} {s:8.1f}")
    print(f"  {'write (total)':34} {write_total:8.1f}")
    for label in ("serialize + deflate", "verify (re-parse)"):
        print(f"      {label:30} {acc[('write', label)]:8.1f}")

    print("\n(2) FULL-GAMESTATE PASSES")
    passes = defaultdict(int)
    for (ph, label), n in cnt.items():
        passes[label] += n
    for label, n in sorted(passes.items(), key=lambda x: -x[1]):
        print(f"  {label:34} {n:>5}")
    print("  (each splice copies the whole gamestate; each index build walks it once; lint checks scan it with "
          "regexes, at least once each)")

    print("\n(4) ON-DISK INDEX CACHE of the input (key: its sha256)")
    t = time.perf_counter()
    key = hashlib.sha256(g_in).hexdigest()
    t_sha = time.perf_counter() - t
    t = time.perf_counter()
    top = gs._top_index(g_in)
    offsets = {}
    for name, blocks in (top or {}).items():
        for b in blocks:
            try:
                ents = [(e.key, e.start, e.open, e.close) for e in gs.iter_entries(g_in, *b.body)]
            except gs.GamestateError:
                continue
            offsets[name.decode()] = ents
            for e in list(gs.iter_entries(g_in, *b.body))[:0]:
                pass
    t_build = time.perf_counter() - t
    blob = pickle.dumps({"sha": key, "top": top, "entries": offsets}, protocol=5)
    t = time.perf_counter()
    pickle.loads(blob)
    t_load = time.perf_counter() - t
    print(f"  sha256 of the input: {t_sha:.1f}s; build (top index + every section's entry offsets): {t_build:.1f}s; "
          f"pickled {len(blob) / 1e6:.1f} MB; load {t_load:.2f}s")
    first_splice = next((r.id for r in rules if cnt[(r.id, 'splice (whole bytes rebuilt)')]), None)
    print(f"  the input's offsets stay valid only until the first splice (rule {first_splice}); after it every "
          f"offset in the gamestate moves")


if __name__ == "__main__":
    main()
