"""shots_to_webp: write a quality-90 WebP beside every PNG screenshot under a folder (the run folders' shots).

Non-destructive: the PNGs stay; a WebP that already exists is skipped. Each WebP is reopened and checked to have
the PNG's size before it counts. Removing the PNGs afterwards is a separate step, by `dz safedel`, on the
maintainer's word (2026-10-27: 580 PNGs, 3.0 GB; WebP q90 is about 7% of a PNG's size).

Usage: python -I tests/one-offs/shots_to_webp.py <folder> [--list-done <file>]
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image


def main():
    root = Path(sys.argv[1])
    done_list = Path(sys.argv[sys.argv.index("--list-done") + 1]) if "--list-done" in sys.argv else None
    pngs = sorted(p for p in root.rglob("*.png") if "shots" in p.parts or p.parent.name == "shots")
    before = after = ok = skipped = bad = 0
    done = []
    unreadable = []
    for p in pngs:
        w = p.with_suffix(".webp")
        before += p.stat().st_size
        try:
            with Image.open(p) as im:
                size = im.size
                if not w.exists():
                    im.convert("RGB").save(w, "WEBP", quality=90, method=4)
                else:
                    skipped += 1
        except (OSError, Image.UnidentifiedImageError) as e:   # e.g. a capture cut short by a machine crash
            unreadable.append(str(p))
            print(f"UNREADABLE (left as is): {p}: {e}")
            continue
        with Image.open(w) as back:
            if back.size == size:
                ok += 1
                done.append(str(p))
                after += w.stat().st_size
            else:
                bad += 1
                print(f"MISMATCH {w}: {back.size} vs {size}")
    if done_list:
        done_list.write_text("\n".join(done) + "\n", encoding="utf-8")
    print(f"pngs {len(pngs)}; webp verified {ok} (already there {skipped}); mismatched {bad}; unreadable {len(unreadable)}; "
          f"png bytes {before / 1e9:.2f} GB -> webp {after / 1e9:.2f} GB")


if __name__ == "__main__":
    main()
