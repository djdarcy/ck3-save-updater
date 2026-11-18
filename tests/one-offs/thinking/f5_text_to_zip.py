"""F5 test tooling: a kind 00 (Text) save, as a -debug_mode console save writes it, copied as the kind 02 the game
writes with compression on (plaintext meta, then a zip of one `gamestate` member, date_time as the game's own).

The tool reads kind 00 but never writes from it (the director's ruling 2026-11-17__03-48-44: "a read-only reader for
kind 00 ... writing stays kind 02"). F5 needs `update --witness` on the loop's own re-save, which is kind 00, so this
one-off makes a kind 02 COPY for the test. It is not product code: whether `update` should accept kind 00 input is
asked of djdarcy and the Director (players with save compression off). Writes a NEW file only.
Run: python -I -X utf8 tests/one-offs/thinking/f5_text_to_zip.py <kind 00 save> <out.ck3>
"""
import io
import pathlib
import sys
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from ck3_save_migrator import savefile as sf  # noqa: E402


def main(src, dst):
    dst = pathlib.Path(dst)
    assert not dst.exists(), f"{dst} exists; this writes new files only"
    s = sf.read_save(src)
    assert s.header.kind == sf.KIND_TEXT, f"kind {s.header.kind:02x}, not 00"
    g = s.gamestate
    meta = g[:sf.meta_block_end(g)]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=sf.DEFLATE_LEVEL) as z:
        zi = zipfile.ZipInfo(filename=sf.GAMESTATE, date_time=(1980, 1, 1, 0, 0, 0))
        zi.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(zi, g, compress_type=zipfile.ZIP_DEFLATED, compresslevel=sf.DEFLATE_LEVEL)
    h = s.header
    dst.write_bytes(f"SAV{h.unknown}{sf.KIND_UNIFIED_TEXT:02x}{h.random}{len(meta):08x}".encode("ascii") + h.newline
                    + meta + buf.getvalue())
    back = sf.read_save(dst)
    assert back.header.kind == sf.KIND_UNIFIED_TEXT and back.gamestate == g
    print(f"{dst.name}: kind 02, gamestate identical ({len(g):,} bytes)")


if __name__ == "__main__":
    main(*sys.argv[1:3])
