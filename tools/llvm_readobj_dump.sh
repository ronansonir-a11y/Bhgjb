#!/usr/bin/env bash
# Independent cross-check of the pefile-based analysis with LLVM's llvm-readobj.
# Usage: tools/llvm_readobj_dump.sh <archive.zip> <output-dir>
set -uo pipefail

ZIP="${1:?usage: llvm_readobj_dump.sh <zip> <outdir>}"
OUT="${2:?usage: llvm_readobj_dump.sh <zip> <outdir>}"
mkdir -p "$OUT"

READOBJ="$(command -v llvm-readobj || true)"
if [ -z "$READOBJ" ]; then
  READOBJ="$(ls /usr/bin/llvm-readobj-* 2>/dev/null | sort -V | tail -1 || true)"
fi
if [ -z "$READOBJ" ] || [ ! -x "$READOBJ" ]; then
  echo "llvm-readobj is unavailable; pefile report in report/pe-analysis.json is authoritative." \
      > "$OUT/README.txt"
  echo "[llvm-readobj] unavailable, skipped"
  exit 0
fi

echo "llvm-readobj: $READOBJ" > "$OUT/README.txt"
"$READOBJ" --version >> "$OUT/README.txt" 2>&1 || true

KEYS=(
  "game/bin/win64/dota2.exe"
  "game/bin/win64/engine2.dll"
  "game/bin/win64/rendersystemvulkan.dll"
  "game/bin/win64/rendersystemdx11.dll"
  "game/bin/win64/tier0.dll"
  "game/bin/win64/steam_api64.dll"
  "game/dota/bin/win64/client.dll"
  "game/dota/bin/win64/server.dll"
  "game/dota/bin/win64/host.dll"
)

for key in "${KEYS[@]}"; do
  name="$(basename "$key")"
  tmp="$(mktemp)"
  if unzip -p "$ZIP" "$key" > "$tmp" 2>/dev/null && [ -s "$tmp" ]; then
    "$READOBJ" \
      --file-headers --sections \
      --coff-imports --coff-exports --coff-basereloc \
      --coff-debug-directory --coff-load-config --coff-tls-directory \
      "$tmp" > "$OUT/$name.readobj.txt" 2>&1 || \
      echo "[llvm-readobj] partial failure for $name" >> "$OUT/README.txt"
    # Some LLVM builds lack individual COFF flags; retry with a minimal set.
    if [ ! -s "$OUT/$name.readobj.txt" ]; then
      "$READOBJ" --file-headers "$tmp" > "$OUT/$name.readobj.txt" 2>&1 || true
    fi
    echo "[llvm-readobj] $name -> $name.readobj.txt"
  else
    echo "[llvm-readobj] missing in archive: $key" | tee -a "$OUT/README.txt"
  fi
  rm -f "$tmp"
done
