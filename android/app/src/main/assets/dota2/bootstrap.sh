#!/system/bin/sh
# Dota 2 container bootstrap. Executed by ContainerSession.java via `sh bootstrap.sh`.
# Contains NO Valve code. All paths come from the user or the runtime installer.
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
log "DISPLAY      : ${DISPLAY:-<unset>}"
log "------------------------------------------------------------"

# ---- Autodiscover the components unpacked by RuntimeInstaller ----------------
find_one() {
    find "$RUNTIME_DIR" -type f -name "$1" 2>/dev/null | head -1
}

BOX64="$(find_one box64)"
WINE64="$(find_one wine64)"
[ -z "$WINE64" ] && WINE64="$(find_one wine)"
ROOTFS="$(find "$RUNTIME_DIR" -type d -name rootfs 2>/dev/null | head -1)"
XSERVER="$(find_one Xvfb)"
[ -z "$XSERVER" ] && XSERVER="$(find_one XServer)"
ICD="$(find "$RUNTIME_DIR" -type f -name 'vortek_icd*.json' 2>/dev/null | head -1)"

log "box64        : ${BOX64:-<MISSING>}"
log "wine64       : ${WINE64:-<MISSING>}"
log "rootfs       : ${ROOTFS:-<MISSING>}"
log "XServer      : ${XSERVER:-<MISSING>}"
log "Vulkan ICD   : ${ICD:-<system>}"

# ---- Preflight ---------------------------------------------------------------
if [ ! -f "$DOTA_EXE" ]; then
    log "FATAL: dota2.exe not found at $DOTA_EXE"
    log "Use the DEMO button (no files needed), or 'Загрузить контент' with your"
    log "own private ZIP of 'dota 2 beta'. See docs/07-MOBILE-ONLY.md."
    exit 12
fi

if [ ! -f "$RUNTIME_DIR/installed.json" ]; then
    log "FATAL: runtime not installed. Tap 'Скачать рантайм' in the menu."
    exit 10
fi

if [ -z "$BOX64" ] || [ ! -x "$BOX64" ]; then
    log "FATAL: box64 missing or not executable."
    log "Expected an arm64 Box64 binary inside dota2-runtime-core.zip."
    exit 11
fi

if [ -z "$WINE64" ] || [ ! -x "$WINE64" ]; then
    log "FATAL: wine64 missing."
    log "A 'minimal Wine PE loader' cannot boot Source 2: hundreds of builtin"
    log "Win32 DLLs are required (see docs/03-PATH-B-CONTAINER.md)."
    exit 13
fi

if [ -z "$XSERVER" ]; then
    log "WARN : no Xvfb/XServer binary in the runtime bundle. Winlator implements"
    log "       its XServer in Java; without a display server Wine GUI will not"
    log "       create an HWND. This is milestone M4, not a missing flag."
fi

# ---- Environment -------------------------------------------------------------
export WINEARCH="${WINEARCH:-win64}"
export WINEDEBUG="${WINEDEBUG:--all}"
export WINEPREFIX="${WINEPREFIX:-$RUNTIME_DIR/prefix}"
export DISPLAY="${DISPLAY:-:0}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-$RUNTIME_DIR/xdg}"
export BOX64_DYNAREC="${BOX64_DYNAREC:-1}"
export BOX64_DYNAREC_BIGBLOCK="${BOX64_DYNAREC_BIGBLOCK:-1}"
[ -n "$ICD" ] && export VK_ICD_FILENAMES="$ICD"
if [ -n "$ROOTFS" ]; then
    for lib in "$ROOTFS/usr/lib" "$ROOTFS/lib" "$ROOTFS/usr/lib/aarch64-linux-gnu"; do
        [ -d "$lib" ] && export LD_LIBRARY_PATH="$lib:${LD_LIBRARY_PATH:-}"
    done
fi
mkdir -p "$WINEPREFIX" "$XDG_RUNTIME_DIR" 2>/dev/null || true

# ---- Optional display server -------------------------------------------------
if [ -n "$XSERVER" ] && [ -x "$XSERVER" ]; then
    "$XSERVER" :0 -screen 0 1280x720x24 >/dev/null 2>&1 &
    sleep 1
    log "started $XSERVER on :0"
fi

# ---- Launch ------------------------------------------------------------------
# $DOTA_ARGS is intentionally unquoted: separate argv tokens.
# shellcheck disable=SC2086
log "exec: $BOX64 $WINE64 $DOTA_EXE $DOTA_ARGS"
log "NOTE: vkCreateWin32SurfaceKHR -> ANativeWindow WSI thunk (M5) is not bundled;"
log "      a Vulkan surface will fail without Vortek/FEX thunking."
exec "$BOX64" "$WINE64" "$DOTA_EXE" $DOTA_ARGS
