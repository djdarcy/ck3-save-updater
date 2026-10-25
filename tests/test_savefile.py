"""Tests for ck3_save_migrator.savefile -- reading and writing kind-02 .ck3 saves.

Every save here is synthetic (tests/fixtures/make_ck3.py) and every write goes to
tmp_path. The real-save checks at the bottom run only when the gitignored
private/data copies exist, and always write into tmp_path.
"""

from __future__ import annotations

import difflib
import io
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from ck3_save_migrator import savefile as sf
from tests.fixtures.make_ck3 import DEFAULT_BODY, DEFAULT_META, build_ck3

ROOT = Path(__file__).resolve().parents[1]
REF_SAVE = ROOT / "private" / "data" / "originals" / "reference-1.20" / "ref_1_20_persia_867.ck3"


def write(tmp_path: Path, data: bytes, name: str = "test.ck3") -> Path:
    p = tmp_path / name
    p.write_bytes(data)
    return p


def inflate(data: bytes) -> bytes:
    off = data.index(sf.ZIP_MAGIC)
    with zipfile.ZipFile(io.BytesIO(data[off:])) as z:
        return z.read("gamestate")


# --------------------------------------------------------------------------- reading
class TestRead:
    def test_header_fields(self, tmp_path):
        save = sf.read_save(write(tmp_path, build_ck3()))
        h = save.header
        assert (h.unknown, h.kind, h.random, h.newline) == ("01", 2, "7d3b0037", b"\n")
        assert h.meta_len == len(DEFAULT_META) == len(save.meta)
        assert save.gamestate == DEFAULT_META + DEFAULT_BODY
        assert save.warnings == []

    def test_meta_is_prefix_of_gamestate(self, tmp_path):
        save = sf.read_save(write(tmp_path, build_ck3()))
        assert save.gamestate.startswith(save.meta)
        assert save.derived_meta() == save.meta

    def test_meta_block_end_skips_braces_inside_strings(self):
        # DEFAULT_META has '{braces}' and escaped quotes inside a quoted value
        assert sf.meta_block_end(DEFAULT_META + DEFAULT_BODY) == len(DEFAULT_META)

    def test_crlf_header_accepted(self, tmp_path):
        save = sf.read_save(write(tmp_path, build_ck3(newline=b"\r\n")))
        assert save.header.newline == b"\r\n"
        assert save.warnings == []

    def test_uppercase_hex_accepted(self, tmp_path):
        save = sf.read_save(write(tmp_path, build_ck3(random="7D3B0037", upper_hex=True)))
        assert save.header.random == "7D3B0037"
        assert save.header.meta_len == len(DEFAULT_META)

    def test_not_a_save(self, tmp_path):
        with pytest.raises(sf.SaveFormatError, match="SAV"):
            sf.read_save(write(tmp_path, b"PK\x03\x04 not a save"))

    @pytest.mark.parametrize("kind", [0, 1, 3, 5])
    def test_unsupported_kinds_refused(self, tmp_path, kind):
        with pytest.raises(sf.UnsupportedKindError, match=f"{kind:02x}"):
            sf.read_save(write(tmp_path, build_ck3(kind=kind)))

    def test_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            sf.read_save(tmp_path / "nope.ck3")

    def test_wrong_meta_length_warns_and_finds_zip(self, tmp_path):
        save = sf.read_save(write(tmp_path, build_ck3(meta_len=len(DEFAULT_META) - 10)))
        assert any("meta length field is wrong" in w for w in save.warnings)
        assert save.gamestate == DEFAULT_META + DEFAULT_BODY

    def test_disagreeing_meta_copies_warn(self, tmp_path):
        other = DEFAULT_META.replace(b"987.10.27", b"900.01.01")
        save = sf.read_save(write(tmp_path, build_ck3(plaintext_meta=other)))
        assert any("differs from the gamestate" in w for w in save.warnings)

    def test_no_gamestate_member(self, tmp_path):
        with pytest.raises(sf.SaveFormatError, match="gamestate"):
            sf.read_save(write(tmp_path, build_ck3(member_name="other")))

    def test_corrupt_zip(self, tmp_path):
        data = build_ck3()
        off = data.index(sf.ZIP_MAGIC)
        with pytest.raises(sf.SaveFormatError, match="corrupt"):
            sf.read_save(write(tmp_path, data[: off + 40]))


