#!/usr/bin/env python3
"""
analyze_pe.py — PE32+ import/export/ABI reconnaissance for the Dota 2 win64 depot.

Purpose (stages 0 of both Path A and Path B):
  * inventory every x86-64 PE in the user-supplied archive;
  * measure the real Win32 / CRT / Vulkan / Steam API surface that any
    recompiler glue (Path A) or Wine container (Path B) has to answer;
  * find the concrete blockers: SEH/.pdata, dynamic loading, JIT/W^X,
    cross-DLL late binding, delay imports, CFG, exported-Source2 interfaces.

It never modifies the input binaries and never emits game code.

Usage:
  python tools/analyze_pe.py --input assets/incoming/dota2-win64-bins.zip \
      --manifest data/depot-373303-2026-11-03.tsv --out report --deep
  python tools/analyze_pe.py --input /tmp/extracted --out report

Outputs (all plain text, safe to commit):
  report/pe-analysis.json     full structured inventory
  report/PE-REPORT.md         human-readable summary + blocker signals
  report/import-graph.dot     Graphviz graph of the internal DLL dependency web
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

try:
    import pefile
except ImportError:
    sys.exit("pefile is required: pip install -r tools/requirements.txt")

PE32PLUS_MAGIC = 0x20B
AMD64_MACHINE = 0x8664

KEY_MODULES = [
    "dota2.exe", "engine2.dll", "rendersystemvulkan.dll", "rendersystemdx11.dll",
    "client.dll", "server.dll", "host.dll", "tier0.dll", "steam_api64.dll",
    "filesystem_stdio.dll", "panorama.dll", "v8.dll", "SDL3.dll",
]

# API families whose presence determines the amount of glue / Wine work.
CATEGORY_PATTERNS = [
    ("win32-core", re.compile(r"^(kernel32|kernelbase|ntdll|user32|advapi32|ole32|oleaut32|shell32|shlwapi|gdi32|ws2_32|wininet|crypt32|bcrypt|secur32|setupapi|version|winmm|imm32|comdlg32|comctl32|psapi|iphlpapi|dwmapi|uxtheme|dbghelp|msvcrt|ucrtbase|vcruntime140|vcruntime140_1|msvcp140|msvcp140_1|msvcp140_2|concrt140)\.dll$", re.I)),
    ("graphics-vulkan", re.compile(r"^(vulkan-1|vulkan|libvulkan|vk_swiftshader|vortek)\.dll$", re.I)),
    ("graphics-d3d", re.compile(r"^(d3d11|d3d12|d3d9|d3dcompiler_47|dxgi|dxcompiler|dxil|vfx_dx11|rendersystemdx11)\.dll$", re.I)),
    ("steam", re.compile(r"^(steam_api64|steamclient64|steamnetworkingsockets|steamaudio|tier0_s)\.dll$", re.I)),
    ("source2-internal", re.compile(r"^(engine2|tier0|vstdlib|filesystem_stdio|materialsystem2|meshsystem|resourcesystem|scenesystem|soundsystem|networksystem|inputsystem|schemasystem|panorama|panorama_text_pango|particles|worldrenderer|vphysics2|vscript|v8system|v8|localize|pulse_system|animationsystem|navsystem|host|client|server|dota2)\.(dll|exe)$", re.I)),
    ("third-party", re.compile(r"^(qt5.*|lib.*|phonon.*|embree3|amd_ags_x64|ati_compress_wrapper|gfsdk_aftermath_lib\.x64|cairo|p4lib|symsrv|dbghelp|SDL3|valve_.*|vconsole2|assetpreview|resourcecompiler|physicsbuilder|toolframework2|visbuilder|propertyeditor|scenefilecache|helpsystem|imemanager|bugreporter_filequeue|vconcomm)\.dll$", re.I)),
]

BLOCKER_APIS = {
    "dynamic_loading": ["LoadLibraryA", "LoadLibraryW", "LoadLibraryExA", "LoadLibraryExW",
                        "GetProcAddress", "GetModuleHandleA", "GetModuleHandleW",
                        "GetModuleHandleExA", "GetModuleHandleExW", "LdrLoadDll",
                        "LdrGetProcedureAddress", "FreeLibrary"],
    "seh_eh": ["__C_specific_handler", "__CxxFrameHandler3", "__CxxFrameHandler4",
               "_CxxThrowException", "RtlAddFunctionTable", "RtlDeleteFunctionTable",
               "RtlLookupFunctionEntry", "RtlUnwindEx", "RtlVirtualUnwind",
               "RtlInstallFunctionTableCallback", "RaiseException",
               "SetUnhandledExceptionFilter", "AddVectoredExceptionHandler"],
    "jit_wx": ["VirtualAlloc", "VirtualAllocEx", "VirtualProtect", "VirtualProtectEx",
               "VirtualQuery", "MapViewOfFile", "MapViewOfFileEx", "FlushInstructionCache",
               "NtProtectVirtualMemory", "CreateFileMappingW"],
    "vulkan": ["vkGetInstanceProcAddr", "vkGetDeviceProcAddr", "vkCreateInstance",
               "vkCreateWin32SurfaceKHR", "vkCreateAndroidSurfaceKHR", "vkEnumerateInstanceExtensionProperties",
               "vkEnumerateDeviceExtensionProperties", "vkCreateDevice", "vkGetPhysicalDeviceSurfaceSupportKHR"],
    "threading_tls": ["CreateThread", "CreateThreadpoolWork", "TlsAlloc", "TlsSetValue",
                      "FlsAlloc", "InitOnceExecuteOnce", "GetCurrentThreadId",
                      "SetThreadContext", "GetThreadContext", "RtlCaptureContext"],
    "panel_jit": ["v8::", "JSC", "luaL_", "sqlite3_"],
}

DIR_NAMES = [
    "IMAGE_DIRECTORY_ENTRY_EXPORT", "IMAGE_DIRECTORY_ENTRY_IMPORT",
    "IMAGE_DIRECTORY_ENTRY_EXCEPTION", "IMAGE_DIRECTORY_ENTRY_RESOURCE",
    "IMAGE_DIRECTORY_ENTRY_SECURITY", "IMAGE_DIRECTORY_ENTRY_BASERELOC",
    "IMAGE_DIRECTORY_ENTRY_DEBUG", "IMAGE_DIRECTORY_ENTRY_TLS",
    "IMAGE_DIRECTORY_ENTRY_LOAD_CONFIG", "IMAGE_DIRECTORY_ENTRY_BOUND_IMPORT",
    "IMAGE_DIRECTORY_ENTRY_IAT", "IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT",
    "IMAGE_DIRECTORY_ENTRY_COM_DESCRIPTOR",
]


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def human(n: int) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024 or unit == "GiB":
            return f"{n:.2f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024.0
    return str(n)


def parse_manifest(path: Path) -> dict[str, int]:
    out = {}
    if not path or not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 4:
            out[parts[0].strip()] = int(parts[3])
    return out


def categorize(dll: str) -> str:
    for name, rx in CATEGORY_PATTERNS:
        if rx.match(dll):
            return name
    return "other"


def extract_input(input_path: Path, workdir: Path) -> Path:
    """Return a directory of PE files. ZIPs are extracted with a zip-slip guard."""
    if input_path.is_dir():
        return input_path
    if input_path.suffix.lower() != ".zip":
        sys.exit(f"Unsupported input (need a directory or .zip): {input_path}")
    root = workdir / "extracted"
    root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(input_path) as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/").lstrip("/")
            parts = [p for p in name.split("/") if p not in ("", ".", "..")]
            if not parts or ".." in name.split("/"):
                continue
            if not name.lower().endswith((".dll", ".exe", ".txt", ".inf", ".gi")):
                continue
            dest = root.joinpath(*parts)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, dest.open("wb") as dst:
                while True:
                    chunk = src.read(1 << 20)
                    if not chunk:
                        break
                    dst.write(chunk)
    return root


def deep_stats(pe, max_text_bytes: int) -> dict:
    """Linear-sweep estimate of .text complexity. Heuristic: linear sweep can
    desynchronise on data-in-code; treat all numbers as orders of magnitude."""
    stats = {"method": "capstone linear sweep (.text), approximate",
             "instructions": 0, "direct_calls": 0, "indirect_calls": 0,
             "indirect_jumps": 0, "returns": 0, "int3": 0,
             "swept_bytes": 0, "truncated": False}
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_64
    except ImportError:
        stats["error"] = "capstone not installed"
        return stats
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = False
    text = None
    for s in pe.sections:
        nm = s.Name.rstrip(b"\x00").decode("ascii", "replace").lower()
        if nm == ".text":
            text = s.get_data()
            break
    if text is None:
        stats["error"] = "no .text section"
        return stats
    if len(text) > max_text_bytes:
        text = text[:max_text_bytes]
        stats["truncated"] = True
    stats["swept_bytes"] = len(text)
    va = pe.OPTIONAL_HEADER.ImageBase + next(
        s.VirtualAddress for s in pe.sections
        if s.Name.rstrip(b"\x00").decode("ascii", "replace").lower() == ".text")
    for insn in md.disasm(text, va):
        stats["instructions"] += 1
        m = insn.mnemonic
        raw = insn.bytes
        if m == "call" and raw[:1] == b"\xe8":
            stats["direct_calls"] += 1
        elif m in ("call", "jmp") and raw[:1] == b"\xff":
            modrm = raw[1] if len(raw) > 1 else 0
            reg = (modrm >> 3) & 7
            if reg == 2 and m == "call":
                stats["indirect_calls"] += 1
            elif reg == 4 and m == "jmp":
                stats["indirect_jumps"] += 1
        elif m.startswith("ret"):
            stats["returns"] += 1
        elif m == "int3":
            stats["int3"] += 1
    return stats


def analyze_file(path: Path, rel: str, expected_sizes: dict, deep: bool,
                 max_text_bytes: int) -> dict:
    rec = {"path": rel, "size_bytes": path.stat().st_size, "sha256": sha256_of(path),
           "warnings": []}
    if rel in expected_sizes and expected_sizes[rel] != rec["size_bytes"]:
        rec["warnings"].append(
            f"size differs from the 2026-11-03 SteamDB snapshot "
            f"({expected_sizes[rel]} expected) — Valve shipped a newer build")
    with path.open("rb") as f:
        if f.read(2) != b"MZ":
            rec["warnings"].append("not a PE image (MZ missing)")
            return rec
    try:
        pe = pefile.PE(str(path), fast_load=True)
    except Exception as exc:  # noqa: BLE001 - report, never crash the pipeline
        rec["warnings"].append(f"pefile failed: {exc}")
        return rec
    rec["machine"] = hex(pe.FILE_HEADER.Machine)
    rec["is_amd64"] = pe.FILE_HEADER.Machine == AMD64_MACHINE
    rec["magic"] = hex(pe.OPTIONAL_HEADER.Magic)
    rec["is_pe32plus"] = pe.OPTIONAL_HEADER.Magic == PE32PLUS_MAGIC
    rec["is_dll"] = bool(pe.FILE_HEADER.Characteristics & 0x2000)
    rec["image_base"] = hex(pe.OPTIONAL_HEADER.ImageBase)
    rec["entrypoint_rva"] = hex(pe.OPTIONAL_HEADER.AddressOfEntryPoint)
    rec["size_of_image"] = pe.OPTIONAL_HEADER.SizeOfImage
    rec["subsystem"] = pe.OPTIONAL_HEADER.Subsystem
    rec["dll_characteristics"] = hex(pe.OPTIONAL_HEADER.DllCharacteristics)
    rec["timestamp"] = pe.FILE_HEADER.TimeDateStamp
    rec["number_of_sections"] = pe.FILE_HEADER.NumberOfSections
    if not (rec["is_amd64"] and rec["is_pe32plus"]):
        rec["warnings"].append("NOT x86-64 PE32+ — this depot should be pure win64")

    dirs = {}
    for name in DIR_NAMES:
        idx = pefile.DIRECTORY_ENTRY[name]
        d = pe.OPTIONAL_HEADER.DATA_DIRECTORY[idx]
        dirs[name.replace("IMAGE_DIRECTORY_ENTRY_", "").lower()] = {
            "rva": d.VirtualAddress, "size": d.Size}
    rec["directories"] = dirs
    try:
        wanted = [pefile.DIRECTORY_ENTRY[n] for n in DIR_NAMES]
        pe.parse_data_directories(directories=wanted)
    except Exception as exc:  # noqa: BLE001
        rec["warnings"].append(f"partial data-directory parse: {exc}")

    rec["sections"] = []
    for s in pe.sections:
        rec["sections"].append({
            "name": s.Name.rstrip(b"\x00").decode("ascii", "replace"),
            "virtual_size": s.Misc_VirtualSize, "raw_size": s.SizeOfRawData,
            "virtual_address": hex(s.VirtualAddress),
            "characteristics": hex(s.Characteristics),
        })

    imports = []
    for entry in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []) or []:
        dll = entry.dll.decode("utf-8", "replace") if isinstance(entry.dll, bytes) else str(entry.dll)
        funcs = []
        for imp in entry.imports:
            if imp.name:
                funcs.append({"name": imp.name.decode("utf-8", "replace")
                              if isinstance(imp.name, bytes) else str(imp.name),
                              "ordinal": None, "hint": imp.hint})
            else:
                funcs.append({"name": None, "ordinal": imp.ordinal, "hint": None})
        imports.append({"dll": dll, "category": categorize(dll), "functions": funcs})
    rec["imports"] = imports
    rec["import_dll_count"] = len(imports)
    rec["import_thunk_count"] = sum(len(i["functions"]) for i in imports)

    delay = []
    for entry in getattr(pe, "DIRECTORY_ENTRY_DELAY_IMPORT", []) or []:
        dll = entry.dll.decode("utf-8", "replace") if isinstance(entry.dll, bytes) else str(entry.dll)
        delay.append({"dll": dll,
                      "functions": [i.name.decode("utf-8", "replace")
                                    if isinstance(i.name, bytes) else str(i.name)
                                    for i in entry.imports if i.name]})
    rec["delay_imports"] = delay

    exp = getattr(pe, "DIRECTORY_ENTRY_EXPORT", None)
    exports = []
    if exp:
        for sym in exp.symbols:
            if sym.name:
                exports.append(sym.name.decode("utf-8", "replace")
                               if isinstance(sym.name, bytes) else str(sym.name))
    rec["export_count"] = len(exports)
    rec["exports_sample"] = exports[:40]
    rec["has_exports"] = bool(exports) or (exp is not None and exp.struct.NumberOfFunctions > 0)

    ex_size = dirs.get("exception", {}).get("size", 0)
    rec["exception_rva_entries"] = ex_size // 12 if ex_size else 0  # IMAGE_RUNTIME_FUNCTION_ENTRY = 12 B
    rec["has_pdata"] = any(s["name"].lower() == ".pdata" for s in rec["sections"])

    tls = getattr(pe, "DIRECTORY_ENTRY_TLS", None)
    rec["tls_callbacks_rva"] = hex(tls.struct.AddressOfCallBacks) if tls else None

    dbg = []
    for d in getattr(pe, "DIRECTORY_ENTRY_DEBUG", []) or []:
        try:
            pdb = d.entry.PdbFileName
            if isinstance(pdb, bytes):
                pdb = pdb.rstrip(b"\x00").decode("utf-8", "replace")
            dbg.append(pdb)
        except Exception:
            pass
    rec["pdb_paths"] = dbg

    lc = getattr(pe, "DIRECTORY_ENTRY_LOAD_CONFIG", None)
    if lc:
        st = lc.struct
        rec["guard_cf_flags"] = hex(getattr(st, "GuardFlags", 0) or 0)
        rec["security_cookie_rva"] = hex(getattr(st, "SecurityCookie", 0) or 0)
    rec["has_clr"] = dirs.get("com_descriptor", {}).get("size", 0) > 0

    if deep:
        rec["deep"] = deep_stats(pe, max_text_bytes)
    pe.close()
    return rec


def build_summary(records: list[dict]) -> dict:
    by_base = {Path(r["path"]).name.lower(): r for r in records if "warnings" in r}
    internal = set(by_base.keys())
    api_counter: dict[str, set[str]] = defaultdict(set)
    dll_counter = Counter()
    signals: dict[str, list[str]] = defaultdict(list)
    edges = []
    unresolved = Counter()
    vulkan_apis = set()

    for r in records:
        if "imports" not in r:
            continue
        who = Path(r["path"]).name
        for imp in r["imports"]:
            dll = imp["dll"]
            dll_counter[dll.lower()] += 1
            cat = imp["category"]
            for f in imp["functions"]:
                if f["name"]:
                    api_counter[cat].add(f["name"])
                    if cat == "graphics-vulkan":
                        vulkan_apis.add(f["name"])
                    for group, names in BLOCKER_APIS.items():
                        if f["name"] in names:
                            signals[group].append(f"{who}: {f['name']}")
            if dll.lower().replace(".dll", "") + ".dll" in internal or dll.lower() in internal:
                edges.append((who, dll))
            elif cat not in ("win32-core", "third-party"):
                unresolved[dll.lower()] += 1

    return {
        "module_count": len(records),
        "pe32plus_amd64_count": sum(1 for r in records if r.get("is_amd64") and r.get("is_pe32plus")),
        "total_bytes": sum(r["size_bytes"] for r in records),
        "total_import_thunks": sum(r.get("import_thunk_count", 0) for r in records),
        "total_import_dlls": sum(r.get("import_dll_count", 0) for r in records),
        "unique_apis_by_category": {k: len(v) for k, v in sorted(api_counter.items())},
        "unique_api_names_by_category": {k: sorted(v) for k, v in sorted(api_counter.items())},
        "unique_imported_dlls": dict(dll_counter.most_common()),
        "total_exports": sum(r.get("export_count", 0) for r in records),
        "total_exception_entries": sum(r.get("exception_rva_entries", 0) for r in records),
        "modules_with_pdata": [Path(r["path"]).name for r in records if r.get("has_pdata")],
        "modules_with_delay_imports": [Path(r["path"]).name for r in records if r.get("delay_imports")],
        "modules_with_pdb_paths": [Path(r["path"]).name for r in records if r.get("pdb_paths")],
        "blocker_signals": {k: sorted(set(v))[:40] for k, v in signals.items()},
        "vulkan_entrypoints": sorted(vulkan_apis),
        "internal_edges": sorted(set(edges)),
        "possibly_unresolved_dlls": dict(unresolved.most_common()),
        "deep_totals": {
            "instructions": sum(r.get("deep", {}).get("instructions", 0) for r in records),
            "indirect_calls": sum(r.get("deep", {}).get("indirect_calls", 0) for r in records),
            "indirect_jumps": sum(r.get("deep", {}).get("indirect_jumps", 0) for r in records),
        },
    }


def write_markdown(records, summary, out: Path, manifest: dict) -> None:
    L = []
    L.append("# PE32+ reconnaissance report")
    L.append("")
    L.append(f"* Modules analysed: **{summary['module_count']}** "
             f"(x86-64 PE32+: {summary['pe32plus_amd64_count']}), "
             f"total **{human(summary['total_bytes'])}**.")
    L.append(f"* Import thunks: **{summary['total_import_thunks']}**, "
             f"imported DLL references: **{summary['total_import_dlls']}**, "
             f"unique exported names: **{summary['total_exports']}**.")
    L.append(f"* `.pdata` runtime-function entries (SEH/unwind records): "
             f"**{summary['total_exception_entries']}** across "
             f"{len(summary['modules_with_pdata'])} modules.")
    if summary["deep_totals"]["instructions"]:
        d = summary["deep_totals"]
        L.append(f"* Approximate `.text` linear sweep: **{d['instructions']:,} instructions**, "
                 f"{d['indirect_calls']:,} indirect calls, {d['indirect_jumps']:,} indirect jumps. "
                 f"These are *estimates* (linear sweep, may desync on data-in-code).")
    L.append("")
    L.append("## 1. Key modules")
    L.append("")
    L.append("| Module | Size | Imports (DLLs / thunks) | Exports | .pdata entries | Delay imports | PDB |")
    L.append("|---|---:|---:|---:|---:|---:|---|")
    keymap = {Path(r["path"]).name.lower(): r for r in records}
    for key in KEY_MODULES:
        r = keymap.get(key)
        if not r:
            L.append(f"| {key} | — | MISSING | — | — | — | — |")
            continue
        L.append(f"| `{Path(r['path']).name}` | {human(r['size_bytes'])} | "
                 f"{r.get('import_dll_count',0)} / {r.get('import_thunk_count',0)} | "
                 f"{r.get('export_count',0)} | {r.get('exception_rva_entries',0)} | "
                 f"{len(r.get('delay_imports',[]))} | {'yes' if r.get('pdb_paths') else 'no'} |")
    L.append("")
    L.append("## 2. Unique API surface (this is the glue/Wine workload)")
    L.append("")
    L.append("| Category | Unique imported names |")
    L.append("|---|---:|")
    for cat, n in summary["unique_apis_by_category"].items():
        L.append(f"| `{cat}` | {n} |")
    L.append("")
    if summary["vulkan_entrypoints"]:
        L.append("### Vulkan entry points actually imported")
        L.append("")
        L.append("```")
        L.append("\n".join(summary["vulkan_entrypoints"][:80]))
        L.append("```")
        L.append("")
        L.append("> If `vulkan-1.dll` is **not** in this list, `rendersystemvulkan.dll` resolves "
                 "Vulkan through `vkGetInstanceProcAddr`/loader thunks at runtime — a static "
                 "import table alone cannot prove where the calls go. See "
                 "`docs/03-PATH-B-CONTAINER.md` (WSI / thunk section).")
        L.append("")
    L.append("## 3. Blocker signals")
    L.append("")
    L.append("| Signal | Meaning | Hits (sample) |")
    L.append("|---|---|---|")
    meaning = {
        "dynamic_loading": "LoadLibrary/GetProcAddress: DLL set is decided at runtime, not in the import table",
        "seh_eh": "MSVC x64 SEH / C++ exceptions: `.pdata`/`.xdata` unwinding must be reproduced",
        "jit_wx": "VirtualAlloc/VirtualProtect: self-modifying or JIT-generated code (V8, shader cache)",
        "vulkan": "Vulkan loader / WSI entry points",
        "threading_tls": "Threads, TLS callbacks, context manipulation",
        "panel_jit": "Embedded scripting engines",
    }
    for group, label in meaning.items():
        hits = summary["blocker_signals"].get(group, [])
        L.append(f"| `{group}` | {label} | {len(hits)} — {', '.join(hits[:4]) or '—'} |")
    L.append("")
    L.append("## 4. Internal DLL dependency edges (subset)")
    L.append("")
    L.append(f"{len(summary['internal_edges'])} edges of the form `module -> imported DLL shipped "
             f"in the same archive`. Full graph: `import-graph.dot`.")
    L.append("")
    for a, b in summary["internal_edges"][:25]:
        L.append(f"* `{a}` → `{b}`")
    L.append("")
    if summary["possibly_unresolved_dlls"]:
        L.append("### DLLs referenced but not present in the archive")
        L.append("")
        for dll, n in list(summary["possibly_unresolved_dlls"].items())[:40]:
            L.append(f"* `{dll}` ({n} references)")
        L.append("")
    L.append("## 5. Warnings")
    L.append("")
    warns = [(Path(r["path"]).name, w) for r in records for w in r.get("warnings", [])]
    if not warns:
        L.append("None — every file parsed as x86-64 PE32+.")
    else:
        for name, w in warns[:60]:
            L.append(f"* `{name}`: {w}")
    L.append("")
    L.append("---")
    L.append("")
    L.append("Generated by `tools/analyze_pe.py`. Numbers describe **your** uploaded build; "
             "the checked-in `data/depot-373303-2026-11-03.tsv` is only a reference snapshot. "
             "See `docs/02-PATH-A-STATIC-RECOMPILATION.md` and `docs/03-PATH-B-CONTAINER.md`.")
    (out / "PE-REPORT.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def write_dot(records, summary, out: Path) -> None:
    lines = ["digraph dota2_win64 {", "  rankdir=LR;",
             "  node [shape=box, fontsize=9, fontname=\"monospace\"];"]
    names = {Path(r["path"]).name for r in records}
    for n in sorted(names):
        lines.append(f'  "{n}";')
    for a, b in summary["internal_edges"]:
        lines.append(f'  "{a}" -> "{b}";')
    lines.append("}")
    (out / "import-graph.dot").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, type=Path,
                    help="directory with game/bin/win64 + game/dota/bin/win64, or a .zip")
    ap.add_argument("--manifest", type=Path, default=Path("data/depot-373303-2026-11-03.tsv"))
    ap.add_argument("--out", type=Path, default=Path("report"))
    ap.add_argument("--deep", action="store_true",
                    help="capstone linear sweep of .text (slow on 100 MB client.dll)")
    ap.add_argument("--max-text-bytes", type=int, default=64 * 1024 * 1024)
    args = ap.parse_args()

    expected = parse_manifest(args.manifest)
    args.out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dota2-pe-") as tmp:
        root = extract_input(args.input, Path(tmp))
        files = sorted(p for p in root.rglob("*")
                       if p.is_file() and p.suffix.lower() in (".exe", ".dll"))
        if not files:
            print("ERROR: no .exe/.dll found in input", file=sys.stderr)
            return 2
        print(f"[analyze_pe] {len(files)} PE candidates under {root}", flush=True)
        records = []
        for p in files:
            rel = p.relative_to(root).as_posix()
            rec = analyze_file(p, rel, expected, args.deep, args.max_text_bytes)
            records.append(rec)
            print(f"  {rel}: {human(rec['size_bytes'])}, "
                  f"{rec.get('import_thunk_count',0)} imports, "
                  f"{rec.get('export_count',0)} exports", flush=True)
        summary = build_summary(records)
        payload = {"tool": "analyze_pe.py", "input": str(args.input),
                   "manifest": str(args.manifest) if expected else None,
                   "summary": summary, "modules": records}
        (args.out / "pe-analysis.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        write_markdown(records, summary, args.out, expected)
        write_dot(records, summary, args.out)
        print(f"[analyze_pe] wrote {args.out}/pe-analysis.json, PE-REPORT.md, import-graph.dot")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
