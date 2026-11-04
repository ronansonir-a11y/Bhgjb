# runtime/ — пинованные сторонние компоненты

Здесь **нет кода Valve**. `sources.json` описывает открытые апстримы; в CI
`scripts/pack_runtime.sh` переупаковывает их в **два обычных ZIP**, которые
установленное приложение скачивает само, с ProgressBar, без ПК и без ADB.

| Файл в Releases `mobile` | Что внутри | Лицензия |
|---|---|---|
| `dota2-runtime-core.zip` | `rootfs/` (Wine+glibc), `box64-*`, `turnip-*`, `vortek-*`, `container_pattern/`, `LICENSES.txt` | LGPL-2.1 / MIT |
| `dota2-goldberg.zip` | `steam_api64.dll` (Goldberg), `steam_settings/`, `LICENSES.txt` | LGPL-3.0 |
| `dota2-runtime-manifest.json` | размеры + SHA-256 обоих ZIP | — |

Источники (пинованы в `sources.json`):
[Winlator v11.2.0](https://github.com/brunodev85/winlator/releases/tag/v11.2.0)
· [Goldberg gbe_fork](https://github.com/Detanup01/gbe_fork/releases)
· [Box64](https://github.com/ptitSeb/box64) · [FEX](https://github.com/FEX-Emu/FEX).

### Путь на телефоне

```
Dota2.apk → «Скачать рантайм» → HttpURLConnection + ProgressBar
          → SHA-256 сверка → ZipInputStream → filesDir/runtime/
          → «Запустить» → bootstrap.sh ищет box64/wine64/rootfs → exec
```

`fetch.py` остаётся для локальной/CI-отладки; приложение его не использует.
Ни один ZIP не содержит `.dll`/`.exe`/VPK игры. См.
[docs/07-MOBILE-ONLY.md](../docs/07-MOBILE-ONLY.md) и
[docs/06-LEGAL-AND-RISKS.md](../docs/06-LEGAL-AND-RISKS.md).