# --------------------------------------------------------------------------- serialising
class TestRoundTrip:
    def test_noop_is_byte_identical(self, tmp_path):
        data = build_ck3()
        save = sf.read_save(write(tmp_path, data))
        assert save.to_bytes() == data

    def test_noop_crlf_byte_identical(self, tmp_path):
        data = build_ck3(newline=b"\r\n")
        assert sf.read_save(write(tmp_path, data)).to_bytes() == data

    def test_recompress_keeps_gamestate_and_header(self, tmp_path):
        data = build_ck3(compresslevel=1)
        out = sf.read_save(write(tmp_path, data)).to_bytes(recompress=True)
        assert out != data                               # really re-deflated
        back = sf.parse_save(out)
        assert back.gamestate == DEFAULT_META + DEFAULT_BODY
        assert back.header.raw == data[: len(back.header.raw)]
        assert back.warnings == []

    def test_recompress_member_metadata(self, tmp_path):
        out = sf.read_save(write(tmp_path, build_ck3())).to_bytes(recompress=True)
        with zipfile.ZipFile(io.BytesIO(out[out.index(sf.ZIP_MAGIC):])) as z:
            (info,) = z.infolist()
        assert info.filename == "gamestate"
        assert info.compress_type == zipfile.ZIP_DEFLATED
        assert info.date_time == (1980, 1, 1, 0, 0, 0)

    def test_extra_members_preserved(self, tmp_path):
        data = build_ck3(extra_members={"rnw.zip": b"extra"})
        save = sf.read_save(write(tmp_path, data))
        back = sf.parse_save(save.to_bytes(recompress=True))
        assert [m.name for m in back.members] == ["gamestate", "rnw.zip"]
        assert back.members[1].data == b"extra"

    def test_header_written_lowercase_with_fields_kept(self, tmp_path):
        save = sf.read_save(write(tmp_path, build_ck3(random="7D3B0037", upper_hex=True)))
        out = save.to_bytes(recompress=True)
        assert out.startswith(f"SAV0102{'7D3B0037'}{len(DEFAULT_META):08x}\n".encode())


# --------------------------------------------------------------------------- edits (A1b)
class TestEdits:
    def test_body_edit_changes_only_its_range(self, tmp_path):
        save = sf.read_save(write(tmp_path, build_ck3()))
        before = save.gamestate
        start = before.index(b"birth=950.3.9") + len(b"birth=")
        end = start + len(b"950.3.9")
        save.replace_range(start, end, b"951.4.10")
        after = sf.parse_save(save.to_bytes()).gamestate
        ops = [op for op in difflib.SequenceMatcher(None, before, after, autojunk=False).get_opcodes()
               if op[0] != "equal"]
        assert all(start <= i1 and i2 <= end for _, i1, i2, _, _ in ops), ops
        assert after[:start] == before[:start] and after[start + 8:] == before[end:]
        assert save.edits == [sf.Edit(start, end, 8)]

    def test_body_edit_leaves_meta_and_length(self, tmp_path):
        save = sf.read_save(write(tmp_path, build_ck3()))
        i = save.gamestate.index(b"Simin")
        save.replace_range(i, i + 5, b"Simon")
        back = sf.parse_save(save.to_bytes())
        assert back.meta == DEFAULT_META
        assert back.header.meta_len == len(DEFAULT_META)
        assert back.warnings == []

    def test_meta_edit_updates_both_copies_and_length(self, tmp_path):
        save = sf.read_save(write(tmp_path, build_ck3()))
        i = save.gamestate.index(b'version="1.8.1"')
        save.replace_range(i, i + len(b'version="1.8.1"'), b'version="1.20.1.2"')
        back = sf.parse_save(save.to_bytes())
        assert b'version="1.20.1.2"' in back.meta
        assert back.gamestate.startswith(back.meta)
        assert back.header.meta_len == len(DEFAULT_META) + 3 == len(back.meta)
        assert back.warnings == []

    def test_edit_out_of_range(self, tmp_path):
        save = sf.read_save(write(tmp_path, build_ck3()))
        with pytest.raises(IndexError):
            save.replace_range(0, len(save.gamestate) + 1, b"")

    def test_foreign_disagreeing_meta_is_rederived_on_write(self, tmp_path):
        other = DEFAULT_META.replace(b"987.10.27", b"900.01.01")
        save = sf.read_save(write(tmp_path, build_ck3(plaintext_meta=other)))
        back = sf.parse_save(save.to_bytes())          # not verbatim: copies disagree
        assert back.meta == DEFAULT_META and back.warnings == []


