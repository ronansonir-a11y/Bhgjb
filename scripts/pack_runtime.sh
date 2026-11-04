#!/usr/bin/env bash
# Repacks pinned third-party runtime components into TWO plain ZIP files that an
# Android app can extract with java.util.zip (no 7z/zstd decoder on the phone).
#
# Usage: RELEASE_BASE=https://github.com/O/R/releases/download/mobile/ \
#        bash scripts/pack_runtime.sh dist
#
# NEVER includes Valve game files. Sources come from runtime/sources.json.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-dist}"
RELEASE_BASE="${RELEASE_BASE:-https://github.com/ronansonir-a11y/Bhgjb/releases/download/mobile/}"
mkdir -p "$OUT"
WORK="$(mktemp -d)"
mkdir -p "$WORK/core" "$WORK/goldberg" "$WORK/apk"
PACK_OK=1

url_of() {
  python3 - "$1" <<'PY'
import json, sys
j = json.load(open('runtime/sources.json'))
for c in j['components']:
    if c['id'] == sys.argv[1]:
        print(c['url']); break
PY
}
cd "$ROOT"

WINLATOR_URL="$(url_of winlator-apk)"
GOLDBERG_URL="$(url_of goldberg)"

LICENSE_TEXT='Third-party open-source components, redistributed under their own licences.
No Valve game files are included in this archive.

- Winlator (brunodev85/winlator) .......... LGPL-2.1, https://github.com/brunodev85/winlator
- Wine / glibc rootfs from Winlator ....... LGPL-2.1 / LGPL-2.1+
- Box64 (ptitSeb/box64) ................... MIT, https://github.com/ptitSeb/box64
- Mesa Turnip / Vortek (brunodev85) ....... MIT / LGPL-2.1
- Goldberg Steam Emulator (Detanup01/gbe_fork) ... LGPL-3.0, https://github.com/Detanup01/gbe_fork

See docs/06-LEGAL-AND-RISKS.md. These are compatibility research artefacts,
NOT a Dota 2 distribution. The game content must be supplied by the user.
'
printf '%s\n' "$LICENSE_TEXT" > "$WORK/core/LICENSES.txt"
printf '%s\n' "$LICENSE_TEXT" > "$WORK/goldberg/LICENSES.txt"

# ---- 1. Winlator APK -> unpack .tzst -> plain directory tree -----------------
echo "[pack] downloading Winlator APK ($WINLATOR_URL)"
if curl -fL --retry 3 --connect-timeout 25 -o "$WORK/winlator.apk" "$WINLATOR_URL"; then
  unzip -oq "$WORK/winlator.apk" 'assets/*' -d "$WORK/apk" 2>/dev/null || true
  count=0
  while IFS= read -r tz; do
    [ -z "$tz" ] && continue
    name="$(basename "$tz" .tzst)"
    mkdir -p "$WORK/core/$name"
    if tar --zstd -xf "$tz" -C "$WORK/core/$name" 2>/dev/null; then
      echo "[pack]   unpacked $name"
    elif command -v unzstd >/dev/null && tar -I unzstd -xf "$tz" -C "$WORK/core/$name" 2>/dev/null; then
      echo "[pack]   unpacked $name (unzstd)"
    else
      echo "[pack]   WARN cannot unpack $name, keeping .tzst as-is"
      cp "$tz" "$WORK/core/$name/"
    fi
    count=$((count + 1))
    [ "$count" -ge 12 ] && break
  done < <(find "$WORK/apk" -name '*.tzst' -type f | sort)
  echo "[pack] Winlator components: $count"
  [ "$count" -eq 0 ] && PACK_OK=0
else
  echo "[pack] WARN Winlator download failed"
  echo "Winlator runtime components could not be downloaded during this build." \
      > "$WORK/core/DOWNLOAD-FAILED.txt"
  PACK_OK=0
fi

# ---- 2. Goldberg 7z -> steam_api64.dll + steam_settings --------------------
echo "[pack] downloading Goldberg ($GOLDBERG_URL)"
if curl -fL --retry 3 --connect-timeout 25 -o "$WORK/goldberg.7z" "$GOLDBERG_URL" \
   && (command -v 7z >/dev/null || command -v 7za >/dev/null); then
  SEVEN="$(command -v 7z || command -v 7za)"
  "$SEVEN" x -y -o"$WORK/gb" "$WORK/goldberg.7z" >/dev/null 2>&1 || true
  find "$WORK/gb" -type f -name 'steam_api64.dll' -exec cp {} "$WORK/goldberg/" \; 2>/dev/null
  find "$WORK/gb" -type f -name 'steam_interfaces.txt' -exec cp {} "$WORK/goldberg/" \; 2>/dev/null
  find "$WORK/gb" -type d -name 'steam_settings*' -exec cp -r {} "$WORK/goldberg/settings/" \; 2>/dev/null || true
  echo "[pack] Goldberg files: $(find "$WORK/goldberg" -type f | wc -l)"
else
  echo "[pack] WARN Goldberg download/extract failed"
  echo "Goldberg steam_api64.dll could not be fetched. The app still builds." \
      > "$WORK/goldberg/DOWNLOAD-FAILED.txt"
  PACK_OK=0
fi

# ---- 3. ZIP + manifest ------------------------------------------------------
( cd "$WORK/core" && zip -qr "$ROOT/$OUT/dota2-runtime-core.zip" . )
( cd "$WORK/goldberg" && zip -qr "$ROOT/$OUT/dota2-goldberg.zip" . )

RELEASE_BASE="$RELEASE_BASE" PACK_OK="$PACK_OK" python3 - "$OUT" <<'PY'
import hashlib, json, os, sys, time
from pathlib import Path
out = Path(sys.argv[1]); base = os.environ['RELEASE_BASE']
assets = []
for aid, name in [('runtime-core', 'dota2-runtime-core.zip'),
                  ('goldberg', 'dota2-goldberg.zip')]:
    p = out / name
    h = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else ''
    assets.append({'id': aid, 'name': name, 'url': base + name,
                   'sha256': h, 'bytes': p.stat().st_size if p.exists() else 0})
manifest = {'schema': 1, 'generated': int(time.time()),
            'ok': os.environ['PACK_OK'] == '1',
            'note': 'Third-party OSS runtime only. NO Valve files.',
            'assets': assets}
(out / 'dota2-runtime-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print('[pack] manifest:', json.dumps(manifest, indent=2))
PY

echo "[pack] done -> $OUT"
ls -lh "$OUT"
rm -rf "$WORK"
exit 0
