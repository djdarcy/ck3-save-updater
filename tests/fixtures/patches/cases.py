"""The synthetic saves the five declarative patches (R1, R4, R5, R7, R11) are checked on.

Each case is a rule id, a meta block, a body and the ``RuleContext`` settings. The expected output of each case
(``<case>.gamestate``, and the counts and hashes in ``expected.json``) was written by the Python rules these
patches replaced, before they were removed; ``make_expected.py`` says how to write them again.
"""

from __future__ import annotations

from tests.fixtures.make_ck3 import RULES_BODY, RULES_META
from tests.fixtures.religion import OLD_BODY, OLD_META

META = (b'meta_data={\n\tsave_game_version=8\n\tversion="1.8.1"\n\tportraits_version=3\n\tgame_rules={\n'
        b'\t\tsettings={ "" "" normal_difficulty "" }\n\t\tsetting={ "" a }\n\t\tother={ "" }\n\t}\n}\n')

R1_BODY = (
    b"opinions={\n\tactive_opinions={\n"
    b"\t\t1={\n\t\t\ttemporary_opinion={\n\t\t\t\tvalue=5\n\t\t\t\tconverging={\n\t\t\t\t\ta={ 1 2 }\n\t\t\t\t}\n"
    b"\t\t\t\tdays=3\n\t\t\t}\n"
    b"\t\t\tconverging={ x=1 }\n"                                     # near miss: not inside temporary_opinion
    b"\t\t\ttemporary_opinion={ value=2 }\n"                           # near miss: nothing to delete, not counted
    b"\t\t}\n"
    b"\t\t2={\n\t\t\ttemporary_opinion={ converging=yes value=1 }\n"
    b"\t\t\ttemporary_opinion={\n\t\t\t\tconverging={ }\n\t\t\t\tconverging={ y=2 }\n\t\t\t}\n\t\t}\n"
    b"\t\t{\n\t\t\ttemporary_opinion={\n\t\t\t\tconverging={ z={ w=1 } }\n\t\t\t}\n\t\t}\n"
    b"\t}\n\ttemporary_opinion={ converging={ } }\n}\n"              # near miss: not in active_opinions
    b"misc={\n\ttemporary_opinion={\n\t\tconverging={ }\n\t}\n}\n"   # near miss: not in opinions
)

R4_BODY = (
    b'game_rules={\n\tsetting={ "" "" a }\n\tsettings={\n\t\t""\n\t\tb\n\t}\n\tlist={ "" }\n\tsetting=""\n}\n'
    b'misc={\n\tsettings={ "" }\n}\n'                                 # near miss: not under game_rules
    b'game_rules={\n\tsetting={ "" }\n}\n'                            # the top-level section a second time
)

R5_BODY = (
    b"decision_cooldowns={\n\t=-5000.1.1\n\ta=987.1.1\n\t=-5000.1.1\n}\n"
    b"interaction_cooldowns={\n\tx={\n\t\t\t=-5000.1.1\n\t\t\tb=1\n\t}\n}\n"
    b"deep={\n\ta={\n\t\tb={\n  =1\n\t\t}\n\t}\n}\n"
    b"inline={\n\tk={ =2 }\n}\n"                                        # near miss: not at line start
    b'strings={\n\tname="first\n=second"\n}\n'                        # near miss: an = at line start in a string
)

R11_BODY = (
    b"living={\n"
    b'1={\n\tmodifier={\n\t\tmodifier=""\n\t\tdays=5\n\t\tnested={ a=1 }\n\t}\n'
    b'\ttimed_modifier={\n\t\tmodifier=""\n\t}\n'
    b'\tmodifier={\n\t\tmodifier="good"\n\t}\n'                       # near miss: a named modifier
    b'\tother={\n\t\tmodifier=""\n\t}\n'                              # near miss: the parent is not a modifier
    b'\tinline={ modifier={ modifier="" } }\n'                        # near miss: not at line start
    b"}\n}\n"
    b'artifacts={\n\tartifacts={\n2={\n\t\tmodifiers={ "" a "" }\n\t\txmodifiers={ "" }\n'   # near miss: xmodifiers
    b'\t\tmodifiers={\n\t\t\t""\n\t\t}\n\t\tlist={ "" }\n\t}\n\t}\n}\n'                     # near miss: another list
    b'events={\n\tx={\n\t\ttype=""\n\t\tkind={ type="" }\n\t}\n\ttype="real"\n}\n'          # near misses: inline, named
)

AT_TARGET = b'meta_data={\n\tsave_game_version=18\n\tversion="1.20.1.2"\n}\n'

# name -> (rule id, meta, body, RuleContext keyword arguments)
CASES = {
    "R1": ("R1", META, R1_BODY, {}),
    "R4": ("R4", META, R4_BODY, {}),
    "R5": ("R5", META, R5_BODY, {}),
    "R7-no-portraits": ("R7", META, b"date=987.10.27\n", {"portraits_version": None}),
    "R7-portraits-5": ("R7", META, b"date=987.10.27\n", {"portraits_version": 5}),
    "R7-portraits-3": ("R7", META, b"date=987.10.27\n", {"portraits_version": 3}),
    "R7-at-target": ("R7", AT_TARGET, b"x={\n}\n", {}),
    "R7-another-target": ("R7", META, b"x={\n}\n", {"target_version": "1.21.0", "target_save_game_version": 19}),
    "R11": ("R11", META, R11_BODY, {}),
}
for _rid in ("R1", "R4", "R5", "R7", "R11"):
    CASES[f"rules-fixture-{_rid}"] = (_rid, RULES_META, RULES_BODY, {})
    CASES[f"religion-fixture-{_rid}"] = (_rid, OLD_META, OLD_BODY, {})


def big_gamestate(target: int = 21 * 1024 * 1024) -> bytes:
    """More than 20 MB of filler with every shape R5 and R11 edit in each section (for the speed test; its expected
    output is kept as a hash, not a file)."""
    chunk = (b"\t{\n\t\tname=\"filler entry with some text\"\n\t\tdata={ 1 2 3 4 5 6 7 8 9 10 }\n"
             b"\t\tvalue=12.5\n\t}\n") * 40
    shapes = (b'\tx={\n\t\tmodifier={\n\t\t\tmodifier=""\n\t\t}\n\t\tmodifiers={ "" a }\n\t\ttype=""\n'
              b"\t\t=-5000.1.1\n\t}\n")
    parts, size, i = [], 0, 0
    while size < target:
        part = b"sec" + str(i).encode() + b"={\n" + chunk + shapes + b"}\n"
        parts.append(part)
        size += len(part)
        i += 1
    return b"".join(parts)


BIG = ("R5", "R11")          # the two '**' patches the speed test runs on big_gamestate()
