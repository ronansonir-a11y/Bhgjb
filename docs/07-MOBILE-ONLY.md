# Только с телефона: установка, демо, рантайм, контент

> Обновление **4 ноября 2026**. Вы сказали, что работаете только с Android и не
> можете запустить PowerShell/собрать ZIP со Steam. Всё ниже перестроено под это:
> **никакого ПК, никакого локального ZIP, никаких Artifacts**.

## 0. Одна ссылка

**https://github.com/ronansonir-a11y/Bhgjb/releases/tag/mobile**

В Release лежат 4 файла:

| Файл | Нажать | Что делает |
|---|---|---|
| **`Dota2.apk`** | ✅ тап → «Установить» | подписанный release-ключом APK, `arm64-v8a`, `targetSdk 28` |
| `dota2-runtime-core.zip` | не нужно вручную | Wine/glibc rootfs, Box64, Turnip, Vortek, container pattern |
| `dota2-goldberg.zip` | не нужно вручную | `steam_api64.dll` Goldberg + `steam_settings/` |
| `dota2-runtime-manifest.json` | не нужно вручную | размеры и SHA-256 двух ZIP |

Приложение само скачивает три последних файла кнопкой «**Скачать рантайм**».
Разрешите «Установку из неизвестных источников» — это обычный sideload, не Play Market.

## 1. Что работает сразу после установки (демо)

При первом открытии автоматически стартует **ДЕМО-режим**
(`launch.json` → `demoOnStart: true`):

* `DemoSurfaceView` — наш собственный `SurfaceView`-рендерер на ARM64;
* те же **28 сенсорных элементов** из `controls.json` (ПКМ-движение, Q/W/E/D/F/R,
  предметы 1–6, камера, зум, магазин, глиф, TAB, ESC, ALT…);
* каждое нажатие видно на экране: счётчики по биндингам, пульсация способности,
  движение «героя» к точке заказа, панорама камеры, зум, последняя кнопка;
* события идут через `InputBridge` (abstract UNIX socket + in-process listeners) —
  тот же тракт, который в M4 должен питать Wine/XTest.

> ⚠️ **Это НЕ Source 2 и НЕ Dota 2.** Это честный self-contained тестовый режим нашего
> собственного кода: он позволяет проверить экран, тач и ARM64-сборку на телефоне
> «сразу из коробки» и показать друзьям, не имея 30 ГБ VPK. Ни одного байта Valve.

Кнопка **«Назад»** возвращает в меню.

## 2. Рантайм одной кнопкой (ProgressBar)

`RuntimeInstaller.java`:

```
assets/dota2/runtime-sources.json → dota2-runtime-manifest.json (SHA-256 + размеры)
   → HttpURLConnection (GitHub Releases, редиректы, таймауты)
   → ProgressBar: «Загрузка: dota2-runtime-core.zip · 42.1 / 157.0 МиБ · 27%»
   → SHA-256 проверка → ZipInputStream в filesDir/runtime/
   → zip-slip защита, chmod +x для box64/wine64/*.sh/*.so
   → filesDir/runtime/installed.json
```

Никакого `7z`/`zstd` на телефоне: `scripts/pack_runtime.sh` в CI заранее
переупаковывает `.tzst` и `.7z` апстримов в **обычные ZIP**. Источники пинованы в
`runtime/sources.json` (Winlator 11.2.0, Goldberg `release-2026_09_27`, Box64,
Turnip, Vortek) и все — открытые компоненты под LGPL/MIT.

### Ограничение упаковки (честно)

