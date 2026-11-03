#!/usr/bin/env python3
"""
validate_archive.py — gate #0 of the CI pipeline.

Checks a user-supplied ZIP before any analysis or APK build:
  * exact path layout (game/bin/win64/**, game/dota/bin/win64/**);
  * presence of the critical PE modules;
  * PE32+ / AMD64 signatures, no ARM/PE32/ELF/Mach-O contamination;
  * sha256 of every file, size drift vs. the SteamDB reference snapshot;
  * zip-slip, absolute paths, non-game payloads (VPK, PDB, EXE installers).

It also prints the legal warning: Valve binaries must not be committed to a
public repository (see docs/06-LEGAL-AND-RISKS.md).

Usage:
  python tools/validate_archive.py --zip assets/incoming/dota2-win64-bins.zip \
      --manifest data/depot-373303-2026-11-03.tsv --out report [--strict]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import zipfile
from pathlib import Path

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
ALLOWED_PREFIXES = ("game/bin/win64/", "game/dota/bin/win64/")
ALLOWED_SUFFIXES = (".dll", ".exe", ".txt", ".inf", ".gi", ".json")
FORBIDDEN_SUFFIXES = (".vpk", ".pdb", ".zip", ".7z", ".msi", ".cab", ".tar", ".gz")


def parse_manifest(path: Path):
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        p = line.split("\t")
        if len(p) >= 4:
            out[p[0].strip()] = int(p[3])
    return out


def pe_identity(blob: bytes) -> dict:
    info = {"mz": blob[:2] == b"MZ", "pe32plus": False, "amd64": False,
            "magic": None, "machine": None, "is_dll": None}
    if len(blob) < 0x100 or blob[:2] != b"MZ":
        return info
    try:
        e_lfanew = struct.unpack_from("<I", blob, 0x3C)[0]
        if blob[e_lfanew:e_lfanew + 4] != b"PE\0\0":
            return info
        machine = struct.unpack_from("<H", blob, e_lfanew + 4)[0]
        opt_size = struct.unpack_from("<H", blob, e_lfanew + 20)[0]
        opt = e_lfanew + 24
        magic = struct.unpack_from("<H", blob, opt)[0]
        chars = struct.unpack_from("<H", blob, e_lfanew + 22)[0]
        info.update({"machine": hex(machine), "magic": hex(magic),
                     "pe32plus": magic == 0x20B, "amd64": machine == 0x8664,
                     "is_dll": bool(chars & 0x2000), "opt_size": opt_size})
    except Exception as exc:  # noqa: BLE001
        info["error"] = str(exc)
    return info


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zip", required=True, type=Path)
    ap.add_argument("--manifest", type=Path, default=Path("data/depot-373303-2026-11-03.tsv"))
    ap.add_argument("--out", type=Path, default=Path("report"))
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 if any critical file is missing or non-PE32+/AMD64")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    expected = parse_manifest(args.manifest) if args.manifest.exists() else {}

    found, errors, warnings = {}, [], []
    if not args.zip.exists():
        sys.exit(f"archive not found: {args.zip}")
    with zipfile.ZipFile(args.zip) as zf:
        for info in zf.infolist():
            raw = info.filename.replace("\\", "/")
            if info.is_dir():
                continue
            if raw.startswith("/") or ".." in raw.split("/"):
                errors.append(f"unsafe path in archive: {raw}")
                continue
            name = raw.lstrip("./")
            if name.lower().endswith(FORBIDDEN_SUFFIXES):
                warnings.append(f"non-binary payload in archive (not needed for PE analysis): {name}")
                continue
            if not name.lower().endswith(ALLOWED_SUFFIXES):
                warnings.append(f"unexpected file type: {name}")
                continue
            if not name.startswith(ALLOWED_PREFIXES):
                warnings.append(f"outside the two win64 folders (ignored): {name}")
                continue
            blob = zf.read(info)
            item = {"path": name, "size": len(blob),
                    "sha256": hashlib.sha256(blob).hexdigest()}
            if name.lower().endswith((".dll", ".exe")):
                item.update(pe_identity(blob))
                if not item["pe32plus"] or not item["amd64"]:
                    errors.append(f"{name}: NOT x86-64 PE32+ (machine={item['machine']}, magic={item['magic']})")
            if name in expected and expected[name] != len(blob):
                item["size_expected_snapshot"] = expected[name]
                warnings.append(
                    f"{name}: size {len(blob)} != reference {expected[name]} — "
                    "Valve has updated the build; refresh data/depot-*.tsv")
            found[name] = item

    missing = [p for p in CRITICAL if p not in found]
    extra = sorted(set(found) - set(expected)) if expected else []
    for p in missing:
        errors.append(f"missing critical file: {p}")
    if extra:
        warnings.append(f"{len(extra)} file(s) not in the reference snapshot (harmless, "
                        f"usually a newer patch): {', '.join(extra[:8])}")

    result = {"archive": str(args.zip), "manifest": str(args.manifest),
              "files": found, "file_count": len(found),
              "total_uncompressed_bytes": sum(f["size"] for f in found.values()),
              "missing_critical": missing, "errors": errors, "warnings": warnings,
              "critical_pe_checks": {
                  p: {"sha256": found[p]["sha256"], "machine": found[p].get("machine"),
                      "magic": found[p].get("magic")}
                  for p in CRITICAL if p in found}}
    (args.out / "manifest-check.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    md = ["# Archive validation", "",
          f"* Archive: `{args.zip}`",
          f"* PE files: **{len(found)}**, uncompressed **{result['total_uncompressed_bytes']/1048576:.1f} MiB**",
          f"* Missing critical files: **{len(missing)}**",
          f"* Errors: **{len(errors)}**, warnings: **{len(warnings)}**", "",
          "## Critical modules (sha256)", "",
          "| Path | Size | sha256 |", "|---|---:|---|"]
    for p in CRITICAL:
        f = found.get(p)
        if f:
            md.append(f"| `{p}` | {f['size']} | `{f['sha256']}` |")
        else:
            md.append(f"| `{p}` | — | **MISSING** |")
    md += ["", "## Errors", ""]
    md += [f"* {e}" for e in errors] or ["* none"]
    md += ["", "## Warnings", ""]
    md += [f"* {w}" for w in warnings[:60]] or ["* none"]
    md += ["", "---", "",
           "**Legal:** these are Valve's proprietary binaries. Do not commit the ZIP to a "
           "public repository; use a private GitHub Release asset or a CI secret. "
           "See `docs/04-FILE-MANIFEST.md` and `docs/06-LEGAL-AND-RISKS.md`."]
    (args.out / "MANIFEST-CHECK.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"[validate] {len(found)} PE files, {len(missing)} missing, "
          f"{len(errors)} errors, {len(warnings)} warnings")
    for e in errors[:20]:
        print("  ERROR:", e, file=sys.stderr)
    return 1 if args.strict and (errors or missing) else 0


if __name__ == "__main__":
    raise SystemExit(main())
