#!/system/bin/sh
# Dota 2 container bootstrap. Executed by RuntimeBootstrap.java via `sh bootstrap.sh`.
# It does NOT contain any Valve code; all paths are user-supplied.
set -u

log() { echo "[dota2] $*" >&2; }

: "${RUNTIME_DIR:?RUNTIME_DIR is not set}"
: "${GAME_ROOT:?GAME_ROOT is not set}"
: "${DOTA_EXE:?DOTA_EXE is not set}"
: "${DOTA_ARGS:=}"
: "${DOTA_LOG:=}"

log "------------------------------------------------------------"
log "ABI          : $(getprop ro.product.cpu.abi 2>/dev/null || echo unknown)"
log "Android      : $(getprop ro.build.version.release 2>/dev/null || echo unknown)"
log "GAME_ROOT    : $GAME_ROOT"
log "DOTA_EXE     : $DOTA_EXE"
log "DOTA_ARGS    : $DOTA_ARGS"
log "RUNTIME_DIR  : $RUNTIME_DIR"
log "WINEPREFIX   : ${WINEPREFIX:-<unset>}"
log "VK_ICD       : ${VK_ICD_FILENAMES:-<system>}"
log "------------------------------------------------------------"

# ---- Preflight ---------------------------------------------------------------
if [ ! -f "$DOTA_EXE" ]; then
    log "FATAL: dota2.exe not found. Copy the full game to /sdcard/Dota2/."
    log "See docs/04-FILE-MANIFEST.md (section 3)."
    exit 12
fi

if [ ! -f "$RUNTIME_DIR/rootfs.tzst" ] && [ ! -d "$RUNTIME_DIR/rootfs" ]; then
    log "FATAL: Wine/glibc rootfs.tzst missing."
    log "Run build-apk.yml with bundle_runtime=true, or unpack Winlator's"
    log "rootfs.tzst + container_pattern.tzst into assets/runtime/ manually."
    exit 10
fi

if [ ! -x "$RUNTIME_DIR/bin/box64" ]; then
    log "FATAL: $RUNTIME_DIR/bin/box64 missing or not executable."
    log "Expected the Box64 arm64 build from Winlator's box64-0.4.4.tzst."
    exit 11
fi

WINE64="${WINE64:-$RUNTIME_DIR/wine/bin/wine64}"
if [ ! -x "$WINE64" ]; then
    log "FATAL: $WINE64 missing."
    log "A 'minimal Wine PE loader' cannot boot Source 2: hundreds of builtin"
    log "Win32 DLLs are required (see docs/03-PATH-B-CONTAINER.md section 1)."
    exit 13
fi

if [ ! -f "$RUNTIME_DIR/vortek_icd.aarch64.json" ]; then
    log "WARN : Vortek ICD manifest not found; system Vulkan ICD will be used."
    log "       vkCreateWin32SurfaceKHR needs the Win32->Android WSI shim (M5)."
fi

# ---- Environment -------------------------------------------------------------
export WINEARCH="${WINEARCH:-win64}"
export WINEDEBUG="${WINEDEBUG:--all}"
export WINEPREFIX="${WINEPREFIX:-$RUNTIME_DIR/prefix}"
export BOX64_DYNAREC="${BOX64_DYNAREC:-1}"
export BOX64_DYNAREC_BIGBLOCK="${BOX64_DYNAREC_BIGBLOCK:-1}"
if [ -d "$RUNTIME_DIR/rootfs/usr/lib" ]; then
    export LD_LIBRARY_PATH="$RUNTIME_DIR/rootfs/usr/lib:${LD_LIBRARY_PATH:-}"
fi

mkdir -p "$WINEPREFIX" 2>/dev/null || true

# ---- Launch ------------------------------------------------------------------
# NOTE: $DOTA_ARGS is intentionally unquoted: these are separate argv tokens.
# shellcheck disable=SC2086
log "exec: $RUNTIME_DIR/bin/box64 $WINE64 $DOTA_EXE $DOTA_ARGS"
exec "$RUNTIME_DIR/bin/box64" "$WINE64" "$DOTA_EXE" $DOTA_ARGS
