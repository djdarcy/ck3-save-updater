"""face_round: one character's side-by-side sheet for a #40 judging round (the goal's S2 unit 7).

Each look is a launch_load_test run folder. From each, the last screenshot taken before the game was asked to close
(the "exit: WM_CLOSE posted" line in timeline.txt; else the last shot) is cropped to the HUD portrait and laid out
left to right with face_crop_compare.py. The sheet goes to private/data/faces/rounds/<round>/<character>.png, and
README.md in that folder gains one section per sheet naming each look's run, executable, save and shot, so a sheet
can always be traced back. The loop's reading of a sheet is written beside it (reading.md), never on the image.

Usage: python -I tests/one-offs/face_round.py <round> <character> <label>=<run dir>[@l,t,r,b] [...] [--scale S]
  box: the crop as fractions of the shot (default: 1.20's HUD portrait, 0.02,0.75,0.145,0.958)
"""
import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
ROUNDS = REPO / "private" / "data" / "faces" / "rounds"
HUD_120 = "0.02,0.75,0.145,0.958"


def secs(t: str) -> int:
    h, m, s = (int(x) for x in t.split(":"))
    return h * 3600 + m * 60 + s


def pick_shot(run: Path) -> tuple[Path, str]:
    shots = sorted((run / "shots").glob("*.webp"))
    if not shots:
        raise SystemExit(f"{run}: no shots")
    tl = (run / "timeline.txt").read_text(encoding="utf-8", errors="replace")
    launch = re.search(r"^\[(\d\d:\d\d:\d\d)\] launch:", tl, re.M)
    close = re.search(r"^\[(\d\d:\d\d:\d\d)\] exit: WM_CLOSE posted", tl, re.M)
    if launch and close:
        cut = secs(close.group(1)) - secs(launch.group(1))
        before = [s for s in shots if int(re.search(r"__(\d+)s", s.name).group(1)) < cut]
        if before:
            return before[-1], f"last shot before the close ({cut}s after launch)"
    return shots[-1], "last shot (no close recorded)"


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    rnd, who = argv[0], argv[1]
    scale = argv[argv.index("--scale") + 1] if "--scale" in argv else "1.0"
    looks = [a for a in argv[2:] if "=" in a and not a.startswith("--")]
    out_dir = ROUNDS / rnd
    out_dir.mkdir(parents=True, exist_ok=True)
    pairs, readme = [], [f"\n## {who} ({dt.datetime.now():%Y-%m-%d %H:%M})\n"]
    for spec in looks:
        label, rest = spec.split("=", 1)
        run_s, _, box = rest.partition("@")
        run = Path(run_s)
        shot, why = pick_shot(run)
        pairs.append(f"{label}={shot}@{box or HUD_120}")
        cmd = (run / "cmdline.txt").read_text(encoding="utf-8").strip() if (run / "cmdline.txt").exists() else "?"
        readme.append(f"- **{label}**: run `{run.name}`; {why}: `{shot.name}`; crop {box or HUD_120}; "
                      f"command `{cmd}`")
    sheet = out_dir / f"{who}.png"
    r = subprocess.run([sys.executable, "-I", str(HERE / "face_crop_compare.py"), str(sheet), scale, *pairs],
                       capture_output=True, text=True)
    print(r.stdout.strip() or r.stderr.strip()[-400:])
    if r.returncode != 0 or not sheet.is_file():
        return 1
    with open(out_dir / "README.md", "a", encoding="utf-8") as f:
        f.write("\n".join(readme) + f"\n- sheet: `{sheet.name}`\n")
    print(f"sheet {sheet}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
