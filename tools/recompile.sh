#!/usr/bin/env bash
#
# recompile.sh — end-to-end: reference ROM -> native recompiled executable.
#
# Usage:
#   tools/recompile.sh                # build ROM, recompile, build native project
#   tools/recompile.sh --run          # ...then boot it headless for a few frames
#   tools/recompile.sh --rom X.gbc    # recompile an existing ROM instead of building one
#
# Prerequisites:
#   - RGBDS (for building the reference ROM from the disassembly)
#   - CMake 3.20+, Ninja, a C11/C++20 compiler, and SDL2 (for gbrecomp + runtime)
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

POKETCG="$REPO/vendor/poketcg"
GBRECOMP="$REPO/vendor/gb-recompiled"
GBRECOMP_BIN="$GBRECOMP/build/bin/gbrecomp"
ROM="$POKETCG/poketcg.gbc"
SYMBOLS="$POKETCG/poketcg.sym"
OUT="$REPO/build/recomp"
RUN=0
PATCH=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --rom) ROM="$(cd "$(dirname "$2")" && pwd)/$(basename "$2")"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --patch) PATCH="$(cd "$(dirname "$2")" && pwd)/$(basename "$2")"; shift 2 ;;
    --run) RUN=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

echo "==> [1/4] Reference ROM"
if [[ ! -f "$ROM" ]]; then
  echo "    building from disassembly (RGBDS)..."
  make -C "$POKETCG"
fi
echo "    ROM: $ROM"
shasum "$ROM" | sed 's/^/    /'

echo "==> [2/4] gbrecomp"
if [[ ! -x "$GBRECOMP_BIN" ]]; then
  echo "    building gb-recompiled..."
  cmake -G Ninja -B "$GBRECOMP/build" "$GBRECOMP"
  ninja -C "$GBRECOMP/build"
fi

echo "==> [3/4] Recompile ROM -> portable C"
if [[ -n "$PATCH" ]]; then
  echo "    applying native patch: $PATCH"
  "$GBRECOMP_BIN" "$ROM" --symbols "$SYMBOLS" --native-patch "$PATCH" -o "$OUT"
else
  "$GBRECOMP_BIN" "$ROM" --symbols "$SYMBOLS" -o "$OUT"
fi

echo "==> [4/4] Build native executable"
cmake -G Ninja -S "$OUT" -B "$OUT/build"
ninja -C "$OUT/build"

echo "    Done: $OUT/build/poketcg"

if [[ "$RUN" == "1" ]]; then
  echo "==> Booting headless (120 frames)..."
  "$OUT/build/poketcg" --headless --no-audio --limit-frames 120 \
    --dump-state "$OUT/boot-state.json"
  echo "    state written to $OUT/boot-state.json"
fi