# --------------------------------------------------------------------------- writing
class TestWrite:
    def test_default_output_name(self):
        assert sf.default_output(Path("a/Save_987.ck3")) == Path("a/Save_987.migrated.ck3")

    def test_write_verbatim(self, tmp_path):
        data = build_ck3()
        save = sf.read_save(write(tmp_path, data))
        r = sf.write_save(save, tmp_path / "out.ck3")
        assert (tmp_path / "out.ck3").read_bytes() == data
        assert r.verbatim and not r.dry_run and r.sha256 == sf.sha256(data)
        assert not (tmp_path / "out.ck3.tmp").exists()

    def test_write_recompressed(self, tmp_path):
        save = sf.read_save(write(tmp_path, build_ck3()))
        r = sf.write_save(save, tmp_path / "out.ck3", recompress=True)
        assert not r.verbatim
        assert inflate((tmp_path / "out.ck3").read_bytes()) == DEFAULT_META + DEFAULT_BODY

    def test_dry_run_writes_nothing(self, tmp_path):
        save = sf.read_save(write(tmp_path, build_ck3()))
        r = sf.write_save(save, tmp_path / "out.ck3", dry_run=True)
        assert r.dry_run and r.path is None
        assert not (tmp_path / "out.ck3").exists()

    def test_refuses_in_place(self, tmp_path):
        src = write(tmp_path, build_ck3())
        before = src.read_bytes()
        save = sf.read_save(src)
        with pytest.raises(sf.InPlaceError):
            sf.write_save(save, src, force=True)
        assert src.read_bytes() == before

    def test_refuses_existing_output(self, tmp_path):
        save = sf.read_save(write(tmp_path, build_ck3()))
        out = write(tmp_path, b"keep me", "out.ck3")
        with pytest.raises(sf.OutputExistsError):
            sf.write_save(save, out)
        assert out.read_bytes() == b"keep me"

    def test_force_overwrites(self, tmp_path):
        save = sf.read_save(write(tmp_path, build_ck3()))
        out = write(tmp_path, b"old", "out.ck3")
        sf.write_save(save, out, force=True)
        assert out.read_bytes().startswith(b"SAV0102")

    def test_replace_retried_while_file_held(self, tmp_path, monkeypatch):
        """Windows can hold a just-written output for a moment (WinError 5); the replace is retried."""
        save = sf.read_save(write(tmp_path, build_ck3()))
        out = write(tmp_path, b"old", "out.ck3")
        real, calls, sleeps = sf.os.replace, {"n": 0}, []

        def held_twice(src, dst):
            calls["n"] += 1
            if calls["n"] <= 2:
                raise PermissionError(5, "Access is denied", str(dst))
            return real(src, dst)
        monkeypatch.setattr(sf.os, "replace", held_twice)
        monkeypatch.setattr(sf.time, "sleep", sleeps.append)
        sf.write_save(save, out, force=True)
        assert calls["n"] == 3 and sleeps == [sf.REPLACE_DELAY] * 2
        assert out.read_bytes().startswith(b"SAV0102")
        assert not list(tmp_path.glob("*.tmp"))

    def test_replace_gives_up_with_the_original_error(self, tmp_path, monkeypatch):
        save = sf.read_save(write(tmp_path, build_ck3()))
        out = write(tmp_path, b"keep me", "out.ck3")
        calls = {"n": 0}

        def always_held(src, dst):
            calls["n"] += 1
            raise PermissionError(5, f"held {calls['n']}", str(dst))
        monkeypatch.setattr(sf.os, "replace", always_held)
        monkeypatch.setattr(sf.time, "sleep", lambda s: None)
        with pytest.raises(PermissionError, match=f"held {sf.REPLACE_ATTEMPTS}"):
            sf.write_save(save, out, force=True)
        assert calls["n"] == sf.REPLACE_ATTEMPTS
        assert out.read_bytes() == b"keep me" and not list(tmp_path.glob("*.tmp"))

    def test_failed_disk_verify_leaves_nothing(self, tmp_path, monkeypatch):
        save = sf.read_save(write(tmp_path, build_ck3()))
        real = sf.verify_bytes
        calls = {"n": 0}

        def flaky(data, expected):
            calls["n"] += 1
            if calls["n"] == 2:            # the re-read of the temp file on disk
                raise sf.VerifyError("simulated disk corruption")
            return real(data, expected)

        monkeypatch.setattr(sf, "verify_bytes", flaky)
        with pytest.raises(sf.VerifyError):
            sf.write_save(save, tmp_path / "out.ck3")
        assert not (tmp_path / "out.ck3").exists()
        assert not (tmp_path / "out.ck3.tmp").exists()


