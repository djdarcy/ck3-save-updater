"""docs_guard: protect a box's CK3 Documents folder around game runs (the #40 goal, S2 unit 2).

djdarcy, 2026-11-03: "make sure we backup and protect the data on each of the other boxes in the documents folders so
nothing gets clobbered ... make sure we backup old material and that we move it all back after we're done".

Three classes of path under <docs> (Documents\\Paradox Interactive\\Crusader Kings III):
  protected  every file outside the classes below (settings, dlc_load.json, pdx_settings.txt, launcher-v2*.sqlite,
             mod/, player/, playsets_backup/, last_save.ck3, continue_game.json, ...): copied into the backup and
             hashed; `restore` puts back any that changed or vanished, and moves any new one into the backup's
             `added/` folder (recoverable, never deleted).
  saves      `save games/`: size and mtime recorded. A changed or vanished save is a violation that `restore` does NOT
             touch (it never writes into djdarcy's saves); it is reported for a person. New saves named MIGRATE_TEST__*
             are allowed; any other new save is reported.
  ignored    logs/, crashes/, dumps/, exceptions/, cache/, .launcher-cache/, shadercache/, pops_filestorage/, account/
             (the game's own session file): counted, never restored.

Usage:
  python -I tests/one-offs/docs_guard.py snapshot <box> [--docs PATH]   -> private/data/backups/<stamp>__docs-<box>/
  python -I tests/one-offs/docs_guard.py check    <box> [--docs PATH] [--backup DIR]   (prints "0 differences")
  python -I tests/one-offs/docs_guard.py restore  <box> [--docs PATH] [--backup DIR]   (then checks)
The newest backup for <box> is named in private/data/backups/docs-<box>.latest. Exit 0 when clean, 1 otherwise.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKUPS = REPO / "private" / "data" / "backups"
DEFAULT_DOCS = Path.home() / "Documents" / "Paradox Interactive" / "Crusader Kings III"
# account/: the Paradox account session (account/PDX/SDK/ck3/account.json), rewritten by every launch of the game;
# putting an older copy back could sign the player out, so it is counted, never restored (2026-11-03, first live run)
IGNORED = ("logs", "crashes", "dumps", "exceptions", "cache", ".launcher-cache", "shadercache", "pops_filestorage",
           "account")
SAVES = "save games"
ALLOWED_NEW_SAVE = "MIGRATE_TEST__"


def classify(rel: str) -> str:
    top = rel.split("/", 1)[0]
    if top in IGNORED:
        return "ignored"
    if top == SAVES:
        return "saves"
    return "protected"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def walk(docs: Path) -> dict[str, dict]:
    out = {}
    for root, dirs, files in os.walk(docs):
        rroot = Path(root).relative_to(docs).as_posix()
        if rroot != "." and classify(rroot) == "ignored":
            dirs[:] = []
            continue
        for name in files:
            p = Path(root) / name
            rel = (Path(rroot) / name).as_posix() if rroot != "." else name
            st = p.stat()
            out[rel] = {"class": classify(rel), "size": st.st_size, "mtime": st.st_mtime_ns}
    return out


def snapshot(box: str, docs: Path, backups: Path = BACKUPS) -> Path:
    stamp = datetime.datetime.now().strftime("%Y-%m-%d__%H-%M-%S")
    dest = backups / f"{stamp}__docs-{box}"
    files = dest / "files"
    files.mkdir(parents=True)
    manifest = walk(docs)
    for rel, m in manifest.items():
        if m["class"] == "protected":
            src = docs / rel
            m["sha256"] = sha256(src)
            (files / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, files / rel)
            if sha256(files / rel) != m["sha256"]:
                raise SystemExit(f"backup copy differs from its source: {rel}")
    (dest / "manifest.json").write_text(json.dumps({"box": box, "docs": str(docs), "taken": stamp,
                                                    "files": manifest}, indent=1), encoding="utf-8")
    (backups / f"docs-{box}.latest").write_text(str(dest), encoding="utf-8")
    n = {c: sum(1 for m in manifest.values() if m["class"] == c) for c in ("protected", "saves")}
    print(f"snapshot {dest}: {n['protected']} protected files backed up, {n['saves']} saves recorded")
    return dest


def latest(box: str, backups: Path = BACKUPS) -> Path:
    p = backups / f"docs-{box}.latest"
    if not p.is_file():
        raise SystemExit(f"no snapshot for {box}: run `snapshot {box}` first")
    return Path(p.read_text(encoding="utf-8").strip())


def differences(docs: Path, backup: Path) -> list[tuple[str, str, str]]:
    """(kind, class, rel) for everything that differs from the snapshot, ignored paths aside."""
    before = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))["files"]
    now = walk(docs)
    out = []
    for rel, m in before.items():
        cls = classify(rel)                 # today's classes, not the snapshot's (a class can move to ignored)
        if cls == "ignored":
            continue
        cur = now.get(rel)
        if cur is None:
            out.append(("vanished", cls, rel))
        elif cls == "protected":
            if cur["size"] != m["size"] or sha256(docs / rel) != m["sha256"]:
                out.append(("changed", "protected", rel))
        elif cur["size"] != m["size"] or cur["mtime"] != m["mtime"]:
            out.append(("changed", "saves", rel))
    for rel, cur in now.items():
        if rel in before or cur["class"] == "ignored":
            continue
        if cur["class"] == "saves" and Path(rel).name.startswith(ALLOWED_NEW_SAVE):
            continue
        out.append(("new", cur["class"], rel))
    return out


def check(docs: Path, backup: Path) -> int:
    diff = differences(docs, backup)
    for kind, cls, rel in diff:
        print(f"  {kind:8} {cls:9} {rel}")
    print(f"{len(diff)} differences (against {backup.name})")
    return 0 if not diff else 1


def restore(docs: Path, backup: Path) -> int:
    for kind, cls, rel in differences(docs, backup):
        if cls != "protected":
            print(f"  left for a person: {kind} {cls} {rel}")
            continue
        if kind in ("changed", "vanished"):
            (docs / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup / "files" / rel, docs / rel)
            print(f"  restored {rel}")
        elif kind == "new":
            moved = backup / "added" / rel
            moved.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(docs / rel), str(moved))
            print(f"  moved new file into the backup: {rel}")
            parent = (docs / rel).parent           # a folder the run created and this emptied (1.8.2's terraincache/)
            while parent != docs and parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
                print(f"  removed the emptied folder: {parent.relative_to(docs).as_posix()}/")
                parent = parent.parent
    return check(docs, backup)


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] not in ("snapshot", "check", "restore"):
        print(__doc__)
        return 2
    cmd, box = argv[0], argv[1]
    docs = Path(argv[argv.index("--docs") + 1]) if "--docs" in argv else DEFAULT_DOCS
    if not docs.is_dir():
        raise SystemExit(f"no such Documents folder: {docs}")
    if cmd == "snapshot":
        snapshot(box, docs)
        return 0
    backup = Path(argv[argv.index("--backup") + 1]) if "--backup" in argv else latest(box)
    return check(docs, backup) if cmd == "check" else restore(docs, backup)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
