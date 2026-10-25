"""How do the 1.8.1 save's faith templates map onto 1.20's faith_types / rite_types?

The 1.20 loader (faith_manager.cpp:396) tries to resolve each saved faith by its template key
against the current faith and rite databases and keeps the old faith only if nothing matches.
This counts how many of the save's 103 faith templates resolve as a 1.20 faith type, a rite type,
or `<key>_rite`, and lists the rest -- the candidates for a rename table.

Usage: python -I faith_key_mapping.py <gamestate> <game_dir>
"""
import re
import sys
from pathlib import Path


def keys_in(folder: Path) -> set[str]:
    out = set()
    for f in folder.glob("*.txt"):
        text = f.read_text(encoding="utf-8", errors="replace")
        text = re.sub(r"#.*", "", text)
        out |= set(re.findall(r"(?m)^([a-z_0-9]+)\s*=\s*\{", text))
    return out


def main(gamestate: str, game_dir: str) -> None:
    game = Path(game_dir) / "common" / "religion"
    faith_types = keys_in(game / "faith_types")
    rite_types = keys_in(game / "rite_types")
    religion_types = keys_in(game / "religion_types")
    data = Path(gamestate).read_bytes()
    m = re.search(rb"^religion=\{", data, re.M)
    body = data[m.end():m.end() + 400_000]
    faiths = re.findall(rb'(\d+)=\{\s*\n\s*template="([a-z_0-9]+)"', body)
    rel = [(i.decode(), t.decode()) for i, t in faiths if t.endswith(b"_religion")]
    fai = [(i.decode(), t.decode()) for i, t in faiths if not t.endswith(b"_religion")]
    print(f"1.20 faith_types={len(faith_types)} rite_types={len(rite_types)} religion_types={len(religion_types)}")
    print(f"save religions={len(rel)} faiths={len(fai)}")
    print(f"religions resolving in 1.20 religion_types: {sum(t in religion_types for _, t in rel)}/{len(rel)}; "
          f"missing: {[t for _, t in rel if t not in religion_types]}")
    as_faith = [(i, t) for i, t in fai if t in faith_types]
    as_rite = [(i, t) for i, t in fai if t not in faith_types and t in rite_types]
    as_rite_suffix = [(i, t) for i, t in fai if t not in faith_types and t not in rite_types and t + "_rite" in rite_types]
    neither = [(i, t) for i, t in fai if t not in faith_types and t not in rite_types and t + "_rite" not in rite_types]
    print(f"faiths as 1.20 faith_type : {len(as_faith)}")
    print(f"faiths as 1.20 rite_type  : {len(as_rite)}  e.g. {[t for _, t in as_rite][:12]}")
    print(f"faiths as <key>_rite      : {len(as_rite_suffix)}  {[t for _, t in as_rite_suffix]}")
    print(f"faiths matching nothing   : {len(neither)}  {[(i, t) for i, t in neither]}")
    # which of the unresolved faiths do characters actually use?
    counts = {}
    for i, t in neither + as_rite + as_rite_suffix:
        n = len(re.findall(rb"^\tfaith=" + i.encode() + rb"\n", data, re.M))
        counts[t] = n
    print("living/dead characters per unresolved-or-rite faith id (top 20):")
    for t, n in sorted(counts.items(), key=lambda kv: -kv[1])[:20]:
        print(f"   {n:>7}  {t}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
