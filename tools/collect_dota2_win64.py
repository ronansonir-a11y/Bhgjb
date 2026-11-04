#!/usr/bin/env python3
"""Cross-platform twin of collect_dota2_win64.ps1 (e.g. a Proton/Steam-Linux install).

Usage:
  python tools/collect_dota2_win64.py --game-dir "/.../steamapps/common/dota 2 beta" \
      --out dota2-win64-bins.zip [--include-optional]
"""
from __future__ import annotations

import argparse
import hashlib
import zipfile
from pathlib import Path

BIN_DIRS = ("game/bin/win64", "game/dota/bin/win64")
CRITICAL = (
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
)
OPTIONAL = (
    "game/dota/steam.inf", "game/dota/gameinfo.gi",
    "game/bin/win64/steam_appid.txt", "game/dota/pak01_dir.vpk",
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-dir", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=Path("dota2-win64-bins.zip"))
    ap.add_argument("--include-optional", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    root = args.game_dir.resolve()
    if not root.is_dir():
        raise SystemExit(f"not a directory: {root}")
    missing = [p for p in CRITICAL if not (root / p).is_file()]
    if missing:
        raise SystemExit("missing critical files:\n  " + "\n  ".join(missing))
    files = []
    for d in BIN_DIRS:
        files += [p for p in (root / d).rglob("*")
                  if p.is_file() and p.suffix.lower() in (".dll", ".exe")]
    if args.include_optional:
        files += [root / p for p in OPTIONAL if (root / p).is_file()]
    files = sorted(set(files))
    if args.out.exists() and not args.force:
        raise SystemExit(f"output exists: {args.out} (use --force)")
    total = sum(p.stat().st_size for p in files)
    print(f"[collect] {len(files)} files, {total/1048576:.1f} MiB "
          f"(reference depot 373303 @ 2026-11-03 = 624.73 MiB / 96 PE files)")
    with zipfile.ZipFile(args.out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for p in files:
            zf.write(p, p.relative_to(root).as_posix())
    digest = hashlib.sha256(args.out.read_bytes()).hexdigest()
    Path(str(args.out) + ".sha256").write_text(
        f"{digest}  {args.out.name}\n", encoding="ascii")
    print(f"[collect] {args.out} sha256={digest}")
    print("[collect] WARNING: Valve proprietary binaries — private release asset or local use only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
