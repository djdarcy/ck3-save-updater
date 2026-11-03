"""q8_count: did the game keep the faces of a vanilla-layout save? (Q8, the kill-check for R19's vanilla half)

djdarcy loaded MIGRATE_TEST__q8_vanilla_dna (a 1.8.1 save whose faces were translated to the vanilla layout, then
updated to 1.20.1.2 with portraits_version 5) with no mods, and saved at once as ..._resaved (2026-11-02 23:34).

Prediction (director, 2026-10-31 01:27): dna= kept on every character that had one (11,230), 0 DNA-length errors.
Fail signal: a drop toward the 99 the mods-off ladder kept.

For each save: dna= strings by length; portraits_version in meta_data and the gamestate; per character section,
entries with a face. Then, by character id: faces in the input kept in the re-save, kept byte for byte, changed,
lost; and characters with a face only in the re-save. With an error.log: its DNA lines.

Usage: python -I tests/one-offs/q8_count.py <input.ck3> <resaved.ck3> [error.log]
"""
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
from ck3_save_migrator import savefile as sf  # noqa: E402
import dna_whole_save as W  # noqa: E402

DNA_ANY = re.compile(rb'dna="([^"]*)"')
PV = re.compile(rb"(?m)^\s*portraits_version=(\d+)")


def describe(label: str, path: str) -> dict:
    s = sf.read_save(path)
    g = s.gamestate
    lens = Counter(len(m.group(1)) for m in DNA_ANY.finditer(g))
    ppl = W.people(g)
    by_sec = Counter(r["sec"] for r in ppl.values() if r["dna"])
    print(f"== {label}: {Path(path).name}")
    print(f"   dna= strings: {sum(lens.values())}, by length {dict(sorted(lens.items()))}")
    print(f"   portraits_version: meta {PV.findall(s.meta)}, gamestate {Counter(PV.findall(g))}")
    print(f"   characters with a face, by section: {dict(by_sec)} (total {sum(by_sec.values())})")
    return {cid: r["dna"] for cid, r in ppl.items() if r["dna"]}


def main():
    a = describe("input", sys.argv[1])
    b = describe("re-save", sys.argv[2])
    kept = [c for c in a if c in b]
    same = [c for c in kept if a[c] == b[c]]
    lost = [c for c in a if c not in b]
    print("== by character id")
    print(f"   faces in the input: {len(a)}; still with a face in the re-save: {len(kept)} "
          f"(byte for byte {len(same)}, changed {len(kept) - len(same)}); lost: {len(lost)}")
    print(f"   faces only in the re-save: {len([c for c in b if c not in a])}")
    if lost:
        print(f"   lost, first ids: {lost[:10]}")
    changed = [c for c in kept if a[c] != b[c]]
    if changed:
        c = changed[0]
        print(f"   first changed: {c}: {len(a[c])} -> {len(b[c])} characters")
    if len(sys.argv) > 3:
        log = Path(sys.argv[3]).read_text(encoding="utf-8", errors="replace").splitlines()
        dna = [ln for ln in log if "DNA" in ln or "dna" in ln]
        print(f"== {Path(sys.argv[3]).name}: {len(log)} lines; mentioning DNA: {len(dna)}")
        for ln in Counter(re.sub(r"^\[[^\]]*\]", "", ln)[:160] for ln in dna).most_common(8):
            print(f"   {ln[1]} x {ln[0]}")


if __name__ == "__main__":
    main()
