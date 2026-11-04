#!/usr/bin/env python3
"""
gen_touch_profile.py — produce the Dota 2 touch layout in two formats:

  android/app/src/main/assets/dota2/controls.icp   Winlator-compatible profile
                                                   (InputControlsView / .icp JSON)
  android/app/src/main/assets/dota2/controls.json  our own APK overlay schema

Bindings use Winlator's Binding enum names (KEY_Q, MOUSE_RIGHT_BUTTON, ...).
Element types/shapes use Winlator's ControlElement.Type / Shape enums.
Reference: brunodev85/winlator-app, com/winlator/inputcontrols/*.java

Nothing here is game code: this is an input-mapping description.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

# id, label, icp type, shape, bindings(4), x, y, scale, mouseMoveMode, our-type
C = [
    # ── Movement / camera (left half) ───────────────────────────────────────
    ("move", "MOVE / ПКМ", "BUTTON", "CIRCLE", ["MOUSE_RIGHT_BUTTON", "NONE", "NONE", "NONE"], 0.315, 0.690, 1.35, True, "button"),
    ("trackpad", "КУРСОР", "TRACKPAD", "RECT", ["MOUSE_MOVE_UP", "MOUSE_MOVE_RIGHT", "MOUSE_MOVE_DOWN", "MOUSE_MOVE_LEFT"], 0.165, 0.460, 1.00, False, "trackpad"),
    ("cam", "КАМЕРА", "D_PAD", "CIRCLE", ["KEY_UP", "KEY_RIGHT", "KEY_DOWN", "KEY_LEFT"], 0.075, 0.760, 1.00, False, "stick"),
    ("cam_grip", "ЗАХВАТ КАМЕРЫ", "BUTTON", "CIRCLE", ["MOUSE_MIDDLE_BUTTON", "NONE", "NONE", "NONE"], 0.245, 0.880, 0.70, False, "button"),
    ("zoom_in", "ZOOM +", "BUTTON", "CIRCLE", ["MOUSE_SCROLL_UP", "NONE", "NONE", "NONE"], 0.155, 0.170, 0.65, False, "button"),
    ("zoom_out", "ZOOM -", "BUTTON", "CIRCLE", ["MOUSE_SCROLL_DOWN", "NONE", "NONE", "NONE"], 0.155, 0.290, 0.65, False, "button"),
    # ── Abilities (right cluster) ──────────────────────────────────────────
    ("q", "Q", "BUTTON", "CIRCLE", ["KEY_Q", "NONE", "NONE", "NONE"], 0.700, 0.560, 0.90, False, "button"),
    ("w", "W", "BUTTON", "CIRCLE", ["KEY_W", "NONE", "NONE", "NONE"], 0.775, 0.470, 0.90, False, "button"),
    ("e", "E", "BUTTON", "CIRCLE", ["KEY_E", "NONE", "NONE", "NONE"], 0.850, 0.560, 0.90, False, "button"),
    ("d", "D", "BUTTON", "CIRCLE", ["KEY_D", "NONE", "NONE", "NONE"], 0.700, 0.680, 0.80, False, "button"),
    ("f", "F", "BUTTON", "CIRCLE", ["KEY_F", "NONE", "NONE", "NONE"], 0.775, 0.750, 0.80, False, "button"),
    ("r", "R", "BUTTON", "CIRCLE", ["KEY_R", "NONE", "NONE", "NONE"], 0.925, 0.680, 1.00, False, "button"),
    # ── Items 1..6 ─────────────────────────────────────────────────────────
    ("i1", "1", "BUTTON", "ROUND_RECT", ["KEY_1", "NONE", "NONE", "NONE"], 0.590, 0.880, 0.65, False, "button"),
    ("i2", "2", "BUTTON", "ROUND_RECT", ["KEY_2", "NONE", "NONE", "NONE"], 0.655, 0.880, 0.65, False, "button"),
    ("i3", "3", "BUTTON", "ROUND_RECT", ["KEY_3", "NONE", "NONE", "NONE"], 0.720, 0.880, 0.65, False, "button"),
    ("i4", "4", "BUTTON", "ROUND_RECT", ["KEY_4", "NONE", "NONE", "NONE"], 0.785, 0.880, 0.65, False, "button"),
    ("i5", "5", "BUTTON", "ROUND_RECT", ["KEY_5", "NONE", "NONE", "NONE"], 0.850, 0.880, 0.65, False, "button"),
    ("i6", "6", "BUTTON", "ROUND_RECT", ["KEY_6", "NONE", "NONE", "NONE"], 0.915, 0.880, 0.65, False, "button"),
    # ── Commands ───────────────────────────────────────────────────────────
    ("attack", "A / АТАКА", "BUTTON", "CIRCLE", ["KEY_A", "NONE", "NONE", "NONE"], 0.925, 0.470, 0.80, False, "button"),
    ("stop", "S / СТОП", "BUTTON", "CIRCLE", ["KEY_S", "NONE", "NONE", "NONE"], 0.925, 0.350, 0.70, False, "button"),
    ("leftclick", "ЛКМ", "BUTTON", "CIRCLE", ["MOUSE_LEFT_BUTTON", "NONE", "NONE", "NONE"], 0.850, 0.350, 0.70, False, "button"),
    ("shop", "МАГАЗИН", "BUTTON", "ROUND_RECT", ["KEY_F5", "NONE", "NONE", "NONE"], 0.590, 0.100, 0.70, False, "button"),
    ("score", "TAB", "BUTTON", "ROUND_RECT", ["KEY_TAB", "NONE", "NONE", "NONE"], 0.700, 0.100, 0.70, False, "button"),
    ("courier", "КУРЬЕР F2", "BUTTON", "ROUND_RECT", ["KEY_F2", "NONE", "NONE", "NONE"], 0.810, 0.100, 0.70, False, "button"),
    ("glyph", "ГЛИФ", "BUTTON", "ROUND_RECT", ["KEY_G", "NONE", "NONE", "NONE"], 0.920, 0.100, 0.70, False, "button"),
    ("console", "КОНСОЛЬ", "BUTTON", "ROUND_RECT", ["KEY_BACKSLASH", "NONE", "NONE", "NONE"], 0.430, 0.100, 0.70, False, "button"),
    ("pause", "ESC", "BUTTON", "ROUND_RECT", ["KEY_ESC", "NONE", "NONE", "NONE"], 0.320, 0.100, 0.70, False, "button"),
    ("alt", "ALT", "BUTTON", "ROUND_RECT", ["KEY_ALT_L", "NONE", "NONE", "NONE"], 0.210, 0.100, 0.70, True, "button"),
]


def build_icp() -> dict:
    elements = []
    for idx, (cid, label, typ, shape, binds, x, y, scale, mmm, _our) in enumerate(C):
        e = {"type": typ, "shape": shape, "bindings": binds, "scale": scale,
             "x": x, "y": y, "toggleSwitch": mmm is True and cid == "alt",
             "text": label, "iconId": 0}
        if mmm:
            e["mouseMoveMode"] = True
        elements.append(e)
    return {"id": 570, "name": "Dota 2 (Arena)", "cursorSpeed": 1.0, "elements": elements}


def build_ours() -> dict:
    controls = []
    for cid, label, typ, shape, binds, x, y, scale, mmm, our in C:
        controls.append({"id": cid, "label": label, "type": our, "shape": shape,
                         "x": x, "y": y, "scale": scale,
                         "binding": binds[0], "bindings": binds,
                         "mouseMoveMode": bool(mmm),
                         "toggle": cid == "alt"})
    return {"profile": "dota2-landscape-v1", "appId": 570,
            "description": "Right-click to move, Q/W/E/D/F/R abilities, 1-6 items, camera pad",
            "socket": "dota2-input", "controls": controls}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path,
                    default=Path("android/app/src/main/assets/dota2"))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "controls.icp").write_text(
        json.dumps(build_icp(), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (args.out / "controls.json").write_text(
        json.dumps(build_ours(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[touch] wrote controls.icp + controls.json ({len(C)} elements) -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
