#!/usr/bin/env bash
# variant_run.sh -- migrate the founding save with a patched scratch copy of the tool, undo the one 1c-bis
# promotion that freezes the game on 987.11.8 (so the run reaches 988), and run it for N seconds.
# Used 2026-10-27 to bisect the crash just after 988.1.1 among part (c)'s pieces (stories, registries, ...).
#
# Usage: bash tests/one-offs/variant_run.sh <scratch folder holding a patched ck3_save_migrator/> <tag> [seconds]
set -u
SCR="$1"; TAG="$2"; SECS="${3:-300}"
P="$(cd "$(dirname "$0")/../.." && pwd)"
D="$P/private/data/play"
( cd "$SCR" && python -c "import ck3_save_migrator; print('tool loaded from', ck3_save_migrator.__file__)" && \
  python -m ck3_save_migrator migrate "$P/private/data/originals/save games/Arch-Abbot_Beidh_of_Omni_Church_Council_987_10_27_husband_died.ck3" \
    --rules all,R14,R15,R16 --reference "$P/private/data/originals/reference-1.20/ref_1_20_987_10_27.ck3" \
    --game-dir "E:/SteamLibrary/steamapps/common/Crusader Kings III/game" --old-game-dir "$P/private/data/versions/1.8.2/game" \
    --wos-shape faith -o "$D/$TAG.ck3" --no-lint > "$D/$TAG.txt" 2>&1 ) || { echo "migrate failed"; exit 2; }
cd "$P" || exit 1
python -I tests/one-offs/variant_undo_promotion.py "$D/$TAG.ck3" "$D/${TAG}_undo.ck3" || exit 3
bash tests/one-offs/bisect_hang.sh "$TAG" "$D/${TAG}_undo.ck3" "$SECS"
