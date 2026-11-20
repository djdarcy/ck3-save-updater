"""The player's choices during an update: questions a rule asks where the game's rules leave more than one legal answer.

Designed with djdarcy on 2026-11-19 (HOLD 21:55, 22:0x, 22:4x, 22:5x; goal 2026-11-19__22-43-27, S4):

* A question is asked per province, the totals in the first prompt's header. ``a<letter>`` (``ak``, ``am``, ``ar``)
  answers this one and every remaining question of the same kind, across all building families.
* ``--auto`` answers kinds in advance: ``all`` (every kind's default), ``all=mygame`` (prefer what the campaign had),
  ``all=newgame`` (prefer what the new version's conversion set up), ``kind=answer``. Entries apply left to right and
  later wins: ``--auto all=newgame,resources=m``. A kind not named is still asked at a terminal.
* Without a terminal (a script, a pipe) every question takes its kind's default; ``--no-ask`` does the same.
* Every answer -- asked, automatic or default -- is recorded for the run's report.

One kind is registered so far, ``resources``: a province whose old resource-type building (quarries, ...) has a 1.21
resource district it could become, but whose single resource slot already holds a different district the game placed.
Its answers: ``k`` keep the game's district, ``m`` add the old building as the game's small (minor) resource building
inside that district, ``r`` replace the district (only one holding nothing but its own building). Default ``m``
(djdarcy: "Where possible when we can make a confident guess that is going to be mostly right that's the way to go").
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Kind:
    name: str
    answers: dict              # letter -> word
    default: str               # letter taken without a terminal, and by ``all``
    mygame: str                # letter for ``all=mygame``
    newgame: str               # letter for ``all=newgame``
    question: str              # the prompt's question


KINDS = {
    "resources": Kind("resources", {"k": "keep", "m": "minor", "r": "replace"}, default="m", mygame="r", newgame="k",
                      question="The slot holds another resource district. Keep it, add the minor building, or replace?"),
}


class AutoError(ValueError):
    pass


def parse_auto(specs) -> dict[str, str]:
    """``--auto`` values (each may hold commas; the option may repeat) -> kind -> answer letter. Later entries win."""
    out: dict[str, str] = {}
    for spec in specs or ():
        for item in (s.strip() for s in spec.split(",")):
            if not item:
                continue
            key, _, val = item.partition("=")
            if key == "all":
                pref = val or "default"
                if pref not in ("default", "mygame", "newgame"):
                    raise AutoError(f"all={val}: use all, all=mygame or all=newgame")
                for k in KINDS.values():
                    out[k.name] = getattr(k, pref)
                continue
            if key not in KINDS:
                raise AutoError(f"--auto {key}: no such question; the questions are: {', '.join(sorted(KINDS))}")
            kind = KINDS[key]
            letter = val if val in kind.answers else next((ltr for ltr, w in kind.answers.items() if w == val), None)
            if letter is None:
                opts = ", ".join(f"{ltr} ({w})" for ltr, w in kind.answers.items())
                raise AutoError(f"--auto {key}={val}: the answers are {opts}")
            out[key] = letter
    return out


@dataclass
class Asker:
    """Asks a kind's questions one by one, or answers them from ``--auto``, the ``a<letter>`` answers, or the default."""
    auto: dict = field(default_factory=dict)
    interactive: bool = False
    stdin: object = None
    stderr: object = None
    record: list = field(default_factory=list)        # (kind, item, letter, how): auto (--auto), asked, rest (an
    #                                                   a<letter> answer given earlier), or default (no terminal)
    _shown: set = field(default_factory=set)
    _rest: dict = field(default_factory=dict)         # kind -> letter, from an a<letter> answer at the prompt

    def ask(self, kind_name: str, item: str, header: str = "") -> str:
        kind = KINDS[kind_name]
        if kind_name in self.auto:
            return self._keep(kind_name, item, self.auto[kind_name], "auto")
        if kind_name in self._rest:
            return self._keep(kind_name, item, self._rest[kind_name], "rest")
        if not self.interactive:
            return self._keep(kind_name, item, kind.default, "default")
        err, inp = self.stderr or sys.stderr, self.stdin or sys.stdin
        if header and kind_name not in self._shown:
            err.write(header.rstrip() + "\n")
            self._shown.add(kind_name)
        letters = list(kind.answers)
        opts = "/".join(ltr.upper() if ltr == kind.default else ltr for ltr in letters)
        opts += "/" + "/".join("a" + ltr for ltr in letters) + "/?"
        while True:
            err.write(f"{item}\n{kind.question}  [{opts}] ")
            err.flush()
            try:
                a = (inp.readline() or "").strip().lower()
            except (EOFError, OSError):
                a = ""
            if a == "":
                return self._keep(kind_name, item, kind.default, "asked")
            if a in kind.answers:
                return self._keep(kind_name, item, a, "asked")
            if len(a) == 2 and a[0] == "a" and a[1] in kind.answers:
                self._rest[kind_name] = a[1]               # this one and every remaining question of this kind
                return self._keep(kind_name, item, a[1], "asked")
            err.write("  " + ", ".join(f"{ltr} = {w}" for ltr, w in kind.answers.items())
                      + "; a<letter> answers all the rest the same way\n")

    def _keep(self, kind, item, letter, how):
        self.record.append((kind, item, letter, how))
        return letter
