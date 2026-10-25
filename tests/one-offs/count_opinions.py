"""Count opinion pairs and temporary-opinion modifiers in saves (what R1 kept vs removed).

Usage: python tests/one-offs/count_opinions.py <save.ck3> [<save.ck3> ...]   (run from the project root)
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

for path in sys.argv[1:]:
    d = sf.read_save(path).gamestate
    ao = gs.locate(d, "opinions/active_opinions")
    body = d[ao.open:ao.end]
    pairs = sum(1 for _ in gs.iter_entries(d, *ao.body))
    print(f"{Path(path).name}")
    print(f"  owner/target pairs   {pairs:>9,}")
    print(f"  temporary_opinion    {body.count(b'temporary_opinion={'):>9,}")
    print(f"  modifier= lines      {len(re.findall(rb'\tmodifier=', body)):>9,}")
    print(f"  value= lines         {len(re.findall(rb'\tvalue=', body)):>9,}")
    print(f"  converging blocks    {body.count(b'converging={'):>9,}")
