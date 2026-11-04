"""Faces (R19): a character's DNA from the layout it was written in to the layout the player will load with.

A face is the ``dna="<base64>"`` string in a character's entry: a run of 4-byte places, one per gene, in the order
the game's ``common/genes`` files define (the layout). Bytes 0 and 2 are the dominant and recessive template, 1
and 3 their values. When the game version or the portrait mods change, the layout changes; the new game rejects a
string in the old layout ("Unexpected DNA string length") and makes up a new face. R19 rewrites every string from
its source layout to the target's, gene by gene and template by template BY NAME, and stamps the target's
``portraits_version``, so the game keeps the faces.

Ported from the prototype (tests/one-offs/dna_layout.py, dna_translate.py, dna_whole_save.py), measured on the
founding save on 2026-10-25:

- gene order is file-name order across all the gene folders, then declaration order inside a file (11,226 strings
  fit with 0 impossible places; the category-grouped order left 7). Genes carry no usable index; templates do;
- a file in a later folder with the same name replaces the earlier file whole; a later gene of the same name
  replaces the earlier one; ``special_genes`` are not stored in DNA;
- vanilla 1.8.2 and vanilla 1.20 have the same 104 genes in the same places (556 base64 characters both), so a
  string's length never tells which layout it was written in: the source is decided per character (its save, or
  the reference for a character the transplant added), and the length is only the check.
"""

from __future__ import annotations

import base64
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from . import gamestate as gs

CATS = ("color_genes", "morph_genes", "accessory_genes")
SECTIONS = ("living", "dead_unprunable", "characters/dead_prunable")
DEFAULT_PLACE = bytes([0, 128, 0, 128])         # a target gene the source lacks: template 0, the middle value
_DNA_ANY = re.compile(rb'dna="([^"]*)"')
_FIRST_INDENT = re.compile(rb"[^\n]*\n(\t*)")
_PV = re.compile(rb"(?m)^(\t*portraits_version=)(\d+)")
_MOD_LIST = re.compile(rb'"(mod/[^"]+\.mod)"')
_PATH_LINE = re.compile(r'(?m)^\s*(path|archive)\s*=\s*"([^"]*)"')


# --------------------------------------------------------------------------- the genes files (the prototype's parser)
def tokens(text: str) -> list[str]:
    text = re.sub(r"#[^\n]*", "", text)
    return re.findall(r'"[^"]*"|[{}=]|[^\s{}="]+', text)


def parse(tok: list[str], i: int = 0) -> tuple[list, int]:
    """A block body as a list of (key, value); a value is a list (a block) or a string."""
    out = []
    while i < len(tok):
        t = tok[i]
        if t == "}":
            return out, i + 1
        if i + 1 < len(tok) and tok[i + 1] == "=":
            v = tok[i + 2] if i + 2 < len(tok) else ""
            if v == "{":
                val, i = parse(tok, i + 3)
            else:
                val, i = v, i + 3
            out.append((t, val))
        elif t == "{":
            val, i = parse(tok, i + 1)
            out.append((None, val))
        else:
            out.append((None, t))
            i += 1
    return out, i


def genes_dir(d: Path) -> Path:
    d = Path(d)
    return d if d.name == "genes" else d / "common" / "genes"


def has_genes(d: Path) -> bool:
    g = genes_dir(d)
    return g.is_dir() and any(g.glob("*.txt"))


def load_genes(spec: list[tuple[str, Path]]) -> dict[str, dict]:
    """Every gene the folders define, in load order (vanilla first): a later file of the same name replaces the
    earlier file whole, a later gene of the same name replaces the earlier gene."""
    files: dict[str, tuple[str, Path]] = {}
    for label, d in spec:
        g = genes_dir(d)
        if g.is_dir():
            for f in sorted(g.glob("*.txt")):
                files[f.name] = (label, f)
    genes: dict[str, dict] = {}
    for fname in sorted(files):
        label, f = files[fname]
        body, _ = parse(tokens(f.read_text(encoding="utf-8-sig", errors="replace")))
        for key, val in body:
            if key == "special_genes" and isinstance(val, list):
                blocks = [(k, v, True) for k, v in val if k in CATS]
            elif key in CATS:
                blocks = [(key, val, False)]
            else:
                continue
            for cat, blk, special in blocks:
                if not isinstance(blk, list):
                    continue
                for gname, gval in blk:
                    if not isinstance(gval, list) or gname is None:
                        continue
                    tidx_by_name = {k: int(vv) for k, v in gval if isinstance(v, list) and k is not None
                                    for kk, vv in v if kk == "index" and isinstance(vv, str) and vv.isdigit()}
                    genes.pop(gname, None)                       # a redefinition takes the later place
                    genes[gname] = {"name": gname, "cat": ("special " if special else "") + cat,
                                    "tidx_by_name": tidx_by_name, "src": label, "file": fname, "order": len(genes)}
    return genes