# --------------------------------------------------------------------------- CLI
def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "ck3_save_migrator", *args],
                          capture_output=True, text=True, cwd=ROOT)


class TestCLI:
    def test_inspect(self, tmp_path):
        r = run_cli("inspect", str(write(tmp_path, build_ck3())))
        assert r.returncode == 0, r.stderr
        assert "UnifiedText" in r.stdout and "gamestate" in r.stdout

    def test_migrate_default_output(self, tmp_path):
        src = write(tmp_path, build_ck3(), "Beidh.ck3")
        r = run_cli("migrate", str(src))
        assert r.returncode == 0, r.stderr
        assert (tmp_path / "Beidh.migrated.ck3").read_bytes() == src.read_bytes()

    def test_migrate_dry_run(self, tmp_path):
        src = write(tmp_path, build_ck3())
        r = run_cli("migrate", str(src), "--dry-run", "-o", str(tmp_path / "o.ck3"))
        assert r.returncode == 0 and "[dry-run]" in r.stdout
        assert not (tmp_path / "o.ck3").exists()

    def test_migrate_refuses_existing(self, tmp_path):
        src = write(tmp_path, build_ck3())
        write(tmp_path, b"x", "o.ck3")
        assert run_cli("migrate", str(src), "-o", str(tmp_path / "o.ck3")).returncode == 2

    def test_migrate_refuses_in_place(self, tmp_path):
        src = write(tmp_path, build_ck3())
        assert run_cli("migrate", str(src), "-o", str(src), "--force").returncode == 2

    def test_bad_input_exit_1(self, tmp_path):
        assert run_cli("inspect", str(write(tmp_path, b"junk"))).returncode == 1


# --------------------------------------------------------------------------- real saves (local only)
@pytest.mark.skipif(not REF_SAVE.exists(), reason="1.20 reference save not present (private/data is gitignored)")
class TestReferenceSave:
    def test_ref_header_and_meta(self):
        save = sf.read_save(REF_SAVE)
        assert save.header.meta_len == 22624 == len(save.meta)
        assert save.warnings == []

    def test_ref_recompressed_roundtrip_a1a(self, tmp_path):
        save = sf.read_save(REF_SAVE)
        original = save.gamestate
        r = sf.write_save(save, tmp_path / "ref.migrated.ck3", recompress=True)
        back = sf.read_save(tmp_path / "ref.migrated.ck3")
        assert back.gamestate == original
        assert back.meta == back.gamestate[: back.header.meta_len]
        assert back.warnings == [] and not r.verbatim
