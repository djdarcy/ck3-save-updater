"""culture_three_way: the culture entries of up to three saves, side by side (the culture DWP's U1, first cut).

Aligns `culture_manager/cultures` entries by culture_template, else by name (cultures made in play have no
template), and compares per culture: ethos, heritage, language, martial_custom, traditions, head, the innovation
list, acceptance count, and the spread fields. Values are normalised (quotes stripped) so a change of quoting is
not counted as a change. Prints, per field, how many cultures differ between each pair, with two examples.

Usage: python -I tests/one-offs/thinking/culture_three_way.py <original.ck3> <ours.ck3> <game re-save.ck3>
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

SCALARS = ("ethos", "heritage", "language", "martial_custom", "head", "name", "culture_template",
           "fascination_marker", "exposure_marker", "spread_marker", "culture_marker", "exposure_type")


def norm(v: bytes) -> str:
    return v.strip().strip(b'"').decode("utf-8", "replace")


def load(path: str) -> bytes:
    """A normal save through read_save; a plain-text save (header kind 00, as the debug console's `save` writes it:
    the culture goal's U0) by dropping its header line (as face_check.py)."""
    raw = Path(path).read_bytes()
    if raw[:3] == b"SAV" and raw[5:7] == b"00":
        return raw[raw.index(b"\n") + 1:]
    return sf.read_save(path).gamestate


def cultures(path: str) -> dict:
    g = load(path)
    b = gs.locate(g, "culture_manager")
    sub = g[b.body[0]:b.body[1]]
    out = {}
    for m in re.finditer(rb"\n\t\t(\d+)=\{", sub):
        end = sub.find(b"\n\t\t}", m.end())
        body = sub[m.end():end]
        row = {"id": m.group(1).decode()}
        for k in SCALARS:      # a field may share its line with others (the game writes some that way)
            mm = re.search(rb"(?:^|[\s{])" + k.encode() + rb'=("[^"]*"|[^\s}]+)', body)
            row[k] = norm(mm.group(1)) if mm else None
        tr = re.search(rb"\n\t\t\ttraditions=\{([^}]*)\}", body)
        row["traditions"] = tuple(sorted(norm(x) for x in tr.group(1).split())) if tr else ()
        ci = re.search(rb"\n\t\t\tculture_innovation=\{(.*?)\n\t\t\t\}", body, re.S)
        row["innovations"] = tuple(sorted(norm(x) for x in re.findall(rb'type="?([a-z_0-9]+)', ci.group(1)))) \
            if ci else ()
        ac = re.search(rb"\n\t\t\tacceptance=\{(.*?)\n\t\t\t\}", body, re.S)
        row["acceptance_n"] = len(re.findall(rb"\d+=", ac.group(1))) if ac else 0
        key = row["culture_template"] or f"name:{row['name']}"
        out[key] = row
    return out


def main():
    names = ["original", "ours", "game"][:len(sys.argv) - 1]
    data = [cultures(p) for p in sys.argv[1:]]
    for i, n in enumerate(names):
        print(f"{n}: {len(data[i])} cultures")
    fields = list(SCALARS) + ["traditions", "innovations", "acceptance_n"]
    for a, b in [(0, 1), (1, 2), (0, 2)][:len(names) * (len(names) - 1) // 2]:
        print(f"\n== {names[a]} -> {names[b]}: only in {names[a]} {len(set(data[a]) - set(data[b]))}, "
              f"only in {names[b]} {len(set(data[b]) - set(data[a]))}")
        common = sorted(set(data[a]) & set(data[b]))
        for f in fields:
            diff = [k for k in common if data[a][k][f] != data[b][k][f]]
            if diff:
                ex = [(k, data[a][k][f], data[b][k][f]) for k in diff[:2]]
                if f == "innovations":
                    ex = [(k, sorted(set(data[a][k][f]) - set(data[b][k][f]))[:4],
                           sorted(set(data[b][k][f]) - set(data[a][k][f]))[:4]) for k in diff[:2]]
                print(f"  {f}: {len(diff)} of {len(common)} differ; e.g. {ex}")
                if f == "innovations":
                    from collections import Counter
                    lost, gained = Counter(), Counter()
                    for k in diff:
                        lost.update(set(data[a][k][f]) - set(data[b][k][f]))
                        gained.update(set(data[b][k][f]) - set(data[a][k][f]))
                    print(f"      lost (innovation: cultures): {lost.most_common(8)}")
                    print(f"      gained (innovation: cultures): {gained.most_common(8)} ... {len(gained)} kinds")


if __name__ == "__main__":
    main()
