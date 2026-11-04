#!/bin/bash
# The R19 acceptance (PR #39 with its --old-portrait-mods follow-up): the founding save through update with the play6
# recipe whose G1 is the witness-only restore (dna_witness_restore.py), both arms; expect play7 e31b5718 / 1289c61a.
# Run against the checkout (PYTHONPATH), never the editable install. Usage: play7_acceptance.sh <out-subfolder> [extra update args...]
# Moved from the 2026-11-03 session scratchpad (pr39acc/run_main.sh) for the #40 goal; the config (it trusts the play6
# recipe pack) lives in private/data/faces/acc/cfg/, outputs and the index cache under private/data/faces/acc/.
# Extra args (e.g. --face-changes fallback) go to both arms, so a candidate is the play7 recipe plus one change.
W="C:/code/ck3-save-migrator"
R="C:/code/ck3-save-migrator"
S="$R/private/data/faces/acc"
O="$S/${1:?out subfolder}"
shift
EXTRA=("$@")
mkdir -p "$O"
SAVE="$R/private/data/originals/save games/Arch-Abbot_Beidh_of_Omni_Church_Council_987_10_27_husband_died.ck3"
REF="$R/private/data/originals/reference-1.20/ref_1_20_987_10_27.ck3"
OLD="$R/private/data/versions/1.8.2/game"
M23="$R/private/data/originals/mods-2023"
FACES=(--old-game-dir "$OLD" --old-portrait-mods "$M23/cfp_3.1.11,$M23/epe_1.6.0" --portrait-mods 2220098919,2507209632,2996881191)
export CK3SM_CONFIG="$S/cfg/config.toml" CK3UPDATE_CACHE_DIR="$S/cache" PYTHONIOENCODING=utf-8 PYTHONPATH="$W"
cd "$W"
hashes() {
  [ -f "$1" ] || { echo "$2 NO OUTPUT"; return; }
  python -I -c "
import sys, hashlib; sys.path.insert(0, r'$W')
from ck3_save_migrator import savefile as sf
s = sf.read_save(sys.argv[1]); print(sys.argv[2], hashlib.sha256(s.gamestate).hexdigest()[:8], hashlib.sha256(s.meta).hexdigest()[:8])" "$1" "$2"
}
echo "== --rules all,R14,R15,R16"
python -m ck3_save_migrator update "$SAVE" --rules all,R14,R15,R16 "${FACES[@]}" "${EXTRA[@]}" --reference "$REF" \
  --wos-shape faith --allow-run -o "$O/rules.ck3" --no-record --plain -q; echo "exit=$?"
hashes "$O/rules.ck3" "rules:"
echo "== --transplant auto"
python -m ck3_save_migrator update "$SAVE" --transplant auto "${FACES[@]}" "${EXTRA[@]}" --reference "$REF" \
  --wos-shape faith --allow-run -o "$O/auto.ck3" --no-record --plain -q; echo "exit=$?"
hashes "$O/auto.ck3" "auto:"
echo "expect: e31b5718 1289c61a"
