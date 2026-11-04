#!/usr/bin/env python3
"""Create a minimal runtime manifest when upstream downloads were unavailable."""
import hashlib
import json
import os
import sys
import time
from pathlib import Path

out = Path(sys.argv[1] if len(sys.argv) > 1 else "dist")
base = os.environ.get(
    "RELEASE_BASE",
    "https://github.com/ronansonir-a11y/Bhgjb/releases/download/mobile/",
)
assets = []
for aid, name in [
    ("runtime-core", "dota2-runtime-core.zip"),
    ("goldberg", "dota2-goldberg.zip"),
]:
    p = out / name
    assets.append({
        "id": aid,
        "name": name,
        "url": base + name,
        "sha256": hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else "",
        "bytes": p.stat().st_size if p.exists() else 0,
    })
manifest = {
    "schema": 1,
    "generated": int(time.time()),
    "ok": False,
    "note": "Runtime unavailable in this build; the app shows a clear error.",
    "assets": assets,
}
(out / "dota2-runtime-manifest.json").write_text(
    json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
)
print("[fallback] wrote", out / "dota2-runtime-manifest.json")
