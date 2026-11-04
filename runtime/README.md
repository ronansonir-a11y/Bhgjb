# runtime/ — пинованные сторонние компоненты

Здесь **нет кода Valve и нет бинарников**. Это только манифест с URL и скрипт,
который во время сборки APK скачивает открытые компоненты:

| id | Что | Лицензия | Откуда |
|---|---|---|---|
| `winlator-apk` | `rootfs.tzst` (glibc/Wine), `container_pattern.tzst` (Wine prefix), `box64-0.4.4.tzst`, `turnip-26.2.0.tzst`, `vortek-2.1.tzst`, `pulseaudio.tzst` | LGPL-2.1 | [Winlator v11.2.0 release](https://github.com/brunodev85/winlator/releases/tag/v11.2.0) |
| `goldberg` | `steam_api64.dll`, `generate_interfaces.exe`, `steam_settings.EXAMPLE` | LGPL-3.0 | [gbe_fork release-2026_09_27](https://github.com/Detanup01/gbe_fork/releases) |
| `box64-component` | альтернативный `box64-0.4.5.tzst` | MIT | [Winlator installable_components](https://github.com/brunodev85/winlator/tree/main/installable_components/box64) |

```bash
python -m pip install py7zr
python runtime/fetch.py --out android/app/src/main/assets/runtime
```

В `build-apk.yml` этот шаг вызывается только при `bundle_runtime=true` и помечен
`continue-on-error`: даже без сети APK-каркас собирается. Результат кладётся в
`android/app/src/main/assets/runtime/` (в `.gitignore`), а скачанные архивы — в
`runtime/bundles/` (тоже в `.gitignore`).

## Что НЕ делает fetch.py

* не скачивает `.dll`/`.exe`/VPK игры;
* не собирает Wine/Box64/FEX из исходников под bionic (это отдельный проект);
* не распаковывает `rootfs.tzst` в работающий контейнер — это задача M3 и
  делается на устройстве; `bootstrap.sh` честно сообщает, чего не хватает;
* не генерирует `steam_interfaces.txt`: это делается из **оригинального**
  `steam_api64.dll` утилитой `generate_interfaces` на вашей машине/устройстве.

См. [docs/03-PATH-B-CONTAINER.md](../docs/03-PATH-B-CONTAINER.md) и
[docs/06-LEGAL-AND-RISKS.md](../docs/06-LEGAL-AND-RISKS.md).
