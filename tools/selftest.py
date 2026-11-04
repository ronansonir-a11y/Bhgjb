#!/usr/bin/env python3
"""
selftest.py — end-to-end smoke test of the analysis pipeline WITHOUT any Valve files.

Builds a tiny synthetic x86-64 PE32+ image (imports, exports, .pdata, delay-free)
that deliberately contains the blocker signals we look for, packs 10 copies under
the real depot paths, then runs validate_archive.py -> analyze_pe.py ->
gen_glue_inventory.py -> gen_touch_profile.py and asserts the results.

Run:  python tools/selftest.py
Used by .github/workflows/selftest.yml on every push.
"""
from __future__ import annotations

import json
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"

CRITICAL = [
    "game/bin/win64/dota2.exe",
    "game/bin/win64/engine2.dll",
    "game/bin/win64/rendersystemvulkan.dll",
    "game/bin/win64/filesystem_stdio.dll",
    "game/bin/win64/tier0.dll",
    "game/bin/win64/steam_api64.dll",
    "game/bin/win64/SDL3.dll",
    "game/dota/bin/win64/client.dll",
    "game/dota/bin/win64/server.dll",
    "game/dota/bin/win64/host.dll",
]

IMPORTS = {
    "kernel32.dll": ["LoadLibraryA", "LoadLibraryExW", "GetProcAddress",
                     "GetModuleHandleW", "VirtualAlloc", "VirtualProtect",
                     "CreateThread", "ExitProcess"],
    "ntdll.dll": ["RtlAddFunctionTable", "RtlLookupFunctionEntry",
                  "__C_specific_handler", "_CxxThrowException"],
    "vulkan-1.dll": ["vkGetInstanceProcAddr", "vkCreateWin32SurfaceKHR"],
    "steam_api64.dll": ["SteamAPI_Init"],
}


def make_synthetic_pe(is_dll: bool) -> bytes:
    """Minimal but structurally valid PE32+ with imports, exports and .pdata."""
    file_align, sect_align = 0x200, 0x1000
    hdr_size = 0x200
    rdata_rva, pdata_rva, text_rva = 0x2000, 0x3000, 0x1000
    rdata = bytearray(0x400)
    cursor = 0

    def alloc(blob: bytes, align: int = 4) -> int:
        nonlocal cursor
        cursor = (cursor + align - 1) & ~(align - 1)
        rva = rdata_rva + cursor
        rdata[cursor:cursor + len(blob)] = blob
        cursor += len(blob)
        return rva

    # Export directory (patched later).
    exp_rva = alloc(b"\x00" * 40)
    dll_name_rva = alloc(b"DOTA2_SELFTEST.dll\x00")
    export_name_rva = alloc(b"TestExport\x00")
    addr_funcs_rva = alloc(struct.pack("<I", text_rva))
    addr_names_rva = alloc(struct.pack("<I", export_name_rva))
    addr_ord_rva = alloc(struct.pack("<H", 0))
    struct.pack_into("<IIHHIIIIIII", rdata, exp_rva - rdata_rva,
                     0, 0, 0, 0, dll_name_rva, 1, 1, 1,
                     addr_funcs_rva, addr_names_rva, addr_ord_rva)

    # Hint/name tables and DLL-name strings.
    hintrva = {}
    for funcs in IMPORTS.values():
        for fn in funcs:
            hintrva[fn] = alloc(struct.pack("<H", 0) + fn.encode() + b"\x00", 2)
    dllname_rva = {d: alloc(d.encode() + b"\x00") for d in IMPORTS}

    # ILT / IAT pairs.
    tables = {}
    for dll, funcs in IMPORTS.items():
        vals = [hintrva[f] for f in funcs]
        if dll == "kernel32.dll":          # one ordinal import, too
            vals.append((1 << 63) | 123)
        vals.append(0)
        blob = b"".join(struct.pack("<Q", v) for v in vals)
        ilt = alloc(blob, 8)
        iat = alloc(blob, 8)
        tables[dll] = (ilt, iat)

    # Import descriptors + null terminator.
    desc_start = cursor
    for dll, (ilt, iat) in tables.items():
        alloc(struct.pack("<IIIII", ilt, 0, 0, dllname_rva[dll], iat))
    alloc(b"\x00" * 20)
    import_dir_size = cursor - desc_start

    pdata = bytearray(0x200)
    for i in range(2):
        struct.pack_into("<III", pdata, i * 12,
                         text_rva + i * 0x10, text_rva + (i + 1) * 0x10,
                         pdata_rva + 0x40)

    text = bytearray(0x200)
    # ret; call rel32; call [rip+disp32]; jmp [rip+disp32]; int3
    text[0:16] = bytes.fromhex("c3 e8 00000000 ff15 00000000 ff25 00000000 cc")

    # ── Headers ────────────────────────────────────────────────────────────
    dos = bytearray(0x80)
    struct.pack_into("<H", dos, 0, 0x5A4D)
    struct.pack_into("<I", dos, 0x3C, 0x80)
    pe_off = 0x80
    coff = struct.pack("<HHIIIHH", 0x8664, 3, 0, 0, 0, 240,
                       0x2102 if is_dll else 0x0022)
    opt = bytearray(240)
    struct.pack_into("<H", opt, 0, 0x20B)                 # PE32+
    opt[2], opt[3] = 14, 0
    struct.pack_into("<I", opt, 4, len(text))
    struct.pack_into("<I", opt, 8, len(rdata))
    struct.pack_into("<I", opt, 16, text_rva)             # entrypoint
    struct.pack_into("<I", opt, 20, text_rva)
    struct.pack_into("<Q", opt, 24, 0x140000000)
    struct.pack_into("<I", opt, 32, sect_align)
    struct.pack_into("<I", opt, 36, file_align)
    struct.pack_into("<H", opt, 40, 6)
    struct.pack_into("<H", opt, 48, 6)
    struct.pack_into("<I", opt, 56, 0x4000)               # SizeOfImage
    struct.pack_into("<I", opt, 60, hdr_size)
    struct.pack_into("<H", opt, 68, 2)                    # GUI
    struct.pack_into("<H", opt, 70, 0x0540)               # DYNAMIC_BASE|NX|GUARD_CF
    struct.pack_into("<Q", opt, 72, 0x100000)
    struct.pack_into("<Q", opt, 80, 0x1000)
    struct.pack_into("<Q", opt, 88, 0x100000)
    struct.pack_into("<Q", opt, 96, 0x1000)
    struct.pack_into("<I", opt, 108, 16)                  # NumberOfRvaAndSizes
    dd = 112
    struct.pack_into("<II", opt, dd + 0 * 8, exp_rva, 40)                 # EXPORT
    struct.pack_into("<II", opt, dd + 1 * 8, rdata_rva + desc_start, import_dir_size)
    struct.pack_into("<II", opt, dd + 3 * 8, pdata_rva, 24)               # EXCEPTION

    def shdr(name, vsize, vaddr, rawsize, rawptr, chars):
        return (name.encode().ljust(8, b"\x00") +
                struct.pack("<IIIIIIHHI", vsize, vaddr, rawsize, rawptr,
                            0, 0, 0, 0, chars))

    sections = b"".join([
        shdr(".text", len(text), text_rva, 0x200, 0x200, 0x60000020),
        shdr(".rdata", len(rdata), rdata_rva, 0x400, 0x400, 0x40000040),
        shdr(".pdata", 24, pdata_rva, 0x200, 0x800, 0x40000040),
    ])
    headers = bytes(dos) + b"PE\0\0" + coff + bytes(opt) + sections
    headers = headers.ljust(hdr_size, b"\x00")

    out = bytearray(0xA00)
    out[0:hdr_size] = headers
    out[0x200:0x200 + len(text)] = text
    out[0x400:0x400 + len(rdata)] = rdata
    out[0x800:0x800 + len(pdata)] = pdata
    return bytes(out)


