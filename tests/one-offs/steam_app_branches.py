"""List a Steam app's beta branches from the Steam client's local appinfo cache (read-only, no network).

appinfo.vdf, format 29 (magic 0x07564429): header (magic, universe, string-table offset), then app entries
(appid, size, info state, last updated, PICS token, two SHA-1s, change number) each followed by a binary KV
tree whose keys are indices into the string table at the end of the file.

Usage: python -I tests/one-offs/steam_app_branches.py [appid] [appinfo.vdf]
       default appid 1158310 (Crusader Kings III), default path C:/Program Files (x86)/Steam/appcache/appinfo.vdf
"""
import datetime
import struct
import sys
from pathlib import Path


def read_strings(data: bytes, off: int) -> list[str]:
    (count,) = struct.unpack_from("<I", data, off)
    pos, out = off + 4, []
    for _ in range(count):
        end = data.index(b"\x00", pos)
        out.append(data[pos:end].decode("utf-8", "replace"))
        pos = end + 1
    return out


def read_kv(data: bytes, pos: int, strings: list[str]) -> tuple[dict, int]:
    out = {}
    while True:
        t = data[pos]
        pos += 1
        if t == 0x08:
            return out, pos
        (ki,) = struct.unpack_from("<I", data, pos)
        pos += 4
        key = strings[ki]
        if t == 0x00:
            out[key], pos = read_kv(data, pos, strings)
        elif t == 0x01:
            end = data.index(b"\x00", pos)
            out[key] = data[pos:end].decode("utf-8", "replace")
            pos = end + 1
        elif t == 0x02:
            (out[key],) = struct.unpack_from("<i", data, pos)
            pos += 4
        elif t == 0x03:
            (out[key],) = struct.unpack_from("<f", data, pos)
            pos += 4
        elif t == 0x07:
            (out[key],) = struct.unpack_from("<Q", data, pos)
            pos += 8
        else:
            raise ValueError(f"unknown KV type {t:#x} at {pos - 1}")


def app_info(path: Path, appid: int) -> dict:
    data = path.read_bytes()
    magic, _universe, st_off = struct.unpack_from("<IIq", data, 0)
    if magic != 0x07564429:
        raise ValueError(f"unsupported appinfo format {magic:#x}")
    strings = read_strings(data, st_off)
    pos = 16
    while True:
        (aid,) = struct.unpack_from("<I", data, pos)
        if aid == 0:
            raise KeyError(appid)
        (size,) = struct.unpack_from("<I", data, pos + 4)
        if aid == appid:
            kv_start = pos + 8 + 60          # infostate 4, last_updated 4, token 8, sha1 20, change 4, sha1 20
            tree, _ = read_kv(data, kv_start, strings)
            return tree
        pos += 8 + size


def sizes(info: dict, branches: list[str], skip: set[str]) -> None:
    """Per branch: the Windows depots that have a manifest for exactly that branch (no fallback to public),
    with Steam's own size on disk and download size. Depots in `skip` (not owned, redistributables) are left out."""
    depots = {k: v for k, v in info["depots"].items() if k.isdigit()}
    total = 0
    print(f"{'branch':10} {'depots':>6} {'on disk GB':>11} {'download GB':>12} {'cumulative on disk GB':>22}")
    for br in branches:
        n, disk, dl = 0, 0, 0
        for k, v in depots.items():
            if k in skip or v.get("config", {}).get("oslist", "windows") not in ("windows", ""):
                continue
            m = v.get("manifests", {}).get(br)
            if not m:
                continue
            n += 1
            disk += int(m.get("size", 0))
            dl += int(m.get("download", 0))
        total += disk
        print(f"{br:10} {n:>6} {disk / 1e9:>11.2f} {dl / 1e9:>12.2f} {total / 1e9:>22.2f}")


def main():
    if "--sizes" in sys.argv:
        i = sys.argv.index("--sizes")
        branches = sys.argv[i + 1].split(",")
        skip = set(sys.argv[i + 2].split(",")) if len(sys.argv) > i + 2 else set()
        info = app_info(Path("C:/Program Files (x86)/Steam/appcache/appinfo.vdf"), 1158310)["appinfo"]
        sizes(info, branches, skip)
        return
    appid = int(sys.argv[1]) if len(sys.argv) > 1 else 1158310
    path = Path(sys.argv[2] if len(sys.argv) > 2 else "C:/Program Files (x86)/Steam/appcache/appinfo.vdf")
    info = app_info(path, appid).get("appinfo", {})
    depots = info.get("depots", {})
    branches = depots.get("branches", {})
    print(f"app {appid}: {info.get('common', {}).get('name')}; {len(branches)} branches")
    rows = []
    for name, b in branches.items():
        t = b.get("timeupdated")
        when = datetime.datetime.fromtimestamp(int(t), datetime.timezone.utc).date() if t else "?"
        rows.append((str(when), name, b.get("buildid"), b.get("description", ""), b.get("pwdrequired", 0)))
    for when, name, build, desc, pwd in sorted(rows):
        print(f"  {when}  {name:24} build {build!s:>10}  pwd {pwd}  {desc}")
    windows = [(k, v.get("config", {}).get("oslist", ""), v.get("manifests", {}).get("public", {}))
               for k, v in depots.items() if k.isdigit()]
    print(f"depots: {[(k, os_) for k, os_, _ in windows]}")


if __name__ == "__main__":
    main()
