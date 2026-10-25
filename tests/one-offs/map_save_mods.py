"""Map the mods a CK3 save references to names, Steam IDs and versions.

Sources, in order:
  1. The save's meta_data `mods={ "mod/xxx.mod" ... }` list (header_meta.txt from inspect_save.py)
  2. The launcher's sqlite DB (launcher-v2.sqlite) copied from the machine that played the save
  3. The .mod descriptor files copied from that machine's Documents/.../mod folder

Usage: python -I map_save_mods.py <header_meta.txt> <launcher-v2.sqlite> <mod_dir_with_.mod_files>
Read-only; prints a table.
"""
import re
import sqlite3
import sys
from pathlib import Path


def parse_mod_descriptor(path: Path) -> dict:
    out = {}
    text = path.read_text(encoding="utf-8", errors="replace")
    for key in ("name", "version", "supported_version", "remote_file_id", "path"):
        m = re.search(rf'^{key}\s*=\s*"([^"]*)"', text, re.M)
        if m:
            out[key] = m.group(1)
    return out


def main(meta_path: str, sqlite_path: str, mod_dir: str) -> None:
    meta = Path(meta_path).read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^\tmods=\{(.*?)\}", meta, re.M | re.S)
    save_mods = re.findall(r'"([^"]+)"', m.group(1)) if m else []
    print(f"save references {len(save_mods)} mods\n")

    con = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
    print("launcher tables:", ", ".join(tables))
    mods_cols = [r[1] for r in con.execute("pragma table_info(mods)")]
    print("mods columns  :", ", ".join(mods_cols), "\n")
    by_descriptor = {}
    for row in con.execute("select * from mods"):
        rec = dict(zip(mods_cols, row))
        gd = rec.get("gameRegistryId") or ""
        by_descriptor[gd.replace("\\", "/")] = rec

    mod_dir_p = Path(mod_dir)
    print(f"{'#':>2} {'descriptor':28} {'steam id':11} {'version':10} {'supports':9} name")
    for i, ref in enumerate(save_mods, 1):
        rec = by_descriptor.get(ref, {})
        desc = {}
        local = mod_dir_p / Path(ref).name
        if local.exists():
            desc = parse_mod_descriptor(local)
        name = rec.get("displayName") or desc.get("name") or "?"
        steam = rec.get("steamId") or desc.get("remote_file_id") or ("ugc" if "ugc_" in ref else "local")
        ver = rec.get("version") or desc.get("version") or "?"
        sup = rec.get("requiredVersion") or desc.get("supported_version") or "?"
        flag = "" if rec or desc else "   <-- no record on the other machine"
        print(f"{i:>2} {Path(ref).name:28} {str(steam):11} {str(ver)[:10]:10} {str(sup)[:9]:9} {name}{flag}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