def run(cmd: list[str]) -> None:
    print("[selftest] $", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=ROOT)


def main() -> int:
    py = sys.executable
    with tempfile.TemporaryDirectory(prefix="dota2-selftest-") as td:
        tmp = Path(td)
        blob_exe = make_synthetic_pe(False)
        blob_dll = make_synthetic_pe(True)
        zpath = tmp / "selftest-bins.zip"
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in CRITICAL:
                zf.writestr(p, blob_exe if p.endswith(".exe") else blob_dll)
        report = tmp / "report"
        run([py, str(TOOLS / "validate_archive.py"), "--zip", str(zpath),
             "--out", str(report), "--strict"])
        run([py, str(TOOLS / "analyze_pe.py"), "--input", str(zpath),
             "--out", str(report), "--deep",
             "--manifest", str(ROOT / "data/depot-373303-2026-11-03.tsv")])
        run([py, str(TOOLS / "gen_glue_inventory.py"),
             "--analysis", str(report / "pe-analysis.json"), "--out", str(report)])
        run([py, str(TOOLS / "gen_touch_profile.py"), "--out", str(tmp / "assets")])

        analysis = json.loads((report / "pe-analysis.json").read_text())
        s = analysis["summary"]
        assert s["module_count"] == 10, s["module_count"]
        assert s["pe32plus_amd64_count"] == 10, s["pe32plus_amd64_count"]
        assert s["total_import_thunks"] >= 10 * 15, s["total_import_thunks"]
        assert s["total_exception_entries"] == 20, s["total_exception_entries"]
        for group in ("dynamic_loading", "seh_eh", "jit_wx", "vulkan"):
            assert s["blocker_signals"].get(group), f"missing blocker signal {group}"
        assert "vkGetInstanceProcAddr" in s["vulkan_entrypoints"]
        assert (report / "glue-stubs.h").exists()
        assert (report / "import-graph.dot").exists()
        assert (tmp / "assets/controls.icp").exists()
        icp = json.loads((tmp / "assets/controls.icp").read_text())
        assert len(icp["elements"]) >= 20
        ours = json.loads((tmp / "assets/controls.json").read_text())
        assert any(c["binding"] == "MOUSE_RIGHT_BUTTON" for c in ours["controls"])
        print("[selftest] PASS — pipeline works on synthetic PE32+ data", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