`zip` в CI не сохраняет симлинки, а `ZipInputStream` на телефоне не умеет их
воссоздавать. В Wine/glibc rootfs симлинки есть (`/lib64`, `/usr/lib64`, …),
поэтому распакованный рантайм **может потребовать постобработки** (создание
symlink'ов по манифесту) перед тем, как `wine64` стартует. Это часть M3/M4:
код загрузки и распаковки работает, но «полностью рабочий rootfs» не
гарантируется без проверки на устройстве. Лог `bootstrap.sh` явно покажет,
какого бинарника не хватает.

## 3. Реальный запуск контейнера

`ContainerSession.start()` → `assets/dota2/bootstrap.sh`:

1. автопоиск `box64`, `wine64`, `rootfs/`, `Xvfb`, `vortek_icd*.json` внутри
   распакованного рантайма;
2. выставление `WINEPREFIX`, `WINEARCH=win64`, `DISPLAY=:0`, `LD_LIBRARY_PATH`,
   `VK_ICD_FILENAMES`, `BOX64_DYNAREC*`;
3. `exec box64 wine64 /sdcard/Dota2/game/bin/win64/dota2.exe <пресет>`;
4. stdout/stderr **в реальном времени** стримится в экран («Лог») и `launch.log`.

`launch.json` содержит три пресета: `requested` (ровно ваша строка
`-novid -vulkan -console +dota_launch_custom_game`), `bots`
(`+map dota +dota_bot_populate`) и `diagnostic`.

**Честно о границах M3–M6.** Код запуска настоящий, но до играбельного матча
не хватает: Java-XServer из Winlator (в нашем APK его нет), Win32→Android Vulkan
WSI-шима (`vkCreateWin32SurfaceKHR` → `VK_KHR_android_surface`/`ANativeWindow`),
инжектора ввода в Wine, оффлайн-GC/steamclient-шима, полного контента и проверки
на реальном устройстве. `bootstrap.sh` пишет об этом в лог, а не делает вид, что
всё работает. Обещать «рабочий Dota 2» без девайса и 25–40 ГБ контента нельзя.

## 4. Как достать файлы игры без ПК

### ✅ Вариант A (реализован): ваша приватная ссылка

Кнопка **«Загрузить контент»** → вставьте `https://…/dota2-beta.zip` (ваша
собственная копия папки `dota 2 beta` в облаке/NAS/приватном хранилище).
`ContentInstaller.java` **потоково** распаковывает ZIP прямо в `/sdcard/Dota2/`
через `ZipInputStream` — 30 ГБ не кэшируются дважды. ProgressBar показывает
байты и число файлов. На Android 11+ кнопка «Доступ к файлам» открывает системную
настройку «Доступ ко всем файлам» (`MANAGE_EXTERNAL_STORAGE`).

Архив должен содержать пути относительно корня `dota 2 beta`:
`game/bin/win64/**`, `game/dota/bin/win64/**`, `game/dota/pak01_*.vpk`,
`game/core/**`, `game/dota/steam.inf`, `gameinfo.gi`, и контент DLC AppID 476580
для `-vulkan`.

### ⚠️ Вариант B (опциональный, не включён по умолчанию): DepotDownloader

`.github/workflows/depot-download.yml` использует
[SteamRE/DepotDownloader](https://github.com/SteamRE/DepotDownloader) с **вашим**
Steam-аккаунтом (`secrets.STEAM_USER/STEAM_PASS`) для депо 373303. Включение —
переменная `ENABLE_DEPOT=1`, репозиторий **должен быть приватным**. Результат
кладётся только в **AES-256-зашифрованный Artifact на 1 день**, никогда — в
Releases и никогда — в Git. Steam Guard часто блокирует неинтерактивный логин,
поэтому шаг `continue-on-error`.

Почему не «просто скачать депо на телефон»:

* DepotDownloader — .NET-приложение, на Android оно не запустится без Termux/proot;
* депо 373303 даёт только **625 МиБ бинарников**, а игре нужен ещё контент
  (`pak01_*.vpk`, `game/core/**`, DLC 476580) — суммарно 25–40 ГБ;
* публикация файлов Valve в публичном Release = DMCA / нарушение Steam SSA.
  Поэтому автоматическая раздача игровых бинарников в Releases **не делается**.

Именно поэтому основной путь — демо + загрузка рантайма + ваша приватная ссылка
на уже имеющуюся у вас копию.

## 5. Что изменилось в CI

| Workflow | Результат |
|---|---|
| `release.yml` | подписанный `Dota2.apk` + 2 runtime-ZIP + манифест в Release `mobile` |
| `build-apk.yml` | debug-APK (для разработки) |
| `selftest.yml` | анализатор без файлов Valve |
| `pe-analysis.yml` | **больше не блокирует вас**: без ZIP честно пропускает измерение |
| `path-a-probe.yml` | эксперимент pcrecomp, тоже опционален |
| `depot-download.yml` | opt-in, зашифрованный артефакт, без Valve-файлов в Releases |

Подпись: `keytool` создаёт keystore в CI, `actions/cache` сохраняет его между
сборками (иначе при обновлении пришлось бы удалять приложение), `apksigner verify`
проверяет подпись перед публикацией. Ключ **не** лежит в Git.

## 6. Чек-лист на телефоне

1. Открыть Release `mobile` → тап по `Dota2.apk` → Установить.
2. Открыть → сразу ДЕМО → понажимать все 28 кнопок → «Назад».
3. «Скачать рантайм» → дождаться 100% → `Рантайм: установлен`.
4. «Доступ к файлам» → включить (Android 11+).
5. «Загрузить контент» → вставить ссылку → дождаться → «Проверить».
6. «Запустить» → смотреть «Лог». Если `%DISPLAY`/WSI/GC не готовы — лог прямо
   скажет, на каком из M4–M6 мы остановились.

→ [00-EXECUTIVE-SUMMARY](00-EXECUTIVE-SUMMARY.md) ·
[03-PATH-B-CONTAINER](03-PATH-B-CONTAINER.md) ·
[05-CI-PIPELINE](05-CI-PIPELINE.md) ·
[06-LEGAL-AND-RISKS](06-LEGAL-AND-RISKS.md)
