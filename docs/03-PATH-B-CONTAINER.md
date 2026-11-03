# Путь Б: нативный контейнер `Dota2.apk` (Wine + Box64/FEX + Vulkan-танк + Goldberg)

## 0. Прямой ответ

> «Можешь ли ты собрать в моём репозитории через GitHub Actions специализированный
> `Dota2.apk` …?»

| Требование | Статус | Где |
|---|---|---|
| Иконка и название «Dota 2» | **Да, сделано** | `android/app/src/main/res/values/strings.xml`, `mipmap-anydpi-v26/ic_launcher.xml`, векторный `drawable/ic_dota2.xml` |
| Преднастроенный рантайм (Box64 + минимальный Wine PE + Vulkan wrapper) | **Частично**: CI скачивает и упаковывает **пинованные** апстрим-артефакты; «минимальный Wine» с нуля не собирается — это тысячи Win32 DLL, берётся готовый rootfs | `.github/workflows/build-apk.yml`, `runtime/sources.json` |
| Пропатченный `steam_api64.dll` (Goldberg) | **Да, как опция**: `emu-win-release-vs22.7z` → `steam_api64.dll` + `steam_interfaces.txt` + `steam_settings/`; применяется bootstrap'ом на телефоне, не в Git | `runtime/sources.json`, `android/.../assets/dota2/bootstrap.sh` |
| Vulkan wrapper | **Да, как компонент**: Vortek / FEX `libvulkan` thunk / Box64 wrapped `libvulkan`; «прямой проброс» без танка невозможен | раздел 3 |
| Тач-управление (ПКМ-движение, Q/W/E/D/F/R, предметы, камера) | **Да, сделано**: 28 элементов, два формата (наш оверлей + Winlator `.icp`) | `tools/gen_touch_profile.py`, `android/.../TouchOverlayView.java`, `assets/dota2/controls.{json,icp}` |
| Автозапуск `dota2.exe -novid -vulkan -console +dota_launch_custom_game` из `/sdcard/Dota2/` | **Да, сделано** (с необходимыми оговорками по аргументам — см. раздел 6) | `assets/dota2/launch.json`, `RuntimeBootstrap.java`, `bootstrap.sh` |
| **Гарантированно играбельный матч с ботами** | **Нет.** Это цель M5–M6 ниже; подтверждённых открытых профилей под Dota 2 нет | раздел 8 |

Иными словами: **установливаемый, правильно подписанный, автоматически стартующий APK-каркас
в CI собирается уже сейчас**; «рабочая Dota 2» требует доводки рантайма на реальном устройстве
и полного комплекта игрового контента (25–40 ГБ) на `/sdcard/Dota2/`.

---

## 1. Архитектура (реальный стек 2026)

