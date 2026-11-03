"""What ``ck3update -h`` says: where to start, then the commands grouped by what you want to do.

djdarcy, 2026-11-02: twenty commands in one flat list "could feel intimidating"; the model is ccs's "first run /
day to day" epilogue, with the commands grouped the way wtf-windows groups its own. A bare ``ck3update`` prints
START_HERE. tests/test_helptext.py fails when a command is in neither the parser nor GROUPS.
"""

DESCRIPTION = """\
Bring an old Crusader Kings III save up to the game version you have
installed. The save you give it is never changed: the updated copy is
written beside it."""

START_HERE = """\
start here:
  ck3update status              # finds your game and your save folder
  ck3update status "My Save"    # what update would do, and whether it can
  ck3update update "My Save"    # writes "My Save__updated__<game version>.ck3"

  "My Save" is a path, or a save's name in the game's save folder (with or
  without .ck3). status writes nothing. If it says REFUSED, the line under
  it says what to run."""

# (heading, [(the command as shown, the commands it covers, what it is for)])
GROUPS = [
    ("updating a save", [
        ("status", ("status",), "what update would do to a save; writes nothing"),
        ("update", ("update",), "write the updated copy beside the save"),
        ("check", ("check",), "for each patch: needed, done, or can't tell"),
    ]),
    ("when something looks wrong", [
        ("lint", ("lint",), "check an updated save before you load it in the game"),
        ("help <id>", ("help",), "what one rule, patch or pack does (ck3update help R11)"),
        ("rules", ("rules",), "list the built-in rules"),
        ("inspect", ("inspect",), "a save's versions and mods, and the game installs found"),
    ]),
    ("your own packs", [
        ("packs", ("packs",), "list your packs and whether each runs"),
        ("trust, untrust", ("trust", "untrust"), "let a pack that runs code run, or take that back"),
        ("disable, enable, disabled", ("disable", "enable", "disabled"),
         "turn a rule off or on, and list those off"),
    ]),
    ("setup", [
        ("setup", ("setup",), "'ck3update' not recognized? finds it and fixes PATH"),
        ("cache", ("cache",), "where the speed-up cache is, or clear it"),
        ("reference-mod", ("reference-mod",), "make the mod that starts a game for a reference save"),
    ]),
    ("advanced", [
        ("migrate", ("migrate",), "write a migrated copy without the plan"),
        ("gamediff", ("gamediff",), "compare two game folders"),
        ("soak", ("soak",), "STARTS THE GAME and lets a save run, to test it"),
        ("tools", ("tools",), "the standalone scripts"),
    ]),
]

FOOTER = """\
ck3update <command> -h explains one command in full.
Guide: https://github.com/djdarcy/ck3-save-updater#readme"""

BARE_FOOTER = "ck3update -h lists every command."

COLUMN = 16          # where a command's text starts, as argparse's own listing does


def grouped() -> str:
    """The commands under their headings; a name too wide for the column takes three spaces instead."""
    out = []
    for heading, rows in GROUPS:
        out.append(f"{heading}:")
        for shown, _, text in rows:
            pad = COLUMN - len(shown) if len(shown) < COLUMN - 1 else 3
            out.append(f"  {shown}{' ' * pad}{text}")
        out.append("")
    return "\n".join(out).rstrip("\n")


def covered() -> set[str]:
    """Every command some group lists."""
    return {c for _, rows in GROUPS for _, cmds, _ in rows for c in cmds}


def epilog() -> str:
    return f"{START_HERE}\n\n{grouped()}\n\n{FOOTER}"


def bare() -> str:
    """What a bare ``ck3update`` prints instead of argparse's error."""
    return f"{DESCRIPTION}\n\n{START_HERE}\n\n{BARE_FOOTER}"
