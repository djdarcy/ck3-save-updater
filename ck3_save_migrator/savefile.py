"""Read and write Crusader Kings III ``.ck3`` save files (header kind 02, "UnifiedText").

Layout of a kind-02 save, as written by CK3 1.5 through 1.20 (and as rakaly's
``ck3save/src/header.rs`` reads it)::

    SAV <2 hex: unknown, "01"> <2 hex: kind> <8 hex: random id> <8 hex: meta length> \\n
    meta_data={ ... }\\n                      <- plaintext copy, exactly <meta length> bytes
    PK\\x03\\x04 ...                           <- zip with one member, "gamestate"

The inflated ``gamestate`` begins with the same ``meta_data={...}`` block, byte
for byte, so the plaintext copy is a prefix of the gamestate. This module treats
the gamestate as the source of truth: when the gamestate changes, the plaintext
block is re-derived from it and the length field recomputed, so the two copies
cannot drift apart.

Writing never touches the input: output goes to a new path (default
``<name>.migrated.ck3``), is written to a temporary file in the same folder,
re-read and verified, and only then moved into place with ``os.replace``.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

KIND_TEXT = 0
KIND_BINARY = 1
KIND_UNIFIED_TEXT = 2
KIND_UNIFIED_BINARY = 3
KIND_NAMES = {0: "Text", 1: "Binary", 2: "UnifiedText", 3: "UnifiedBinary", 4: "SplitText", 5: "SplitBinary"}

SUPPORTED_KINDS = {KIND_UNIFIED_TEXT}

GAMESTATE = "gamestate"
ZIP_MAGIC = b"PK\x03\x04"
DEFLATE_LEVEL = 6

_HEADER_RE = re.compile(
    rb"^SAV(?P<unknown>[0-9a-fA-F]{2})(?P<kind>[0-9a-fA-F]{2})"
    rb"(?P<random>[0-9a-fA-F]{8})(?P<meta_len>[0-9a-fA-F]{8})(?P<newline>\r?\n)"
)


class SaveFormatError(ValueError):
    """The file is not a CK3 save this module can read."""


class UnsupportedKindError(SaveFormatError):
    """A real CK3 save, but a header kind this module does not handle (binary / ironman)."""


class VerifyError(RuntimeError):
    """A written save did not read back as expected; nothing was moved into place."""


class OutputExistsError(FileExistsError):
    """The output path already exists and ``force`` was not given."""


class InPlaceError(ValueError):
    """The output path is the input path; editing an original in place is refused."""


@dataclass
class Header:
    unknown: str          # bytes 3-4, observed "01"; kept verbatim
    kind: int
    random: str           # 8 hex chars; kept verbatim
    meta_len: int
    newline: bytes        # b"\n" or b"\r\n"
    raw: bytes            # the header line exactly as read, newline included

    def render(self, meta_len: int) -> bytes:
        return f"SAV{self.unknown}{self.kind:02x}{self.random}{meta_len:08x}".encode("ascii") + self.newline


@dataclass
class Member:
    name: str
    data: bytes           # inflated
    date_time: tuple
    external_attr: int
    compress_type: int


@dataclass
class Edit:
    start: int            # offsets in the gamestate *before* this edit
    end: int
    new_len: int


@dataclass
class CK3Save:
    header: Header
    meta: bytes                           # plaintext block as read
    members: list[Member]
    raw_zip: bytes                        # zip region as read
    source: Path | None = None
    warnings: list[str] = field(default_factory=list)
    edits: list[Edit] = field(default_factory=list)
    _original_gamestate_sha: str = ""

    # ------------------------------------------------------------------ access
    def _member(self, name: str) -> Member:
        for m in self.members:
            if m.name == name:
                return m
        raise KeyError(name)

    @property
    def gamestate(self) -> bytes:
        return self._member(GAMESTATE).data

    @property
    def kind_name(self) -> str:
        return KIND_NAMES.get(self.header.kind, f"unknown({self.header.kind})")

    @property
    def changed(self) -> bool:
        return sha256(self.gamestate) != self._original_gamestate_sha

    # ------------------------------------------------------------------- edits
    def replace_range(self, start: int, end: int, replacement: bytes) -> None:
        """Replace gamestate[start:end] with ``replacement`` and record the edit.

        The plaintext meta block is re-derived on write, so an edit inside the
        leading ``meta_data`` block updates both copies.
        """
        gs = self.gamestate
        if not (0 <= start <= end <= len(gs)):
            raise IndexError(f"edit range {start}:{end} outside gamestate of {len(gs)} bytes")
        self._member(GAMESTATE).data = gs[:start] + replacement + gs[end:]
        self.edits.append(Edit(start, end, len(replacement)))

    def set_gamestate(self, data: bytes) -> None:
        """Replace the whole gamestate (rules that rebuild it wholesale)."""
        self._member(GAMESTATE).data = data

    # --------------------------------------------------------------- serialise
    def derived_meta(self) -> bytes:
        """The plaintext meta block the gamestate implies: its leading meta_data={...} block."""
        return self.gamestate[: meta_block_end(self.gamestate)]

    def can_reuse_input(self, recompress: bool = False) -> bool:
        """True when serialising can return the input bytes unchanged."""
        return not self.changed and not recompress and self.meta == self.derived_meta()

    def to_bytes(self, recompress: bool = False) -> bytes:
        """Serialise. Unchanged and not ``recompress``: the input bytes, verbatim.

        Otherwise the meta block is re-derived from the gamestate, the length field
        recomputed, and every member re-deflated (zlib level 6), keeping member
        order, names, date_time and external_attr.
        """
        if self.can_reuse_input(recompress):
            return self.header.raw + self.meta + self.raw_zip
        meta = self.derived_meta()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=DEFLATE_LEVEL) as z:
            for m in self.members:
                zi = zipfile.ZipInfo(filename=m.name, date_time=m.date_time)
                zi.compress_type = zipfile.ZIP_DEFLATED
                zi.external_attr = m.external_attr
                z.writestr(zi, m.data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=DEFLATE_LEVEL)
        return self.header.render(len(meta)) + meta + buf.getvalue()


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def meta_block_end(gamestate: bytes) -> int:
    """Offset just past the leading ``meta_data={...}`` block and its newline.

    Brace-matches from the first ``{`` (skipping quoted strings), then includes
    the line ending. Raises SaveFormatError if the gamestate does not start
    with ``meta_data``.
    """
    m = re.match(rb"\s*meta_data\s*=\s*\{", gamestate)
    if not m:
        raise SaveFormatError("gamestate does not begin with a meta_data block")
    depth = 0
    i = m.end() - 1
    n = len(gamestate)
    while i < n:
        c = gamestate[i]
        if c == 0x22:  # quoted string: skip to the closing quote, honouring backslash escapes
            i += 1
            while i < n and gamestate[i] != 0x22:
                i += 2 if gamestate[i] == 0x5C else 1
        elif c == 0x7B:
            depth += 1
        elif c == 0x7D:
            depth -= 1
            if depth == 0:
                i += 1
                if gamestate[i:i + 2] == b"\r\n":
                    return i + 2
                if gamestate[i:i + 1] == b"\n":
                    return i + 1
                return i
        i += 1
    raise SaveFormatError("meta_data block in gamestate is not closed")


def parse_header(data: bytes) -> Header:
    m = _HEADER_RE.match(data)
    if not m:
        raise SaveFormatError("not a CK3 save: missing 'SAV' header line")
    g = m.groupdict()
    return Header(
        unknown=g["unknown"].decode("ascii"),
        kind=int(g["kind"], 16),
        random=g["random"].decode("ascii"),
        meta_len=int(g["meta_len"], 16),
        newline=g["newline"],
        raw=data[: m.end()],
    )


def parse_save(data: bytes, source: Path | None = None) -> CK3Save:
    header = parse_header(data)
    if header.kind not in SUPPORTED_KINDS:
        raise UnsupportedKindError(
            f"save header kind {header.kind:02x} ({KIND_NAMES.get(header.kind, 'unknown')}) is not supported; "
            f"only kind 02 (UnifiedText, a normal non-ironman manual save) can be read"
        )
    hlen = len(header.raw)
    meta_end = hlen + header.meta_len
    warnings: list[str] = []
    zip_at = meta_end
    if data[zip_at:zip_at + 4] != ZIP_MAGIC:
        found = data.find(ZIP_MAGIC, hlen)
        if found < 0:
            raise SaveFormatError("no zip data found after the meta block")
        warnings.append(f"zip starts at byte {found}, not at header+meta_len ({zip_at}); meta length field is wrong")
        zip_at = found
    meta = data[hlen:zip_at]
    raw_zip = data[zip_at:]
    try:
        with zipfile.ZipFile(io.BytesIO(raw_zip)) as z:
            members = [Member(i.filename, z.read(i), i.date_time, i.external_attr, i.compress_type)
                       for i in z.infolist()]
    except zipfile.BadZipFile as exc:
        raise SaveFormatError(f"zip region of the save is corrupt: {exc}") from exc
    if not any(m.name == GAMESTATE for m in members):
        raise SaveFormatError(f"zip has no '{GAMESTATE}' member (members: {[m.name for m in members]})")
    save = CK3Save(header=header, meta=meta, members=members, raw_zip=raw_zip, source=source, warnings=warnings)
    save._original_gamestate_sha = sha256(save.gamestate)
    derived = save.derived_meta()
    if meta != derived:
        save.warnings.append(
            f"plaintext meta block ({len(meta)} bytes) differs from the gamestate's meta_data block "
            f"({len(derived)} bytes); the gamestate copy is treated as authoritative on write"
        )
    return save


def read_save(path: str | os.PathLike) -> CK3Save:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"save file not found: {p}")
    return parse_save(p.read_bytes(), source=p)


def default_output(path: str | os.PathLike) -> Path:
    p = Path(path)
    return p.with_name(f"{p.stem}.migrated{p.suffix or '.ck3'}")


# --------------------------------------------------------------------------- #
# verification and writing
# --------------------------------------------------------------------------- #
@dataclass
class WriteResult:
    path: Path | None
    size: int
    sha256: str
    gamestate_sha256: str
    meta_len: int
    verbatim: bool        # True if the input bytes were reused unchanged
    dry_run: bool


def verify_bytes(data: bytes, expected_gamestate_sha: str) -> CK3Save:
    """Re-parse serialised bytes and check the invariants; raise VerifyError on any failure."""
    try:
        back = parse_save(data)
    except SaveFormatError as exc:
        raise VerifyError(f"written save does not parse: {exc}") from exc
    if back.warnings:
        raise VerifyError("written save has inconsistencies: " + "; ".join(back.warnings))
    if sha256(back.gamestate) != expected_gamestate_sha:
        raise VerifyError("written gamestate differs from the intended gamestate")
    if back.header.meta_len != len(back.meta):
        raise VerifyError(f"meta length field {back.header.meta_len} != meta block {len(back.meta)}")
    return back


REPLACE_ATTEMPTS = 20
REPLACE_DELAY = 0.1   # seconds between attempts: about 2 s in all


def _replace(src: Path, dst: Path) -> None:
    """os.replace, retried on PermissionError: on Windows a scanner or indexer can hold a just-written file
    for a moment (seen as WinError 5 replacing an output written a few ms earlier). The last error is raised."""
    for attempt in range(REPLACE_ATTEMPTS):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(REPLACE_DELAY)


def write_save(save: CK3Save, out: str | os.PathLike, *, force: bool = False, recompress: bool = False,
               dry_run: bool = False) -> WriteResult:
    """Serialise ``save`` to ``out``: never in place, atomic, verified before it lands.

    ``dry_run`` builds and verifies the bytes in memory and writes nothing.
    """
    out_p = Path(out)
    if save.source is not None and out_p.resolve() == save.source.resolve():
        raise InPlaceError(f"refusing to write over the input file: {out_p}")
    if out_p.exists() and not force and not dry_run:
        raise OutputExistsError(f"output already exists: {out_p} (use --force to overwrite)")

    verbatim = save.can_reuse_input(recompress)
    data = save.to_bytes(recompress=recompress)
    expected = sha256(save.gamestate)
    back = verify_bytes(data, expected)
    result = WriteResult(path=None if dry_run else out_p, size=len(data), sha256=sha256(data),
                         gamestate_sha256=expected, meta_len=back.header.meta_len, verbatim=verbatim,
                         dry_run=dry_run)
    if dry_run:
        return result

    tmp = out_p.with_name(out_p.name + ".tmp")
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        verify_bytes(tmp.read_bytes(), expected)   # what reached the disk, not what we meant to write
        _replace(tmp, out_p)
    finally:
        if tmp.exists():
            tmp.unlink()
    return result
