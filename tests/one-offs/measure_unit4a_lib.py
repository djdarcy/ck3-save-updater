"""Helpers shared by the unit-4a probes: read the game's Clausewitz script files with the gamestate scanner."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402

REL = Path(r"E:\SteamLibrary\steamapps\common\Crusader Kings III\game\common\religion")


def strip_comments(b: bytes) -> bytes:
    """Drop '#' comments that are outside quoted strings."""
    out = []
    for line in b.split(b"\n"):
        q = False
        for i, ch in enumerate(line):
            if ch == 0x22:
                q = not q
            elif ch == 0x23 and not q:
                line = line[:i]
                break
        out.append(line)
    return b"\n".join(out)


def script_blocks(folder: Path):
    """(file name, key, data, Block) for every top-level block in folder/*.txt."""
    for f in sorted(folder.glob("*.txt")):
        data = strip_comments(f.read_bytes().lstrip(b"\xef\xbb\xbf"))
        for b in gs.iter_entries(data, 0, len(data)):
            if b.key:
                yield f.name, b.key.decode(), data, b


def val(data, block, key):
    hits = gs.find_keys(data, block, key)
    return data[hits[0].value_start:hits[0].value_end].decode().strip('"') if hits else None


def tokens_in(data, block, key):
    """Bare tokens of the first ``key={ a b c }`` list child of ``block``."""
    hits = gs.find_keys(data, block, key)
    if not hits or hits[0].block is None:
        return []
    return [data[c.start:c.end].decode().strip('"') for c in gs.iter_children(data, *hits[0].block.body) if c.key is None]
