#!/usr/bin/env bash
# bisect_hang.sh -- does a migrated save get past 987.11.8? Stages it as MIGRATE_TEST__bisect_<tag>, runs it in
# observer mode at speed with the portrait mods (autosaves guarded, dlc_load.json restored), and stacks the date
# area of every third screenshot into <run>/dates.png for a look. (2026-10-27: the playable save's sim thread loops
# forever on 987.11.8 over county c_kuzeytorg; this finds the first output that does it.)
#
# Usage: bash tests/one-offs/bisect_hang.sh <tag> <save.ck3> [seconds]
set -u
TAG="$1"; SAVE="$2"; SECS="${3:-240}"
cd "$(dirname "$0")/../.." || exit 1
SG="$HOME/Documents/Paradox Interactive/Crusader Kings III/save games"
cp "$SAVE" "$SG/MIGRATE_TEST__bisect_$TAG.ck3" && cmp "$SAVE" "$SG/MIGRATE_TEST__bisect_$TAG.ck3" || exit 2
python -I tests/one-offs/with_portrait_mods.py "bisect-$TAG" -- python -I tests/one-offs/launch_load_test.py "bisect-$TAG" \
  --h-console=observe --h-key=plus --h-key=plus --h-key=plus --h-key=plus --h-key=space --h-max="$SECS" \
  --h-guard-autosave -debug_mode "-loadsave=MIGRATE_TEST__bisect_$TAG.ck3" > "private/data/play/bisect_$TAG.txt" 2>&1
R=$(ls -d private/data/runs/*"bisect-$TAG" | tail -1)
python -I - "$R" <<'EOF'
import sys, glob
from PIL import Image
R = sys.argv[1]
fs = sorted(glob.glob(R + "/shots/[0-9]*.png") + glob.glob(R + "/shots/[0-9]*.webp"))
ims = []
for f in fs[2::3] or fs:
    im = Image.open(f); w, h = im.size
    ims.append(im.crop((int(w * 0.62), int(h * 0.93), int(w * 0.87), int(h * 0.99))))
out = Image.new("RGB", (ims[0].size[0], sum(i.size[1] for i in ims))); y = 0
for i in ims:
    out.paste(i, (0, y)); y += i.size[1]
out.save(R + "/dates.png")
EOF
grep -E "CRASH|stop:" "private/data/play/bisect_$TAG.txt" | tail -2
echo "dates: $R/dates.png"
