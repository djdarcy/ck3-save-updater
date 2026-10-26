"""Follow-up to diff_saves.py: print the same entry from BASE and LEFT for a few fields the probe flagged.

  - council_task_manager/active: one task's `type` (changed in 9,632 of 9,634): quoting, or a real change?
  - landed_titles/landed_titles: one title's `key` (changed in 12,605)
  - living: characters whose `dna` is in BASE but not in LEFT: how many, and what LEFT has instead

Usage: python -I tests/one-offs/diff_saves_sample.py <base.ck3> <left.ck3>
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402


def gamestate(path):
    raw = Path(path).read_bytes()
    if raw[:3] == b"SAV" and raw[5:7] == b"00":
        return raw[raw.index(b"\n") + 1:]
    return sf.read_save(path).gamestate


def entries(g, path):
    b = gs.locate(g, path)
    return {e.key: g[e.start:e.end] for e in gs.iter_entries(g, *b.body)}


def field(blob, name):
    m = re.search(rb"\b" + name + rb"=(\"[^\"]*\"|[^\s{}]+)", blob)
    return m.group(1) if m else None


def main():
    base, left = gamestate(sys.argv[1]), gamestate(sys.argv[2])
    for path, f in (("council_task_manager/active", b"type"), ("landed_titles/landed_titles", b"key")):
        a, b = entries(base, path), entries(left, path)
        shown = 0
        for k in a:
            if k in b and field(a[k], f) != field(b[k], f):
                print(f"{path} #{k.decode()}: {f.decode()} base={field(a[k], f)!r} left={field(b[k], f)!r}")
                shown += 1
                if shown == 3:
                    break
    a, b = entries(base, "living"), entries(left, "living")
    lost = [k for k in a if k in b and b"dna=" in a[k] and b"dna=" not in b[k]]
    print(f"\nliving: {len(lost)} characters have dna in base and none in left")
    for k in lost[:2]:
        print(f"  #{k.decode()} base head: {a[k][:400]!r}")
        print(f"  #{k.decode()} left head: {b[k][:400]!r}")
    eth = sum(1 for k in lost if b"ethnicity=" in b[k])
    print(f"  of those, with ethnicity= in left: {eth}")


if __name__ == "__main__":
    main()