def dna_order(genes: dict[str, dict]) -> list[dict]:
    """The genes stored in DNA (special genes are not), in DNA order: file name, then declaration in the file."""
    ns = [g for g in genes.values() if not g["cat"].startswith("special")]
    ns.sort(key=lambda g: (g["file"], g["order"]))
    return ns


def chars(places: int) -> int:
    """The base64 length of a DNA string of ``places`` 4-byte places."""
    return -(-4 * places // 3) * 4


@dataclass
class Layout:
    """A DNA layout: the folders it is built from (label, folder), and its genes in DNA order."""
    name: str
    spec: list
    genes: list

    @property
    def places(self) -> int:
        return len(self.genes)

    @property
    def length(self) -> int:
        return chars(self.places)

    def describe(self) -> dict:
        return {"name": self.name, "folders": [{"label": label, "folder": str(d)} for label, d in self.spec],
                "genes": self.places, "dna_characters": self.length}


def build_layout(name: str, spec: list[tuple[str, Path]]) -> Layout:
    return Layout(name, list(spec), dna_order(load_genes(spec)))


# --------------------------------------------------------------------------- the translation (the prototype's plan)
@dataclass
class Plan:
    """How one source layout's places become the target's: per target place, the source place (None: defaulted)
    and the template map (None: a colour gene, copied whole)."""
    source: Layout
    target: Layout
    moves: list = field(default_factory=list)
    kept: int = 0
    remapped: int = 0
    defaulted: list = field(default_factory=list)
    dropped: list = field(default_factory=list)
    templates_lost: int = 0
    moved: int = 0
    renamed: list = field(default_factory=list)        # source genes carried under a new name (RENAMES)

    @property
    def identity(self) -> bool:
        return (self.source.places == self.target.places and not self.defaulted and not self.dropped
                and all(sp == p and (t is None or all(k == v for k, v in t.items())) for p, sp, t in self.moves)
                and self.remapped == 0)

    def apply(self, dna: bytes, impossible: Counter | None = None) -> bytes:
        """``impossible``: counts, by gene, the template bytes the source gene defines no template for (a template
        index past its highest): the sign that the source layout is not the one the face was written in."""
        out = bytearray()
        for _, sp, tmap in self.moves:
            if sp is None:
                out += DEFAULT_PLACE
                continue
            b = dna[sp * 4: sp * 4 + 4]
            if len(b) < 4:
                out += DEFAULT_PLACE
                continue
            if tmap is not None:
                if impossible is not None:
                    g = self.source.genes[sp]
                    top = max(g["tidx_by_name"].values(), default=None)
                    n = (b[0] > top) + (b[2] > top) if top is not None else 0
                    if n:
                        impossible[g["name"]] += n
                b = bytes([tmap.get(b[0], 0), b[1], tmap.get(b[2], 0), b[3]])
            out += b
        return bytes(out)

    def counts(self) -> dict:
        return {"source": self.source.name, "target": self.target.name, "kept": self.kept, "remapped": self.remapped,
                "moved": self.moved,
                "defaulted": self.defaulted, "dropped": self.dropped, "templates_lost": self.templates_lost,
                "renamed": self.renamed}


# Genes renamed between portrait-mod builds: old name -> new name, each with the measurement that shows it is the
# same control (both move the same blendshapes, and the target keeps the old template names). Applied only with
# --face-changes renames, and only when the source lacks the new name and the target lacks the old one.
RENAMES = {
    # EPE 1.6.0's gene moves "bs_head_round_shape"; today's EPE moves it from gene_bs_head_shape, whose templates
    # keep the old names vanilla_head_round_shape / head_round_shape (2026-11-03, tests/one-offs/gene_cousins.py)
    "gene_bs_head_round_shape": "gene_bs_head_shape",
}


def build_plan(source: Layout, target: Layout, renames: dict | None = None) -> Plan:
    plan = Plan(source, target)
    pos = {g["name"]: i for i, g in enumerate(source.genes)}
    tnames = {g["name"] for g in target.genes}
    renamed_to = {new: old for old, new in (renames or {}).items()
                  if old in pos and new not in pos and old not in tnames}
    plan.renamed = sorted(renamed_to.values())
    for p, g in enumerate(target.genes):
        sp = pos.get(g["name"])
        if sp is None and g["name"] in renamed_to:
            sp = pos[renamed_to[g["name"]]]
        if sp is None:
            plan.defaulted.append(g["name"])
            plan.moves.append((p, None, None))
            continue
        s = source.genes[sp]
        if g["cat"] == "color_genes":
            plan.moves.append((p, sp, None))
            plan.kept += 1
            plan.moved += sp != p
            continue
        smap, dmap = s["tidx_by_name"], g["tidx_by_name"]
        tmap = {}
        for tname, si in smap.items():
            if tname in dmap:
                tmap[si] = dmap[tname]
            else:
                plan.templates_lost += 1
        plan.moved += sp != p
        if len(tmap) == len(smap) and all(k == v for k, v in tmap.items()):
            plan.kept += 1
        else:
            plan.remapped += 1
        plan.moves.append((p, sp, tmap))
    names = {g["name"] for g in target.genes}
    plan.dropped = [g["name"] for g in source.genes if g["name"] not in names and g["name"] not in plan.renamed]
    return plan


def b64d(s: bytes) -> bytes:
    return base64.b64decode(s + b"=" * (-len(s) % 4))


def translate(s: bytes, plan: Plan, impossible: Counter | None = None) -> tuple[bytes, str, int]:
    """(the new string, its outcome, the places dropped). The source layout is decided per character; the length
    only checks it:

    - at the source layout's length: translated ("kept" when the same bytes come out);
    - at the target layout's length (and not the source's): "already target", left as it is;
    - longer than the source layout: the places past it are dropped (counted), the rest translated;
    - shorter: "left as is: shorter than its layout"."""
    src_len, dst_len = plan.source.length, plan.target.length
    if len(s) == dst_len and len(s) != src_len:
        return s, "already target", 0
    if len(s) < src_len:
        return s, "left as is: shorter than its layout", 0
    raw = b64d(s)
    extra = max(0, len(raw) // 4 - plan.source.places) if len(s) != src_len else 0
    applied = plan.apply(raw[:4 * plan.source.places], impossible)          # counts even an identity
    new = s if plan.identity and not extra else base64.b64encode(applied)
    return new, ("kept" if new == s else "translated"), extra


# --------------------------------------------------------------------------- which layouts: the setup
def user_dir() -> Path | None:
    """The game's user folder (where ``save games``, ``mod`` and ``dlc_load.json`` are)."""
    from . import discover
    sg = discover.save_games_dir()
    return Path(sg).parent if sg is not None else None


def resolve_mod(entry: str, user: Path | None, game_dir: Path | None) -> Path | None:
    """A launcher entry (``mod/ugc_2220098919.mod``, ``mod/zz_ref_987_10_27.mod``) to its mod folder: through its
    ``.mod`` descriptor's ``path`` in the user folder, else (a Workshop id) the Workshop folder."""
    if user is not None:
        desc = user / entry
        if desc.is_file():
            m = next((m for m in _PATH_LINE.finditer(desc.read_text(encoding="utf-8-sig", errors="replace"))
                      if m.group(1) == "path"), None)
            if m:
                p = Path(m.group(2))
                return p if p.is_absolute() else user / p
    w = re.fullmatch(r"mod/ugc_(\d+)\.mod", entry)
    if w and game_dir is not None:
        from .discover import workshop_content_dir
        d = workshop_content_dir(game_dir) / w.group(1)
        return d if d.is_dir() else None
    return None


def portrait_mods(entries: list[str], user: Path | None, game_dir: Path | None) -> tuple[list, list[str]]:
    """The entries that resolve to a folder shipping ``common/genes`` (label, folder), in their order, and the
    entries that could not be found."""
    found, missing = [], []
    for e in entries:
        d = resolve_mod(e, user, game_dir)
        if d is None or not d.is_dir():
            missing.append(e)
        elif has_genes(d):
            found.append((Path(e).stem, d))
    return found, missing


def read_dlc_load(user: Path | None) -> list[str] | None:
    """The launcher's enabled mods, in load order, from ``dlc_load.json``; None when there is no such file."""
    f = user / "dlc_load.json" if user is not None else None
    if f is None or not f.is_file():
        return None
    try:
        data = json.loads(f.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    return [str(x) for x in data.get("enabled_mods", []) if isinstance(x, str)]


def mods_listed(meta: bytes) -> list[str]:
    return [m.decode("utf-8", "replace") for m in _MOD_LIST.findall(meta)]


def resolve_given(x: str, game_dir: Path | None) -> Path | None:
    """A ``--portrait-mods`` / ``--old-portrait-mods`` entry: a Workshop id (an installed Workshop mod) or a folder;
    None when it is neither."""
    from .discover import workshop_content_dir
    x = x.strip()
    if x.isdigit() and game_dir is not None:
        d = workshop_content_dir(game_dir) / x
        if d.is_dir():
            return d
    d = Path(x)
    return d if d.is_dir() else None


def unresolved(given: list[str], game_dir: Path | None) -> list[str]:
    """The entries that name no installed mod and no folder (the plan refuses them)."""
    return [x for x in given if x.strip() and resolve_given(x, game_dir) is None]


def override_mods(given: list[str], game_dir: Path | None) -> tuple[list, list[str]]:
    """``--portrait-mods``: Workshop ids or folders, in that order (empty: vanilla)."""
    from .discover import workshop_content_dir
    found, missing = [], []
    for x in given:
        x = x.strip()
        if not x:
            continue
        d = (workshop_content_dir(game_dir) / x) if x.isdigit() and game_dir is not None else Path(x)
        if d.is_dir() and has_genes(d):
            found.append((d.name, d))
        else:
            missing.append(x)
    return found, missing


def portraits_version_table() -> dict[str, int]:
    """The built-in pack's table: the target's portraits_version by the game's version line."""
    from .patches.model import tomllib
    f = Path(__file__).parent / "packs" / "to_1_20" / "R19-dna-layout" / "portraits_version.toml"
    if not f.is_file():
        return {}
    return {str(k): int(v) for k, v in tomllib.loads(f.read_text(encoding="utf-8")).get("lines", {}).items()}


@dataclass
class Setup:
    """The layouts R19 translates between, and the portraits_version it stamps, with what each was read from."""
    source: Layout
    target: Layout
    reference: Layout | None = None             # the layout of the characters the transplant added
    portraits_version: int | None = None
    portraits_why: str = ""
    notes: list[str] = field(default_factory=list)
    target_from: str = ""
    source_mods: list = field(default_factory=list)   # (mod, where it came from) per source mod
    face_changes: tuple = ()                    # --face-changes: the named changes beyond 0.4.0's R19 ("renames")

    def plans(self) -> tuple[Plan, Plan | None]:
        if "_plans" not in self.__dict__:
            ren = RENAMES if "renames" in self.face_changes else None
            self.__dict__["_plans"] = (build_plan(self.source, self.target, ren),
                                       build_plan(self.reference, self.target, ren) if self.reference else None)
        return self.__dict__["_plans"]

    def describe(self) -> dict:
        return {"source": self.source.describe(), "target": self.target.describe(),
                "reference": self.reference.describe() if self.reference else None,
                "target_from": self.target_from, "source_mods": [{"mod": m, "from": f} for m, f in self.source_mods],
                "portraits_version": self.portraits_version,
                "portraits_version_from": self.portraits_why, "notes": list(self.notes)}


def target_layout(game_dir: Path | None, portrait_mods_given: list[str] | None = None,
                  user: Path | None = None) -> tuple[Layout, str, list[str]]:
    """The layout the player will load with: the installed game's genes plus the gene-shipping mods the launcher
    enables (``dlc_load.json``, in load order), or ``--portrait-mods`` (empty: vanilla). (layout, where the mods
    came from, notes)."""
    user = user if user is not None else user_dir()
    notes: list[str] = []
    game = [("vanilla", Path(game_dir))] if game_dir else []
    if portrait_mods_given is not None:
        mods, missing = override_mods(portrait_mods_given, game_dir)
        came = "--portrait-mods" if portrait_mods_given else "--portrait-mods (empty: vanilla)"
        notes += [f"--portrait-mods names {m}, which is not a folder with common/genes; left out" for m in missing]
    else:
        enabled = read_dlc_load(user)
        if enabled is None:
            mods, came = [], "no dlc_load.json found: vanilla"
        else:
            mods, missing = portrait_mods(enabled, user, game_dir)
            came = f"the launcher's dlc_load.json ({len(enabled)} enabled mod(s))"
            notes += [f"dlc_load.json enables {m}, which is not found: left out of the target layout" for m in missing]
    name = "the target's" + (f" (+ {', '.join(n for n, _ in mods)})" if mods else " (vanilla)")
    return build_layout(name, game + mods), came, notes


def _line(v: str | None) -> str | None:
    from .discover import parse_version
    pv = parse_version(v)
    return ".".join(str(x) for x in pv[:2]) if pv and len(pv) >= 2 else None


def setup(*, save_meta: bytes, game_dir: Path | None, old_game_dir: Path | None = None,
          reference_meta: bytes | None = None, portrait_mods_given: list[str] | None = None,
          target_version: str | None = None, user: Path | None = None,
          old_portrait_mods: list[str] | None = None) -> Setup:
    """The source, reference and target layouts and the target's portraits_version, each said where it came from.

    Source: the save's own vanilla genes (``old_game_dir``, else the installed game's, assumed) plus the portrait
    mods its mods list names (today's installed builds). Reference: the installed game plus the reference save's
    listed portrait mods. Target: the installed game plus the launcher's enabled gene-shipping mods
    (``dlc_load.json``), or ``portrait_mods_given`` (empty: vanilla). portraits_version: the reference save's own,
    else the built-in table by the game's version line. ``old_portrait_mods`` (``--old-portrait-mods``) replaces the
    save's listed mods for the source layout, in the order given (empty: vanilla): the save's own builds, when the
    installed ones have changed or gone. It speaks for the save's own characters only."""
    from .discover import save_versions
    user = user if user is not None else user_dir()
    notes = []
    vanilla = Path(old_game_dir) if old_game_dir else (Path(game_dir) if game_dir else None)
    sv = save_versions(save_meta)["version"]
    if not old_game_dir and vanilla is not None:
        notes.append(f"the save's own vanilla genes are taken from the installed game (no --old-game-dir): its "
                     f"{sv or '?'} genes are assumed to be the same")
    source_rows: list[tuple[str, str]] = []           # (mod, where it came from), one per source mod, for FACES
    if old_portrait_mods is not None:
        src_mods = []
        for x in old_portrait_mods:
            d = resolve_given(x, game_dir) if x.strip() else None
            if d is None:
                continue                                 # the plan refuses it, naming it
            if has_genes(d):
                src_mods.append((d.name, d))
                source_rows.append((d.name, f"--old-portrait-mods: {d}"))
            else:
                source_rows.append((d.name, f"--old-portrait-mods: {d} (no common/genes: adds nothing)"))
    else:
        src_mods, src_missing = [], []
        for e in mods_listed(save_meta):
            d = resolve_mod(e, user, game_dir)
            if d is None or not d.is_dir():
                src_missing.append(e)
                source_rows.append((Path(e).stem, "not installed"))
            elif has_genes(d):
                src_mods.append((Path(e).stem, d))
                source_rows.append((Path(e).stem, f"the installed build of {e}: {d}"))
        if src_missing:
            more = len(src_missing) - 1
            notes.append(f"the save lists {src_missing[0]}" + (f" (and {more} other{'s' if more != 1 else ''})"
                                                               if more else "")
                         + ", which is not installed; if it shipped portrait genes, the faces R19 translates may "
                           "come out wrong; give the save's own build with --old-portrait-mods")
    base = [("vanilla", vanilla)] if vanilla is not None else []
    source = build_layout(f"the save's ({sv or '?'}"
                          + (f" + {', '.join(n for n, _ in src_mods)})" if src_mods else ", vanilla)"),
                          base + src_mods)
    game = [("vanilla", Path(game_dir))] if game_dir else []
    ref_layout = None
    if reference_meta is not None:
        ref_mods, _ = portrait_mods(mods_listed(reference_meta), user, game_dir)
        ref_layout = build_layout("the reference save's" + (f" (+ {', '.join(n for n, _ in ref_mods)})"
                                                            if ref_mods else " (vanilla)"), game + ref_mods)
    target, target_from, tnotes = target_layout(game_dir, portrait_mods_given, user)
    notes += tnotes
    pv, why = None, ""
    if reference_meta is not None and save_versions(reference_meta)["portraits_version"]:
        pv, why = int(save_versions(reference_meta)["portraits_version"]), "the reference save's"
    else:
        line = _line(target_version)
        table = portraits_version_table()
        if line in table:
            pv, why = table[line], f"the built-in table for the {line} line"
        else:
            why = f"unknown for the {line or '?'} line (no reference save, and no entry in the built-in table)"
    dropped = [g["name"] for g in source.genes if g["name"] not in {t["name"] for t in target.genes}]
    if dropped and source.places and target.places:
        shown = ", ".join(dropped[:5]) + (", ..." if len(dropped) > 5 else "")
        notes.append(f"the target layout drops {len(dropped)} gene{'s' if len(dropped) != 1 else ''} the faces use "
                     f"({shown}); set the launcher's playset to the mods you will play with, or give --portrait-mods")
    return Setup(source, target, ref_layout, pv, why, notes, target_from, source_rows)


# --------------------------------------------------------------------------- the whole save
def _people(g: bytes):
    """(char id, the start and end of its own depth-1 dna value) for every character entry with one."""
    for sec in SECTIONS:
        try:
            b = gs.locate(g, sec)
        except gs.GamestateError:
            continue
        for e in gs.iter_entries(g, *b.body):
            if not (e.key and e.key.isdigit()):
                continue
            head = g[e.start:min(e.end, e.start + 400)]
            fi = _FIRST_INDENT.match(head)
            indent = fi.group(1) if fi else b"\t"
            m = re.search(rb"\n" + re.escape(indent) + rb'dna="([^"]*)"', g[e.start:e.end])
            if m:
                yield e.key.decode(), e.start + m.start(1), e.start + m.end(1)


@dataclass
class Result:
    edits: list = field(default_factory=list)            # (start, end, replacement)
    outcomes: dict = field(default_factory=dict)         # outcome -> [character ids]
    other: Counter = field(default_factory=Counter)      # dna= outside a character's own line: outcome -> count
    dropped_places: Counter = field(default_factory=Counter)   # (layout name, places dropped) -> strings
    portraits_version: tuple | None = None              # (from, to) when it changes
    lengths: Counter = field(default_factory=Counter)
    impossible: Counter = field(default_factory=Counter)    # gene -> template bytes its source layout does not define

    @property
    def changed(self) -> int:
        return sum(len(self.outcomes.get(k, [])) for k in ("translated",)) + self.other.get("translated", 0)

    def impossible_by_gene(self) -> list[tuple[str, int]]:
        """The genes with template indexes their source layout does not define: the most first, then by name."""
        return sorted(self.impossible.items(), key=lambda kv: (-kv[1], kv[0]))

    def left(self) -> dict:
        return {k: len(v) for k, v in self.outcomes.items() if k == "already target" or k.startswith("left")}


def plan_save(g: bytes, st: Setup, transplanted: set[str] | None = None) -> Result:
    """Every change R19 makes to gamestate ``g`` (read only here): the dna strings and portraits_version."""
    transplanted = set(transplanted or ())
    own, ref = st.plans()
    res = Result()
    covered = set()
    for cid, a, b in _people(g):
        covered.add(a)
        s = g[a:b]
        res.lengths[len(s)] += 1
        plan = ref if (cid in transplanted and ref is not None) else own
        new, how, extra = translate(s, plan, res.impossible if plan is own else None)
        res.outcomes.setdefault(how, []).append(cid)
        if extra:
            res.dropped_places[(plan.source.name, extra)] += 1
        if new != s:
            res.edits.append((a, b, new))
    for m in _DNA_ANY.finditer(g):                 # a dna= outside the character entries' own line
        if m.start(1) in covered:
            continue
        s = m.group(1)
        new, how, extra = translate(s, own, res.impossible)
        res.other[how] += 1
        if new != s:
            res.edits.append((m.start(1), m.end(1), new))
    if st.portraits_version is not None:
        for m in _PV.finditer(g):
            if int(m.group(2)) != st.portraits_version:
                res.portraits_version = (int(m.group(2)), st.portraits_version)
                res.edits.append((m.start(2), m.end(2), str(st.portraits_version).encode()))
    res.edits.sort(key=lambda e: (e[0], e[1]))
    return res


def apply_edits(g: bytes, edits: list) -> bytes:
    parts, pos = [], 0
    for s0, s1, rep in edits:
        if s0 < pos:
            raise ValueError(f"overlapping DNA edits at byte {s0}")
        parts += [g[pos:s0], rep]
        pos = s1
    parts.append(g[pos:])
    return b"".join(parts)
