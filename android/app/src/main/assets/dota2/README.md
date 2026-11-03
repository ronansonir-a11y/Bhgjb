# assets/dota2

These are **configuration files only** — no Valve binaries.

| File | Purpose |
|---|---|
| `launch.json` | three launch presets (`requested`, `bots`, `diagnostic`), env vars, autoLaunch |
| `controls.json` | touch overlay schema for `TouchOverlayView.java` (generated) |
| `controls.icp` | the same layout in Winlator `.icp` format (generated) |
| `bootstrap.sh` | preflight + `box64 wine64 dota2.exe $DOTA_ARGS` |
| `steam_appid.txt` | `570`, for Goldberg `steam_settings/` |

Regenerate the layouts after editing `tools/gen_touch_profile.py`:

```bash
python tools/gen_touch_profile.py --out android/app/src/main/assets/dota2
```

The `runtime/` asset directory (sibling of this one) is created by
`runtime/fetch.py` in CI and contains only third-party open-source components
under their own licences. It is gitignored.
