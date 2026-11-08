"""Classify every candidate save in private/data/runs for deletion, by content (sha256), never deleting anything.

djdarcy 2026-11-07: the signed list is the only thing deleted; each file either has another copy (same sha256) that
is kept, or truly has no value (an interim test); saves that help with a crash are kept.

Candidates: .ck3 files outside crash folders. A file is listed for deletion only when one of these holds:
  dup-of-kept   its sha256 equals a file that is kept (another run's file, a crash folder, a representative copy,
                or a save in the Documents save games folder)
  test-autosave the game wrote it (autosave*, soak_autosave*, soak__autosave*, last_save*) during a run that no
                vault note cites and that met no crash (no crash dump, no crash in its timeline)
Kept, never listed: one representative per distinct guard copy (the newest), every file of a cited run, every file
of a run that met a crash, every hand-made save (other names), everything that is not a .ck3.
Writes a TSV (path, sha256, bytes, reason) to argv[1] and prints the totals.
"""
import hashlib
import re
import sys
from collections import defaultdict
from pathlib import Path

RUNS = Path(r"C:\code\ck3-save-migrator\private\data\runs")
VAULT = Path(r"C:\code\ck3-save-migrator\private\claude")
DOCS = Path.home() / "Documents" / "Paradox Interactive" / "Crusader Kings III" / "save games"
AUTOSAVE = ("autosave", "soak_autosave", "soak__autosave", "last_save")


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in VAULT.rglob("*.md"))
runs = sorted(d for d in RUNS.iterdir() if d.is_dir())


def met_a_crash(d: Path) -> bool:
    cr = d / "crashes"
    if cr.is_dir() and any(cr.iterdir()):
        return True
    tl = d / "timeline.txt"
    return tl.is_file() and re.search(r"(?i)crash", tl.read_text(encoding="utf-8", errors="replace")) is not None


cited = {d for d in runs if d.name[:20] in text}
crashed = {d for d in runs if met_a_crash(d)}

files = [(d, f) for d in runs for f in d.rglob("*.ck3")]
print(f"hashing {len(files)} run saves ...", flush=True)
digest = {f: sha(f) for _, f in files}
docs_hashes = {sha(f) for f in DOCS.glob("*.ck3")} if DOCS.is_dir() else set()

# what is kept regardless, and the representative (newest) of each distinct guard copy
kept_hashes = set(docs_hashes)
guards = defaultdict(list)
listed = []
for d, f in files:
    in_crash_folder = "crashes" in f.parts
    if f.parent.name == "autosave-guard":
        guards[digest[f]].append((d.name, f))
    elif in_crash_folder or d in cited or d in crashed or not f.name.lower().startswith(AUTOSAVE):
        kept_hashes.add(digest[f])
for h, copies in guards.items():
    copies.sort()
    kept_hashes.add(h)                                   # the newest copy of each distinct guard save stays
    for _, f in copies[:-1]:
        listed.append((f, h, "dup-of-kept (an older copy of the same guard save)"))
for d, f in files:
    if "crashes" in f.parts or f.parent.name == "autosave-guard":
        continue
    if d in cited or d in crashed or not f.name.lower().startswith(AUTOSAVE):
        continue
    h = digest[f]
    listed.append((f, h, "dup-of-kept" if h in kept_hashes else "test-autosave (uncited run, no crash)"))

with open(sys.argv[1], "w", encoding="utf-8") as out:
    out.write("path\tsha256\tbytes\treason\n")
    for f, h, why in listed:
        out.write(f"{f}\t{h}\t{f.stat().st_size}\t{why}\n")
tot = sum(f.stat().st_size for f, _, _ in listed)
by = defaultdict(lambda: [0, 0])
for f, _, why in listed:
    by[why][0] += 1
    by[why][1] += f.stat().st_size
print(f"runs {len(runs)}; cited {len(cited)}; met a crash {len(crashed)}; distinct guard saves kept {len(guards)}")
for k, (n, s) in by.items():
    print(f"  {k}: {n} files, {s / 1e9:.1f} GB")
print(f"  listed for deletion: {len(listed)} files, {tot / 1e9:.1f} GB")
