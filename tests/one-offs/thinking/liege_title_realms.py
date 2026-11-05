"""#6 criterion 2, the 'link dropped' group: for each campaign title a copied county's reference liege points at,
who holds it in the updated save and whose realm that is (the top of its de facto liege chain), and whether that
is the player's realm. Decides whether Ruling 3 (drop a copied county's link to a campaign title) keeps new land
away from the player, or also from AI realms that 1.20 would give it to.
Usage: python -I liege_title_realms.py <updated .ck3> <title key> [...]"""
import re
import sys

sys.path.insert(0, r"C:\code\ck3-save-migrator\tests\one-offs\thinking")
import newmap_county_holders as H  # noqa: E402

d = H.load(sys.argv[1])
t, by_id = H.titles(d)
pp = H.people(d)
player = re.search(rb"(?m)^played_character=\{\s*name=[^\n]*\n\s*character=(\d+)", d).group(1).decode()
key_of_id = by_id
id_of_key = {v: k for k, v in by_id.items()}


def top(key):
    seen, k = set(), key
    while k and k not in seen:
        seen.add(k)
        lg = t[k][1]
        if not lg or key_of_id.get(lg) is None:
            return k
        k = key_of_id[lg]
    return k


for key in sys.argv[2:]:
    h, _ = t.get(key, (None, None))
    tp = top(key)
    th = t[tp][0]
    print(f"{key}: holder {pp.get(h)} ({h}); realm top {tp} held by {pp.get(th)} ({th})"
          f"{'  <- THE PLAYER' if th == player or h == player else ''}")
