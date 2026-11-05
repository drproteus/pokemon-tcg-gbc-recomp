#!/usr/bin/env bash
#
# test_roundtrip.sh — prove the card translation layer is lossless across every
# editing surface: flat JSON, CSV (spreadsheets), and CastleDB (.cdb).
#
# For each path: encode -> decode -> compile -> reassemble, then assert the ROM
# SHA1 matches the original (byte-identical).
#
# Requires RGBDS + a C compiler (to rebuild the disassembly and its tools).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

TMP="$REPO/build/roundtrip"
rm -rf "$TMP"
mkdir -p "$TMP"

# A pristine copy of the disassembly, reused for every rebuild.
rsync -a \
  --exclude='.git' --exclude='*.o' --exclude='*.gbc' \
  --exclude='*.sym' --exclude='*.map' --exclude='*.patch' \
  vendor/poketcg/ "$TMP/poketcg/"

EXPECTED="$(head -1 vendor/poketcg/rom.sha1 | awk '{print $1}')"

check_asm() {
  local asm="$1"
  cp "$asm" "$TMP/poketcg/src/data/cards.asm"
  make -C "$TMP/poketcg" -j4 >/dev/null
  local actual
  actual="$(shasum "$TMP/poketcg/poketcg.gbc" | awk '{print $1}')"
  if [[ "$EXPECTED" == "$actual" ]]; then
    echo "  PASS: $EXPECTED"
  else
    echo "  FAIL: expected $EXPECTED got $actual" >&2
    exit 1
  fi
}

echo "==> [1/3] flat JSON"
python3 tools/extract_cards.py vendor/poketcg/src/data/cards.asm -o "$TMP/cards.json"
python3 tools/compile_cards.py "$TMP/cards.json" -o "$TMP/json.asm"
check_asm "$TMP/json.asm"

echo "==> [2/3] CSV (spreadsheet)"
python3 tools/spreadsheet.py json2csv "$TMP/cards.json" -o "$TMP/cards.csv"
python3 tools/spreadsheet.py csv2json "$TMP/cards.csv" -o "$TMP/cards_from_csv.json"
python3 tools/compile_cards.py "$TMP/cards_from_csv.json" -o "$TMP/csv.asm"
check_asm "$TMP/csv.asm"

echo "==> [3/3] CastleDB (.cdb)"
python3 tools/castledb.py json2cdb "$TMP/cards.json" -o "$TMP/cards.cdb"
python3 tools/castledb.py cdb2json "$TMP/cards.cdb" -o "$TMP/cards_from_cdb.json"
python3 tools/compile_cards.py "$TMP/cards_from_cdb.json" -o "$TMP/cdb.asm"
check_asm "$TMP/cdb.asm"

echo "All paths byte-identical."
