"""Convert a plain-text CK3 save (header kind 00, what the debug console's `save` writes) into a normal kind-02 save,
so `ck3update lint` can read it. For the 2026-11-07 re-save check (djdarcy: "Are all of the warnings fixed by loading
the save, hitting play, and then resaving"). Reads argv[1], writes argv[2]; the input is never changed.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator.savefile import meta_block_end  # noqa: E402
from tests.fixtures.make_ck3 import build_ck3  # noqa: E402

data = Path(sys.argv[1]).read_bytes()
text = data[data.index(b"\n") + 1:]                       # after the header line
end = meta_block_end(text)
Path(sys.argv[2]).write_bytes(build_ck3(meta=text[:end], body=text[end:]))
print(f"wrote {sys.argv[2]}: meta {end:,} bytes, body {len(text) - end:,} bytes")
