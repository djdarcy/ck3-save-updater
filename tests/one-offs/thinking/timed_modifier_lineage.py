"""S4 (goal 2026-11-04 19:31): for each timed modifier 1.20 removed, trace its lineage through every game version.

For a key: the last version whose common/modifiers defines it; the scripts in that version that reference it (file and
the enclosing top-level block, usually an event id); the same block in the next version and the modifiers it uses
there; and new modifier names in the next version that look like the old one. A block that still exists and now adds
a different modifier is a successor by the game's own lineage, not by a matching effect.

Usage: python -I timed_modifier_lineage.py [key ...]   (no keys: the S4 list)"""
import difflib
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
VERS = Path(r"C:\code\ck3-save-migrator\private\data\versions")
LIVE = Path(r"E:\SteamLibrary\steamapps\common\Crusader Kings III")
ORDER = ["1.7.2", "1.8.2", "1.9.2", "1.10.2", "1.11.5", "1.12.5", "1.13.2", "1.14.3", "1.15.0", "1.16.2",
         "1.17.1", "1.18.4", "1.19.0", "1.20.0"]
KEYS = """rejected_from_marriage_bed_modifier county_weapons_ban_in_city_modifier imprisoned_frontier_hero_modifier
pilgrimage_foreign_guards_modifier pilgrimage_completely_lost_modifier hold_court_7040_tax_cut
hold_court_7040_county_opinion_loss contained_dance_plague_modifier 6200_menacing_wilderness_county_modifier
smelly_court_roco_modifier rice_fields_modifier house_feud_story_modifier 6200_plagued_by_beasts_county_modifier
6200_freed_by_beasts_county_modifier spying_holes_modifier inhospitable_court honored_frontier_hero_modifier
hold_court_8030_settled_character_modifier hold_court_8030_favored_modifier hold_court_8030_duel_modifier
hold_court_7040_tax_boost hold_court_7030_knight_punished hidden_escape_route_modifier feast_archers_insight_modifier
failed_deception_modifier court_6080_cultural_hostility_modifier county_weapons_carried_in_city_modifier""".split()

_cache: dict = {}


def game(v):
    return (LIVE if v == "live" else VERS / v) / "game"


def texts(v, sub):
    k = (v, sub)
    if k not in _cache:
        out = {}
        root = game(v) / sub
        if root.is_dir():
            for p in root.rglob("*.txt"):
                try:
                    out[p.relative_to(game(v)).as_posix()] = p.read_text(encoding="utf-8-sig", errors="replace")
                except OSError:
                    pass
        _cache[k] = out
    return _cache[k]


def modifier_keys(v):
    keys = set()
    for t in texts(v, "common/modifiers").values():
        keys.update(re.findall(r"(?m)^([A-Za-z0-9_]+)\s*=\s*\{", t))
    return keys


def script_files(v):
    files = {}
    for sub in ("events", "common/scripted_effects", "common/court_positions", "common/activities",
                "common/story_cycles", "common/decisions", "common/on_action", "common/schemes",
                "common/character_interactions", "common/scripted_triggers"):
        files.update(texts(v, sub))
    return files


def block_at(text, pos):
    """The top-level block (a line at column 0 opening a brace) that contains pos."""
    starts = [m for m in re.finditer(r"(?m)^([A-Za-z0-9_.]+)\s*=\s*\{", text) if m.start() <= pos]
    return starts[-1].group(1) if starts else None


def block_body(text, name):
    m = re.search(r"(?m)^" + re.escape(name) + r"\s*=\s*\{", text)
    if not m:
        return None
    depth, i = 0, m.end() - 1
    while i < len(text):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[m.start():i + 1]
        elif c == "#":
            j = text.find("\n", i)
            i = j if j >= 0 else len(text)
            continue
        i += 1
    return text[m.start():]


def strip_comments(t):
    return re.sub(r"#[^\n]*", "", t)


def main():
    keys = sys.argv[1:] or KEYS
    vers = ORDER + ["live"]
    defs = {v: modifier_keys(v) for v in vers}
    for key in keys:
        present = [v for v in vers if key in defs[v]]
        print(f"\n== {key}")
        if not present:
            print("   defined in no vanilla version (a mod's)")
            continue
        last = present[-1]
        nxt = vers[vers.index(last) + 1] if last != "live" else None
        print(f"   defined {present[0]} .. {last}; gone in {nxt}")
        if not nxt:
            continue
        old_files, new_files = script_files(last), script_files(nxt)
        blocks = []
        for rel, t in old_files.items():
            for m in re.finditer(r"\b" + re.escape(key) + r"\b", strip_comments(t)):
                b = block_at(strip_comments(t), m.start())
                if b and (rel, b) not in blocks:
                    blocks.append((rel, b))
        if not blocks:
            print(f"   no script in {last} references it")
        for rel, b in blocks[:6]:
            body_new = None
            for t in new_files.values():
                body_new = block_body(strip_comments(t), b)
                if body_new:
                    break
            if body_new is None:
                print(f"   {last} {rel} :: {b} -> block gone in {nxt}")
                continue
            used = sorted(set(re.findall(r"modifier\s*=\s*\"?([A-Za-z0-9_]+)", body_new)) & defs[nxt])
            fresh = [u for u in used if u not in defs[last]]
            print(f"   {last} {rel} :: {b} -> in {nxt} uses {used[:8]}  NEW: {fresh}")
        new_names = sorted(defs[nxt] - defs[last])
        close = difflib.get_close_matches(key, new_names, n=4, cutoff=0.6)
        if close:
            print(f"   similar new names in {nxt}: {close}")


if __name__ == "__main__":
    main()
