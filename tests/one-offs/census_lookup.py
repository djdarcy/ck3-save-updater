"""Census step 6: the character_lookup parse. translate.character_lookup reads ``(\\d+)=(\\d+)`` unanchored, so a
non-numeric history id (``han_1176=5552``, ``188854bis=22584``) is read as a numeric one (``1176`` / ``854``?) and
can overwrite the true entry. Measure, against an exact parse (key = the whole token before '='):

  * reference entries the regex parse gets wrong (overwritten or invented keys);
  * lookup entries for copied people that ours lacks, numeric vs non-numeric history id;
  * the JOIN risk: wrongly parsed reference keys that exist in the campaign's lookup (the translator joins
    characters by history id, so such a reference character would be redirected to the wrong campaign person).

Usage: python -I tests/one-offs/census_lookup.py <ref> <ours> <chain>
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shape_diff import load, characters, LOW, GEN  # noqa: E402
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import translate as T  # noqa: E402


def exact(g):
    b = gs.find_section(g, "character_lookup")
    return {k.decode(): int(v) for k, v in re.findall(rb"(?m)^\t*([^\s={}]+)=(\d+)", g[b.open + 1:b.close])}


def main():
    R, O, C = (load(p) for p in sys.argv[1:4])
    re_ref, ex_ref = T.character_lookup(R), exact(R)
    ex_ours, ex_chain = exact(O), exact(C)
    num = {k: v for k, v in ex_ref.items() if k.isdigit()}
    wrong = {int(k) for k, v in num.items() if re_ref.get(int(k)) != v}
    invented = {k for k in re_ref if str(k) not in ex_ref}
    print(f"ref lookup: {len(ex_ref)} entries ({len(num)} numeric, {len(ex_ref) - len(num)} non-numeric); "
          f"regex parse {len(re_ref)} keys: numeric keys it maps wrongly {len(wrong)}, keys it invents {len(invented)}")
    och, cch = characters(O), characters(C)
    off = 1 + max(i & LOW for i in och & cch)
    copied = {r for r in characters(R) if ((r & GEN) | ((r & LOW) + off)) in och}
    for label, keys in (("numeric", [k for k in ex_ref if k.isdigit()]),
                        ("non-numeric", [k for k in ex_ref if not k.isdigit()])):
        mine = [k for k in keys if ex_ref[k] in copied]
        lack = [k for k in mine if k not in ex_ours]
        print(f"  {label}: entries for copied people {len(mine)}, ours lacks {len(lack)}  e.g. {lack[:6]}")
    camp = set(ex_chain)                       # the campaign's history ids (the chain keeps the campaign's)
    risky = [k for k in wrong | invented if str(k) in camp]
    print(f"JOIN risk: wrongly parsed / invented ref keys that the campaign's lookup also has: {len(risky)} "
          f"e.g. {[(k, re_ref[k], ex_ref.get(str(k)), ex_chain[str(k)]) for k in risky[:5]]}")
    print("   (key, regex ref char, true ref char, campaign char): the regex ref char would be joined to the "
          "campaign char")


if __name__ == "__main__":
    main()
