#!/usr/bin/env python3
"""
fetch.py — download pinned third-party runtime components for the APK build.

Never downloads or stores Valve game files. Everything here is open source and
stays out of Git (`android/app/src/main/assets/runtime/` is gitignored).

Usage (CI):
  python runtime/fetch.py --manifest runtime/sources.json \
      --out android/app/src/main/assets/runtime
Requires for full extraction: py7zr (7z), `zstd`/`tar --zstd` (tzst), unzip via zipfile.
Missing optional tools produce warnings, not failures: the APK shell still builds.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUNDLES = ROOT / "runtime/bundles"


def download(url: str, dest: Path, expected_size: int | None) -> dict:
    if dest.exists() and expected_size and dest.stat().st_size == expected_size:
        return {"status": "cached", "bytes": dest.stat().st_size}
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Bhgjb-runtime-fetch/1.0"})
    with urllib.request.urlopen(req, timeout=300) as r, dest.open("wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    size = dest.stat().st_size
    if expected_size and size != expected_size:
        raise RuntimeError(f"size mismatch for {url}: {size} != {expected_size}")
    return {"status": "downloaded", "bytes": size}


def extract_apk(archive: Path, rules: list[dict], out: Path) -> list[str]:
    copied = []
    with zipfile.ZipFile(archive) as zf:
        names = set(zf.namelist())
        for rule in rules:
            src, dst = rule["from"], out / rule["to"]
            member = src if src in names else next(
                (n for n in names if n.endswith("/" + Path(src).name)), None)
            if not member:
                print(f"[fetch] WARN missing in APK: {src}", file=sys.stderr)
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as s, dst.open("wb") as d:
                shutil.copyfileobj(s, d, 1 << 20)
            copied.append(rule["to"])
    return copied


def extract_7z(archive: Path, wanted: list[str], outdir: Path) -> list[str]:
    """Locate files by basename, so internal layout changes do not break CI."""
    tmp = BUNDLES / "unpacked_7z"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        import py7zr  # type: ignore
        with py7zr.SevenZipFile(archive, "r") as z:
            z.extractall(tmp)
    except ImportError:
        sevenzip = shutil.which("7z") or shutil.which("7za")
        if not sevenzip:
            print("[fetch] WARN: install py7zr or p7zip to unpack Goldberg", file=sys.stderr)
            return []
        subprocess.run([sevenzip, "x", "-y", f"-o{tmp}", str(archive)],
                       check=True, stdout=subprocess.DEVNULL)
    outdir.mkdir(parents=True, exist_ok=True)
    copied = []
    for p in tmp.rglob("*"):
        if not p.is_file():
            continue
        if p.name in wanted or (p.parent.name in wanted):
            target = outdir / p.name
            if not target.exists():
                shutil.copy2(p, target)
                copied.append(p.name)
    return sorted(set(copied))


def unpack_tzst(archive: Path, outdir: Path) -> list[str]:
    tmp = BUNDLES / "unpacked_tzst"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    tar = shutil.which("tar")
    zstd = shutil.which("zstd") or shutil.which("unzstd")
    if not tar:
        print("[fetch] WARN: tar not found, keeping .tzst as-is", file=sys.stderr)
        return []
    cmd = [tar, "--zstd", "-xf", str(archive), "-C", str(tmp)] if zstd else \
          [tar, "-I", "unzstd", "-xf", str(archive), "-C", str(tmp)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"[fetch] WARN: cannot unpack {archive.name}: {r.stderr[:200]}", file=sys.stderr)
        return []
    outdir.mkdir(parents=True, exist_ok=True)
    copied = []
    for p in tmp.rglob("*"):
        if p.is_file():
            shutil.copy2(p, outdir / p.name)
            copied.append(p.name)
    return copied


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, default=ROOT / "runtime/sources.json")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "android/app/src/main/assets/runtime")
    ap.add_argument("--only", default="", help="comma-separated component ids")
    args = ap.parse_args()
    spec = json.loads(args.manifest.read_text(encoding="utf-8"))
    args.out.mkdir(parents=True, exist_ok=True)
    BUNDLES.mkdir(parents=True, exist_ok=True)
    allow = set(filter(None, args.only.split(",")))
    report = {"components": [], "warnings": []}

    for comp in spec["components"]:
        if allow and comp["id"] not in allow:
            continue
        entry = {"id": comp["id"], "license": comp["license"]}
        suffix = Path(comp["url"].split("?")[0]).suffix or ".bin"
        archive = BUNDLES / f"{comp['id']}{suffix}"
        try:
            entry.update(download(comp["url"], archive, comp.get("expected_size")))
            if comp["kind"] == "apk":
                entry["extracted"] = extract_apk(archive, comp["extract"], args.out)
            elif comp["kind"] == "7z":
                entry["extracted"] = extract_7z(
                    archive, comp["extract_by_basename"], args.out / comp.get("to", "goldberg"))
            elif comp["kind"] == "tzst":
                shutil.copy2(archive, args.out / comp["to"])
                entry["extracted"] = [comp["to"]]
                entry["unpacked"] = unpack_tzst(archive, args.out / "box64")[:20]
            else:
                report["warnings"].append(f"unknown kind {comp['kind']}")
            print(f"[fetch] {comp['id']}: {len(entry.get('extracted', []))} files")
        except Exception as exc:  # noqa: BLE001 - optional step must not break the APK build
            entry["status"] = "FAILED"
            entry["error"] = str(exc)
            report["warnings"].append(f"{comp['id']}: {exc}")
            print(f"[fetch] WARN {comp['id']}: {exc}", file=sys.stderr)
        report["components"].append(entry)

    (ROOT / "runtime/fetch-report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"[fetch] done -> {args.out}")
    return 0  # deliberately always 0: the APK shell must build even offline


if __name__ == "__main__":
    raise SystemExit(main())