```
┌──────────────────────────── Android APK (наш код, Java) ────────────────────────────┐
│ MainActivity · TouchOverlayView (28 элементов) · RuntimeBootstrap · LocalServerSocket │
│   assets/dota2/{launch.json, controls.json, controls.icp, bootstrap.sh}              │
│   assets/runtime/  ← rootfs.tzst, container_pattern.tzst, box64, vortek, turnip     │
└───────────────┬─────────────────────────────────────────────────────────────────────┘
                │ execve (targetSdk 28!), env: BOX64_*, WINEPREFIX, VK_ICD_FILENAMES
┌───────────────▼─────────────────────────────────────────────────────────────────────┐
│ libadrenotools: rootless загрузка Turnip ICD в ЭТО приложение (Android 9+, arm64)    │
├─────────────────────────────────────────────────────────────────────────────────────┤
│ proot / bionic-контейнер: glibc rootfs (Winlator) или bionic (Ludashi/Bionic)        │
├─────────────────────────────────────────────────────────────────────────────────────┤
│ Wine: x86_64 WOW64  |  ARM64 Wine WOW64 + FEXCore/box64ec (Arm64EC)                  │
│   wine64 / wineserver / winevulkan.dll / kernel32, ntdll, user32 (builtin)           │
├─────────────────────────────────────────────────────────────────────────────────────┤
│ CPU-транслятор: Box64 (DynaRec) или FEXCore (JIT + AOT IR cache + ThunkLibs)         │
├─────────────────────────────────────────────────────────────────────────────────────┤
│ PE-модули Valve (x86-64): dota2.exe → engine2.dll → tier0 → client.dll/server.dll    │
│                            └→ rendersystemvulkan.dll                                 │
│                            └→ Goldberg steam_api64.dll (замена)                      │
├─────────────────────────────────────────────────────────────────────────────────────┤
│ Vulkan-танк: Vortek (Vk-on-Vk) / FEX libvulkan thunk / Box64 wrapped libvulkan       │
│   vkCreateWin32SurfaceKHR → vkCreateAndroidSurfaceKHR(ANativeWindow)                 │
├─────────────────────────────────────────────────────────────────────────────────────┤
│ ARM64 libvulkan.so (Turnip / системный ICD) → GPU (Adreno/Mali/Xclipse) → Surface    │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### Варианты CPU-бэкенда (все три живы в 2026)

| Вариант | Состав | Плюс | Минус |
|---|---|---|---|
| **A. Классический Winlator** | `box64` (x86-64 Linux ELF) + **x86_64 Wine WOW64** (PE x64 грузит Wine, скомпилированный под x86-64 и исполняемый Box64) | Проверен, v11.2.0, готовые `.tzst` | Двойная трансляция: и Wine, и игра идут через DynaRec |
| **B. Bionic + FEX / Arm64EC** | Wine собран под ARM64EC, x86-64 PE исполняет **FEXCore** как WoW64-бэкенд; Box64 только для 32-бит (WowBox64) | Меньше накладных расходов, нативные Wine DLL, FEX ThunkLibs | Форки нестабильны: `FexEmu/Winlator-Bionic` и `Pipetto-crypto/winlator-bionic` сейчас отдают 404 в GitHub API; живы [StevenMXZ/Winlator-Ludashi](https://github.com/StevenMXZ/Winlator-Ludashi) (1301 ★), [Bannerlator](https://github.com/The412Banner/Bannerlator) |
| **C. Box64 `box64ec.dll`** | В дереве Box64 появился `wine/box64ec/` — реализация ARM64EC `cpu.dll` для Wine | Один проект вместо двух | `docs/WINE.md` Box64: «Arm64 Wine WOW64 … we plan to support Arm64EC in the future» — направление свежее, проверенных сборок под Dota 2 нет |

`docs/WINE.md` Box64 описывает все четыре варианта Wine (x86, x86_64, x86_64 WOW64,
Arm64 Wine WOW64) и указывает [Hangover](https://github.com/AndreRH/hangover) для ARM64.
FEX официально заявляет модульное ядро как **WoW64/ARM64EC backend в Wine**
[1](https://fex-emu.com/).

**Важно про «минимальный Wine PE»:** минимальным он быть не может. Wine — это
сотни builtin-DLL (`ntdll`, `kernel32`, `user32`, `gdi32`, `advapi32`, `ole32`,
`ws2_32`, `winmm`, …). «Минимальный» в смысле «только лоадер PE» не запустит даже
`dota2.exe`: он сразу потянет `kernel32!LoadLibraryW`, реестр, COM, `user32` для окна.
Поэтому в `runtime/sources.json` пиннутся готовые `rootfs.tzst` и
`container_pattern.tzst` из Winlator, а не самописный лоадер.

---

## 2. Что именно пиннуется в CI

`runtime/sources.json` (значения проверены 03.11.2026):

| Компонент | Источник | Размер |
|---|---|---:|
| Winlator v11.2.0 APK (источник `rootfs.tzst`, `container_pattern.tzst`, `box64-0.4.4.tzst`, `turnip-26.2.0.tzst`, `vortek-2.1.tzst`, `pulseaudio.tzst`) | [release asset](https://github.com/brunodev85/winlator/releases/download/v11.2.0/Winlator_11.2.apk) | 157 549 075 Б |
| Box64 component (альтернатива) | `https://github.com/brunodev85/winlator/raw/main/installable_components/box64/box64-0.4.5.tzst` | — |
| Goldberg `emu-win-release-vs22.7z` | [release-2026_09_27](https://github.com/Detanup01/gbe_fork/releases/download/release-2026_09_27/emu-win-release-vs22.7z) | 13 455 496 Б |
| Turnip (свежий) | `The412Banner/Banners-Turnip`, тег `v27.0.0-20261103-r3` | — |
| Box64 upstream | [v0.4.4](https://github.com/ptitSeb/box64/releases/tag/v0.4.4) | — |
| FEX upstream | [FEX-2610](https://github.com/FEX-Emu/FEX/releases/tag/FEX-2610) | — |

Лицензии: Winlator **LGPL-2.1**, Box64/FEX **MIT**, Goldberg **LGPL-3.0**,
GameNative **GPL-3.0**, libadrenotools **BSD-2-Clause**, Wine **LGPL-2.1+**.
См. [06-LEGAL-AND-RISKS](06-LEGAL-AND-RISKS.md).

---

## 3. Vulkan: от «DXVK не нужен» до работающего кадра

### Что верно в вашей посылке

`rendersystemvulkan.dll` (5.99 МиБ) действительно есть в депо 373303 от 03.11.2026,
и `-vulkan` в 2026 году всё ещё документирован как рабочий флаг
[1](https://www.pcgamingwiki.com/wiki/Dota_2), [3](https://skin.land/blog/best-dota-2-launch-options/).
Значит **DXVK/VKD3D не нужны** — мы не переводим D3D11 в Vulkan, а сразу отдаём
готовые Vulkan-вызовы. Это снимает один слой трансляции.

### Что требует доработки

1. **DLC AppID 476580.** Флаг `-vulkan` работает только при установленном «Dota 2 –
   Vulkan support» [1](https://steamdb.info/app/476580/). Его файлы должны быть
   скопированы в `/sdcard/Dota2/` вместе с основным контентом (исторически ~300–766 МБ).
2. **Танк guest→host.** Даже при Vulkan-рендерере исполняется **x86-64 код**, а ICD —
   ARM64. Реализации:
   * FEX `ThunkLibs/libvulkan`: guest packer → `OP_THUNK (0F 3F)` → host unpacker →
     `dlopen("libvulkan.so.1")`, плюс host→guest callbacks ([README](https://github.com/FEX-Emu/FEX/blob/main/ThunkLibs/README.md));
   * Box64 `src/wrapped/wrappedvulkan.c` — обёртка `libvulkan.so.1`, подменяющая
     `vkGet*ProcAddr` guest-совместимыми указателями;
   * **Vortek** — «compatibility layer on top of the Vulkan host driver» с
     эмуляцией форматов, инспекцией SPIR-V, декодированием текстур и сериализацией
     через ring buffer/socket ([repo](https://github.com/brunodev85/vortek)); в APK
     Winlator лежит `vortek-2.1.tzst` + `vortek_icd.aarch64.json`.
   * [leegao/bionic-vulkan-wrapper](https://github.com/leegao/bionic-vulkan-wrapper) —
     Mesa-форк Vk-on-Vk для Bionic/Mali/старых Adreno/Xclipse.
3. **WSI.** `vkCreateWin32SurfaceKHR(HINSTANCE, HWND)` →
   `vkCreateAndroidSurfaceKHR(ANativeWindow*)`. Нужен шим, который:
   перехватывает `vkGetInstanceProcAddr("vkCreateWin32SurfaceKHR")`, объявляет
   `VK_KHR_win32_surface` в `vkEnumerateInstanceExtensionProperties`, мапит Wine `HWND`
   на `ANativeWindow` из Android `Surface`, подменяет `VkWin32SurfaceCreateInfoKHR`
   на `VkAndroidSurfaceCreateInfoKHR`. Без этого `VkSurfaceKHR` не создать и кадр
   не отрисовать — в этом и есть главная нетривиальность «прямого проброса».
4. **Driver features.** Turnip (Mesa Freedreno) может не экспортировать расширения,
   которые ждёт Source 2 (`VK_EXT_descriptor_indexing`, timeline semaphores,
   `VK_KHR_swapchain` с нужными форматами, BCn/ASTC). `libadrenotools` позволяет грузить
   кастомный ICD без root только внутри приложения, но **не чинит** отсутствующие
   расширения.
5. **Память.** `VK_ICD_FILENAMES` / `vortek_icd.aarch64.json` должны указывать на
   распакованный ICD в приватной директории приложения; `libvulkan.so` грузится из
   rootfs контейнера — надо следить, чтобы не подменился системный загрузчик.

Практический вывод: ставьте **Vortek** как дефолт (он уже заточен под Winlator) и
держите FEX-танк как альтернативу для Arm64EC-контейнера.

---

## 4. Goldberg / оффлайн без `Steam.exe`

Цель замены — `game/bin/win64/steam_api64.dll` (309.65 КиБ в вашем депо).

Правильная процедура (по [README.release.md](https://github.com/Detanup01/gbe_fork/blob/dev/post_build/README.release.md)):

1. Достать `steam_api64.dll` из `emu-win-release-vs22.7z` (release-2026_09_27).
2. Сохранить оригинал как `steam_api64.dll.valve`.
3. Обязательно сгенерировать `steam_interfaces.txt` утилитой `generate_interfaces`
   **из оригинального DLL** (иначе Dota 2 не найдёт нужные версии интерфейсов
   `SteamClient017`, `SteamUser019`, …).
4. Создать `steam_settings/` с `configs`/`steam_appid.txt` = `570`.
5. Goldberg **не обходит DRM**; он эмулирует Steamworks API [2](https://github.com/inflation/goldberg_emulator).

### Почему одного файла, скорее всего, мало

* Dota 2 использует не только `steam_api64.dll`, но и `steamclient64.dll` /
  Game Coordinator через `steamnetworkingsockets.dll` (4.11 МиБ в депо). Главное
  меню, инвентарь, профиль и matchmaking — сетевые сервисы GC, а не локальный API.
* Исторические оффлайн-решения для Dota 2 (RevLoader) патчили **и `steamclient.dll`**,
  а боты поднимались консольными командами `map dota` + `dota_bot_populate`,
  кастомные карты — `dota_launch_custom_game <addon> <map>`
  [1](https://pinoytechsaga.blogspot.com/2017/04/play-dota-2-offline-without-steam-using-revloader.html).
* `dota2.exe` из Steam запускается с `-steam` и `+engine_experimental_drop_frame_ticks 1`
  [5](https://steamdb.info/app/570/depots/); без Steam эти параметры надо убрать/эмулировать.
* В appinfo указан **VAC** ([SteamDB](https://steamdb.info/app/570/depots/)). Оффлайн
  матч с ботами античит не должен трогать, но попытка выйти в онлайн с эмулятором —
  уже нарушение Steam ToS. Проект ограничивается оффлайном.

**План:** сначала `pe-analysis` покажет, какие именно символы импортируют `dota2.exe`,
`engine2.dll`, `client.dll`, `server.dll` из `steam_api64.dll` и есть ли статические
импорты `steamclient64.dll`. От этого зависит, хватит ли Goldberg или нужен отдельный
`steamclient`-шим. Заранее обещать «главное меню» нельзя.

---

## 5. Тач-управление под Доту

`tools/gen_touch_profile.py` генерирует **два** формата из одного описания:

* `controls.icp` — профиль Winlator (`InputControlsView`). Типы `BUTTON`, `D_PAD`,
  `TRACKPAD`, `STICK` и биндинги из enum `Binding` (`KEY_Q`, `MOUSE_RIGHT_BUTTON`, …),
  формат проверен по `input_controls/GTA 5.icp` из upstream.
* `controls.json` — схема нашего собственного оверлея в APK.

28 элементов:

| Группа | Элементы |
|---|---|
| Движение | **`MOVE / ПКМ`** — большая кнопка с `mouseMoveMode: true`: ведёте пальцем → курсор, тап → ПКМ (приказ «идти/атаковать»); `TRACKPAD` для точного наведения |
| Камера | `D_PAD` на стрелки, `ЗАХВАТ КАМЕРЫ` (средняя кнопка мыши = drag-камера), `ZOOM ±` (scroll) |
| Способности | `Q W E D F R` |
| Предметы | `1 2 3 4 5 6` |
| Команды | `A` (атака), `S` (стоп), `ЛКМ`, `МАГАЗИН F5`, `TAB`, `КУРЬЕР F2`, `ГЛИФ G`, `КОНСОЛЬ`, `ESC`, `ALT` (toggle) |

События оверлея идут в `InputBridge` (Android `LocalServerSocket` `dota2-input`,
newline-delimited JSON: `{"t":"down","binding":"KEY_Q"}` …). Контракт описан в
`android/app/src/main/java/dev/arena/dota2port/InputBridge.java`; на стороне рантайма
его должен принимать XServer/Wine `SendInput`/XTest-мост (в Winlator это
`InputControlsView` + `XServerDisplayActivity`). Мы **не** выдаём заглушку за готовый
инжектор: в `docs/05-CI-PIPELINE.md` это помечено как M4.

---

## 6. Автозапуск: точная строка и две поправки

Запрошенная строка:

```
dota2.exe -novid -vulkan -console +dota_launch_custom_game
```

Две технические поправки, иначе игра упадёт/не найдёт карту:

1. **`+dota_launch_custom_game` принимает аргументы** — `<addon_name> <map_name>`.
   Без них консольная команда ничего не запустит. Для «матча с ботами» надёжнее
   пресет `+map dota` + `dota_bot_populate` (см. исторический оффлайн-рецепт выше).
2. **`-vulkan` требует DLC 476580** и Vulkan-танка; как fallback держим
   `-dx11` (тогда понадобится DXVK, но на ARM64 это хуже).
3. `-console` в Source 2 обычно `-vconsole`/`-condebug` для лога; мы пишем оба и
   всегда сохраняем `launch.log`.

`assets/dota2/launch.json` содержит три пресета:

| Пресет | Аргументы | Назначение |
|---|---|---|
| `requested` | `-novid -vulkan -console +dota_launch_custom_game <addon> <map>` | ровно ваш запрос |
| `bots` | `-novid -vulkan -console +map dota +dota_bot_populate` | локальный матч с ботами |
| `diagnostic` | `-novid -vulkan -vconsole -condebug -windowed -w 1280 -h 720` | первый запуск/логи |

`RuntimeBootstrap.java` при старте приложения (флаг `autoLaunch: true`):

1. проверяет `/sdcard/Dota2/game/bin/win64/dota2.exe`;
2. распаковывает `assets/runtime/` и `assets/dota2/` в приватную директорию, `chmod +x`;
3. при `patchSteamApi: true` копирует Goldberg `steam_api64.dll` +
   `steam_interfaces.txt` + `steam_settings/` поверх игры (оригинал бэкапится);
4. выставляет `BOX64_DYNAREC=1`, `BOX64_DYNAREC_BIGBLOCK=1`,
   `WINEDEBUG=-all`, `VK_ICD_FILENAMES=…`, `WINEPREFIX=…`, `LD_LIBRARY_PATH=…`;
5. `ProcessBuilder`-ом запускает `bootstrap.sh` с выбранным пресетом и пишет лог.

**`targetSdk 28` — не опечатка.** На Android 10+ (API 29) приложение с более высоким
targetSdk не может исполнять ELF из writable app-data. Все рабочие форки Winlator
используют `compileSdk 34 / targetSdk 28 / minSdk 26` [3](https://github.com/The412Banner/Bannerlator).
APK — только `arm64-v8a`, sideload (не Play Store).

---

## 7. Что реально собирает GitHub Actions

| Workflow | Результат |
|---|---|
| `selftest.yml` | Прогон `tools/selftest.py` на синтетическом PE32+ на каждом push |
| `pe-analysis.yml` | `report/*` с реальными таблицами импортов/экспортов/`llvm-readobj` по вашему ZIP |
| `build-apk.yml` | **Установливаемый `Dota2.apk`** (debug-подпись, arm64-v8a) + `Dota2-runtime bundle` как отдельный артефакт |
| `path-a-probe.yml` | Эксперимент pcrecomp `disasm64` на `dota2.exe` / `engine2.dll` |

Подробности — [05-CI-PIPELINE](05-CI-PIPELINE.md).

Чего CI **не** делает и почему: сборка Wine + Box64/FEX **с нуля под bionic в Actions**
— отдельный проект (нужен AOSP-тулчейн, bionic-патчи, нестандартный `sysroot`,
часы кросс-компиляции). Поэтому рантайм пиннуется из апстрим-релизов, а не
компилируется. Это не «обман», а стандартная практика Bannerlator/GameNative:
GameNative ~554 МБ, Winlator v11.2.0 ~150 МБ [2](https://winlator.gitlab.io/).

---

## 8. Дорожная карта с измеримыми гейтами

| Milestone | Критерий «сделано» | Что проверяем |
|---|---|---|
| **M0** ✅ | Репозиторий с анализатором, валидатором, APK-каркасом, CI | `tools/selftest.py` PASS, `build-apk` зелёный |
| **M1** | Ваш ZIP загружен, получены реальные таблицы импортов 96 PE | `report/PE-REPORT.md`, `glue-inventory.md`, `import-graph.dot` |
| **M2** | APK ставится на устройство, показывает статус файлов и лог | `adb install`, скриншот экрана, `logcat` |
| **M3** | Контейнер стартует: `wine64 --version`, `box64 --version`, `vulkaninfo` через Turnip | лог `bootstrap.sh`, `VK_ICD_FILENAMES` резолвится |
| **M4** | `dota2.exe` грузит `engine2.dll`, не падает на `LoadLibrary`; тач-события доходят до Wine | `WINEDEBUG=+loaddll,+module` лог, тест `KEY_Q` в консоли |
| **M5** | Появляется Vulkan-поверхность и первое окно/меню | `vkCreateAndroidSurfaceKHR` в логе, кадр в `Surface` |
| **M6** | Главное меню + локальный матч с ботами оффлайн | скриншот, `dota_bot_populate`, 5 минут без краша |

M4–M6 — это и есть «рабочий .apk» в вашем смысле. Публично подтверждённого M6 для
Dota 2 я не нашёл: ролик «DOTA 2 on ANDROID is REAL» (декабрь 2025)
[1](https://www.youtube.com/watch?v=_0dOtZSxu-M) существует, но без логов/профилей
не является доказательством. Реалистичная оценка производительности даже при успехе —
меню/low-res, не 60 FPS: три слоя трансляции на мобильном SoC
[1](https://tech-insider.org/winlator-vs-box64-vs-wine-2026/).

---

## 9. Главные риски Пути Б (резюме)

1. **Win32-совместимость**: Source 2 тянет COM, реестр, IOCP, Qt5-плагины, `dbghelp`,
   `symsrv`, `SDL3`, libav — Wine на Android/bionic покрывает это хуже, чем на Linux/glibc.
2. **WSI Win32→Android** (раздел 3) — нет готового публичного шима под Dota 2.
3. **Steam GC**: Goldberg ≠ главное меню Dota 2 (раздел 4).
4. **Память/диск**: 25–40 ГБ контента, ~187 МиБ только client+server DLL, 8–12 ГБ ОЗУ.
5. **Vulkan-расширения Turnip** и форматы текстур.
6. **VAC / Steam ToS / DMCA** — [06-LEGAL-AND-RISKS](06-LEGAL-AND-RISKS.md).
7. **JIT V8 внутри Box64/FEX** — работает, но дорого по CPU.

→ [04-FILE-MANIFEST.md](04-FILE-MANIFEST.md): что загрузить, чтобы перейти от M0 к M1.
