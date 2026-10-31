"""make_marker_save: a copy of a save with an unknown key written into meta_data and at the gamestate's top level.
(2026-10-30, measurement m1 for the director's unit D)

Question: does the game keep an unknown key through its own save? It decides whether an "updated by ck3update"
marker may live in the save at all. Prediction (the director's, written before the launch): the key inside meta_data
is dropped (the engine writes meta_data from its own fields); the top-level one may survive.

The meta_data block leads the gamestate and the plaintext header copy is re-derived from it on write
(savefile.CK3Save.derived_meta), so one edit to the gamestate puts the marker in both copies. The top-level key goes
right after the meta_data block. After djdarcy loads the marker save and saves it again, run with --read on the
re-save to see which of the two keys survived (and in which copy of meta_data).

Usage:
  python -I tests/one-offs/make_marker_save.py <save.ck3> <out.ck3> [--value test-2026-10-30]
  python -I tests/one-offs/make_marker_save.py --read <resaved.ck3>
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import savefile as sf  # noqa: E402

META_KEY = b"ck3update_record"
TOP_KEY = b"ck3update_record_top"


def make(src: str, out: str, value: str) -> None:
    save = sf.read_save(src)
    gs = save.gamestate
    end = sf.meta_block_end(gs)
    if META_KEY in gs[:end] or TOP_KEY in gs[end:end + 4096]:
        raise SystemExit("the source already carries a marker")
    head = gs.index(b"{") + 1                      # just inside meta_data={
    nl = b"\r\n" if gs[head:head + 2] == b"\r\n" else b"\n"
    top = TOP_KEY + b'="' + value.encode() + b'"' + nl
    save.replace_range(end, end, top)              # the later offset first, so the earlier stays valid
    save.replace_range(head, head, nl + b"\t" + META_KEY + b'="' + value.encode() + b'"')
    res = sf.write_save(save, out)
    print(f"wrote {out}: {res}")
    read(out)


def read(path: str) -> None:
    raw = Path(path).read_bytes()
    header = sf.parse_header(raw[:64])
    plain = raw[len(header.raw):len(header.raw) + header.meta_len] if header.kind != sf.KIND_TEXT else b""
    gs = sf.read_save(path).gamestate if header.kind != sf.KIND_TEXT else raw[len(header.raw):]
    end = sf.meta_block_end(gs)
    print(f"{path}: kind {header.kind}")
    print(f"  {META_KEY.decode()} in the plaintext meta : {META_KEY in plain}")
    print(f"  {META_KEY.decode()} in gamestate meta_data: {META_KEY in gs[:end]}")
    print(f"  {TOP_KEY.decode()} anywhere in the gamestate: {TOP_KEY in gs}"
          + (f" (at byte {gs.index(TOP_KEY):,})" if TOP_KEY in gs else ""))


def main() -> None:
    a = sys.argv[1:]
    if a and a[0] == "--read":
        read(a[1])
        return
    value = a[a.index("--value") + 1] if "--value" in a else "test-2026-10-30"
    make(a[0], a[1], value)


if __name__ == "__main__":
    main()
