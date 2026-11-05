"""S4: did R28 cause the day-one crash of build s4 (2026-11-04 21:44, ck3+0x2166dd7 on a worker thread)?
Build the A/B pair from the S3 build, which loaded clean: s3 + R28 only (arm A) and s3 + R28 without the relations,
i.e. the modifier removal only (arm B, the control: predicted clean if the relations are the cause).
Usage: python -I r28_crash_ab.py <s3 rules.ck3> <out dir>"""
import sys
from pathlib import Path

sys.path.insert(0, r"C:\code\ck3-save-migrator")
from ck3_save_migrator import savefile as sf  # noqa: E402
from ck3_save_migrator.rules import REGISTRY, RuleContext  # noqa: E402
import ck3_save_migrator.rules.to_1_20 as m  # noqa: E402

src, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
R28 = next(r for r in REGISTRY if r.id == "R28")

a = sf.read_save(src)
print("A:", R28.run(a, RuleContext()))
sf.write_save(a, out / "r28_full.ck3", force=True)

b = sf.read_save(src)
found = m.r28_found
m.r28_found = lambda d: [(c, [], blocks) for c, _, blocks in found(d)]   # no spouses -> no relations
print("B:", R28.run(b, RuleContext()))
m.r28_found = found
sf.write_save(b, out / "r28_modifier_only.ck3", force=True)
