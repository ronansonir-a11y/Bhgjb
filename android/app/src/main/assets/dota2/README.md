# assets/dota2 — конфигурация, без файлов Valve

| Файл | Назначение |
|---|---|
| `launch.json` | пресеты запуска, `demoOnStart: true`, env |
| `controls.json` / `controls.icp` | 28 сенсорных элементов (генерируются) |
| `runtime-sources.json` | **URL двух ZIP-рантаймов в GitHub Releases** для встроенного загрузчика |
| `bootstrap.sh` | автопоиск Box64/Wine/rootfs и `exec` контейнера |
| `steam_appid.txt` | `570` |

`RuntimeInstaller.java` скачивает ZIP'ы с ProgressBar, проверяет SHA-256 из
`dota2-runtime-manifest.json` и распаковывает в `filesDir/runtime/`.
`DemoSurfaceView.java` работает сразу после установки без сети и без VPK.
