"""Stage the zip-manifest test save (2026-11-02, djdarcy's go; the director's ruling of the same night).

Copies MIGRATE_TEST__play7.ck3 to MIGRATE_TEST__zip_manifest.ck3 with one extra zip member, ck3update.toml, written
after gamestate. The question is the game's, answered by one load-and-save:

  PREDICTION 1 (written before the load): the game loads it (it opens `gamestate` by name).
  PREDICTION 2: after the game's own save, the member is gone (the game writes a fresh zip).

The member follows the director's rule 1 (no local path, no user name) and rule 2 (gamestate and meta bytes
unchanged: checked below, and the script refuses to write if either differs). Never overwrites: play7 is read only,
and an existing output is refused.

Run:  python -I tests/one-offs/make_zip_manifest_save.py <save games folder>
Read back after the load:  python -I tests/one-offs/make_zip_manifest_save.py <save games folder> --check <re-saved file>
"""

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ck3_save_migrator import savefile as sf  # noqa: E402
from ck3_save_migrator._version import get_base_version  # noqa: E402

SOURCE, OUT, MEMBER = "MIGRATE_TEST__play7.ck3", "MIGRATE_TEST__zip_manifest.ck3", "ck3update.toml"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def manifest(src: Path, s: sf.CK3Save) -> bytes:
    """No path, no user name: versions, the input's sha256, the date, a note."""
    return (f'# ck3update provenance (test member, 2026-11-02)\nformat = 1\ntool = "ck3-save-updater '
            f'{get_base_version()}"\ngame_version = "1.20.1.2"\ninput_sha256 = "{sha(src.read_bytes())}"\n'
            f'gamestate_sha256 = "{sha(s.gamestate)}"\ndate = "2026-11-02"\n'
            'note = "a test of whether the game loads a save with an extra zip member"\n').encode()


def members(path: Path) -> list[tuple[str, int, str]]:
    s = sf.read_save(path)
    return [(m.name, len(m.data), sha(m.data)[:12]) for m in s.members]


def main() -> int:
    folder = Path(sys.argv[1])
    if "--check" in sys.argv:
        resaved = Path(sys.argv[sys.argv.index("--check") + 1])
        print(f"{resaved.name}: members {members(resaved)}")
        print("PREDICTION 2 (member gone after the game's save):",
              "HELD" if all(n != MEMBER for n, _, _ in members(resaved)) else "MISSED (the member survived)")
        return 0
    src, out = folder / SOURCE, folder / OUT
    if out.exists():
        print(f"refused: {out} exists")
        return 1
    s = sf.read_save(src)
    gs_before, meta_before = sha(s.gamestate), sha(s.meta)
    data = manifest(src, s)
    s.members.append(sf.Member(MEMBER, data, s.members[0].date_time, s.members[0].external_attr,
                               s.members[0].compress_type))
    # recompress: CK3Save.changed looks only at gamestate, so an appended member alone would be written verbatim
    # (the input's bytes, member dropped). A finding for the real build: changed must see the member list too.
    sf.write_save(s, out, recompress=True)
    back = sf.read_save(out)
    ok = sha(back.gamestate) == gs_before and sha(back.meta) == meta_before
    names = [m.name for m in back.members]
    print(f"wrote {out.name}: members {members(out)}")
    print(f"gamestate and meta unchanged: {ok}; member present: {MEMBER in names}; source untouched: "
          f"{sha(src.read_bytes())[:12]}")
    if not ok or MEMBER not in names:
        out.unlink()
        print("removed the output: a check failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
