# Часть 3: что именно загрузить в репозиторий прямо сейчас

## Коротко

Соберите **один ZIP только с PE-бинарниками** из двух папок вашей установки:

```
dota2-win64-bins.zip
├── game/bin/win64/          ← 93 PE-файла (включая подпапки qt5_plugins/, subtools/)
└── game/dota/bin/win64/     ← 3 PE-файла
```

**96 файлов, 624.73 МиБ на диске, ~186 МиБ в ZIP** — это ровно депо `373303`
«Dota 2 Win64» в манифесте `997906608877980277` от **3 ноября 2026, 19:17 UTC**
([SteamDB](https://steamdb.info/depot/373303/)). Этого достаточно, чтобы я снял
таблицы импортов/экспортов, `.pdata`, delay-imports, Guard CF, посчитал уникальный
Win32/Vulkan/Steam API и запустил сборку APK.

> ⚠️ **Не кладите ZIP в публичный Git.** Это проприетарные бинарники Valve:
> лимит обычного файла в GitHub — 100 МБ, LFS упрётся в квоту, а публикация = DMCA.
> Способы передачи — раздел «Как передать» ниже.

---

## 1. Точный список (обязательный минимум)

### 1.1 Критические 10 файлов — без них пайплайн не стартует

| # | Путь в ZIP | Размер (03.11.2026) | Зачем |
|---|---|---:|---|
| 1 | `game/bin/win64/dota2.exe` | 964.65 КиБ | точка входа, импорты лаунчера |
| 2 | `game/bin/win64/engine2.dll` | 6.10 МиБ | ядро, `CreateInterface`-экспорты |
| 3 | `game/bin/win64/rendersystemvulkan.dll` | **5.99 МиБ** | Vulkan-вызовы, WSI |
| 4 | `game/bin/win64/filesystem_stdio.dll` | 2.15 МиБ | VPK/ФС |
| 5 | `game/bin/win64/tier0.dll` | 3.80 МиБ | базовый слой, кросс-модульные импорты |
| 6 | `game/bin/win64/steam_api64.dll` | **309.65 КиБ** | **оригинал!** нужен для `generate_interfaces` и для замены на Goldberg |
| 7 | `game/bin/win64/SDL3.dll` | 2.76 МиБ | окна/ввод/аудио |
| 8 | `game/dota/bin/win64/client.dll` | **102.55 МиБ** | клиентская логика |
| 9 | `game/dota/bin/win64/server.dll` | **84.11 МиБ** | серверная логика локального матча |
| 10 | `game/dota/bin/win64/host.dll` | 1.35 МиБ | хост |

`steam_api64.dll` кладите **оригинальный из Steam**, не пропатченный: генератор
`steam_interfaces.txt` из Goldberg читает именно его.

### 1.2 Все остальные файлы `game/bin/win64/` (ещё 86)

Анализатор должен видеть весь набор: он строит граф «кто импортирует кого» и
отделяет DLL, отсутствующие в архиве ( системные DLL / Wine) от внутренних Source 2.

<details>
<summary>Полный перечень (дублирует <code>data/depot-373303-2026-11-03.tsv</code>)</summary>

**Рендер / графика:** `rendersystemdx11.dll` (4.34 МиБ), `rendersystemempty.dll` (1.70 МиБ),
`materialsystem2.dll` (1.37 МиБ), `meshsystem.dll` (1.60 МиБ), `scenesystem.dll` (6.99 МиБ),
`worldrenderer.dll` (1.57 МиБ), `particles.dll` (6.00 МиБ), `animationsystem.dll` (8.87 МиБ),
`vfx_dx11.dll` (1.27 МиБ), `d3dcompiler_47.dll` (4.14 МиБ), `amd_ags_x64.dll` (177.35 КиБ),
`gfsdk_aftermath_lib.x64.dll` (5.47 МиБ), `embree3.dll` (20.98 МиБ),
`ati_compress_wrapper.dll` (736.35 КиБ), `assetpreview.dll` (46.33 МиБ),
`resourcecompiler.dll` (53.95 МиБ), `physicsbuilder.dll` (13.36 МиБ),
`toolframework2.dll` (12.75 МиБ), `visbuilder.dll` (1.77 МиБ),
`propertyeditor.dll` (1.45 МиБ), `scenefilecache.dll` (1.28 МиБ),
`helpsystem.dll` (774.15 КиБ), `imemanager.dll` (242.65 КиБ).

**Система / движок:** `resourcesystem.dll` (554.15 КиБ), `schemasystem.dll` (434.15 КиБ),
`networksystem.dll` (2.70 МиБ), `soundsystem.dll` (5.58 МиБ), `pulse_system.dll` (1.98 МиБ),
`steamaudio.dll` (3.39 МиБ), `phonon.dll` (50.85 МиБ), `phonon4.dll` (554.35 КиБ),
`steamnetworkingsockets.dll` (4.11 МиБ), `navsystem.dll` (1.26 МиБ),
`vphysics2.dll` (4.68 МиБ), `vscript.dll` (1.29 МиБ), `localize.dll` (373.15 КиБ),
`inputsystem.dll` (295.15 КиБ), `p4lib.dll` (144.15 КиБ), `dbghelp.dll` (1.49 МиБ),
`symsrv.dll` (145.77 КиБ), `bugreporter_filequeue.dll` (163.65 КиБ),
`vconcomm.dll` (253.65 КиБ), `video64.dll` (4.40 МиБ),
`valve_avi.dll` (189.65 КиБ), `valve_webm.dll` (10.86 МиБ), `valve_wmf.dll` (173.15 КиБ).

**Panorama / V8 / скрипты:** `panorama.dll` (5.82 МиБ), `panorama_text_pango.dll` (2.86 МиБ),
`v8.dll` (48.14 МиБ), `v8_icui18n.dll` (3.75 МиБ), `v8_icuuc.dll` (2.72 МиБ),
`v8_libbase.dll` (1.56 МиБ), `v8_libplatform.dll` (1.39 МиБ), `v8_zlib.dll` (824.35 КиБ),
`v8system.dll` (228.15 КиБ), `cairo.dll` (1.21 МиБ), `libfontconfig-1.dll` (481.35 КиБ),
`libfreetype-6.dll` (1.02 МиБ), `libglib-2.0-0.dll` (1.48 МиБ),
`libgmodule-2.0-0.dll` (98.35 КиБ), `libgobject-2.0-0.dll` (326.85 КиБ),
`libgthread-2.0-0.dll` (92.35 КиБ), `libpango-1.0-0.dll` (391.35 КиБ),
`libpangoft2-1.0-0.dll` (380.85 КиБ).

**Медиа/Qt/прочее:** `libavcodec-58.dll` (6.32 МиБ), `libavformat-58.dll` (1.76 МиБ),
`libavresample-4.dll` (738.85 КиБ), `libavutil-56.dll` (1.50 МиБ),
`libswscale-5.dll` (1.22 МиБ), `libmpg123-0.dll` (343.94 КиБ),
`libfbxsdk_2020_3_1.dll` (9.49 МиБ),
`Qt5Concurrent.dll` (128.35 КиБ), `Qt5Core.dll` (6.00 МиБ), `Qt5Gui.dll` (6.68 МиБ),
`Qt5Widgets.dll` (5.36 МиБ), `qtadvanceddocking-qt5.dll` (809.50 КиБ),
`qt5_plugins/imageformats/{qgif,qico,qjpeg,qtga,qtiff}.dll`,
`qt5_plugins/platforms/qwindows.dll`, `qt5_plugins/styles/qwindowsvistastyle.dll`,
`subtools/bugreporter_subtool.dll`, `subtools/netgraph_subtool.dll`,
`vconsole2.exe` (4.90 МиБ).

**`game/dota/bin/win64/`:** `client.dll`, `host.dll`, `server.dll` (см. таблицу выше).

</details>

**Важно про подпапки:** сохраняйте относительные пути `qt5_plugins/…`, `subtools/…`,
`amd_ags_x64.dll` — валидатор и PE-лоадер ориентируются на структуру депо.

### 1.3 Дополнительно (желательно, +несколько КБ/МБ)

Эти файлы **не PE**, но пригодятся для оффлайн-запуска и сверки версии:

| Путь | Назначение |
|---|---|
| `game/dota/steam.inf` | версия клиента / `ClientVersion` — привязать отчёт к конкретному билду |
| `game/dota/gameinfo.gi` | описание search paths Source 2 (откуда грузятся VPK) |
| `game/bin/win64/steam_appid.txt` | если есть; иначе создадим со значением `570` |
| `game/dota/pak01_dir.vpk` | индекс контента (небольшой) — чтобы сверить, какие VPK нужны на телефоне |

`tools/collect_dota2_win64.ps1 -IncludeOptional` добавит их автоматически. Валидатор
предупредит про `.vpk`, но анализ PE от этого не пострадает.

### 1.4 Если в вашей папке есть файлы, которых нет в манифесте

Это нормально: Valve обновляет игру почти ежедневно (последнее обновление депо —
**сегодня, 03.11.2026**). Валидатор честно напишет `size differs from the 2026-11-03
snapshot` и `N file(s) not in the reference snapshot`. Пришлите свежий список —
обновим `data/depot-*.tsv`. Ни в коем случае не вырезайте «лишние» DLL: именно они
могут оказаться новыми зависимостями.

---

## 2. Чего НЕ загружать

| ❌ | Почему |
|---|---|
| `game/bin/win32/**` | это Source 1 / 32-битные бинарники, вы прямо просили не старые билды |
| `dota_ugc/**`, Workshop Tools | гигабайты инструментов, к рантайму отношения не имеют |
| `game/dota/pak01_*.vpk` (кроме `_dir`) | 25–40 ГБ контента; для анализа импортов не нужны, в Git не лезут |
| `*.pdb`, отладочные символы | Valve их не кладёт в депо; если нашли — не публикуйте |
| `steamclient64.dll`, `steam.exe`, файлы из корня Steam | не входят в `dota 2 beta`; для оффлайна вопрос отдельный (см. [03, раздел 4](03-PATH-B-CONTAINER.md)) |
| Уже пропатченный `steam_api64.dll` | потеряем оригинал для `generate_interfaces` |
| Скриншоты, логи, личные данные | лишний риск |

---

## 3. Что понадобится **на телефоне**, но не в репозитории

Чтобы APK из Пути Б реально запустил игру, на `/sdcard/Dota2/` скопируйте **всю**
папку `dota 2 beta` (или минимум):

```
/sdcard/Dota2/game/bin/win64/**              ← те же 93 PE
/sdcard/Dota2/game/dota/bin/win64/**         ← 3 PE
/sdcard/Dota2/game/dota/pak01_*.vpk          ← весь контент
/sdcard/Dota2/game/core/**                   ← базовые ресурсы Source 2
/sdcard/Dota2/game/dota/{steam.inf,gameinfo.gi,scripts/,resource/,…}
/sdcard/Dota2/game/dota_addons/<addon>/      ← если используете +dota_launch_custom_game
/sdcard/Dota2/game/… из DLC AppID 476580    ← ОБЯЗАТЕЛЬНО для -vulkan
```

DLC «Dota 2 – Vulkan support» ([AppID 476580](https://steamdb.info/app/476580/))
должен быть установлен в Steam **до копирования**, иначе `-vulkan` не найдёт
рендер-контент ([PCGamingWiki](https://www.pcgamingwiki.com/wiki/Dota_2)).
Этот объём переносится по USB/`adb push`/карте памяти, **не через Git**.

---

## 4. Как собрать ZIP

### Вариант 1 — Windows (рекомендую)

```powershell
cd Bhgjb
powershell -ExecutionPolicy Bypass -File tools\collect_dota2_win64.ps1 `
  -GameDir "C:\Program Files (x86)\Steam\steamapps\common\dota 2 beta" `
  -OutZip dota2-win64-bins.zip -IncludeOptional -Force
```

Скрипт: проверяет 10 критических файлов, рекурсивно собирает `*.dll`/`*.exe` из двух
папок, сохраняет пути через `/`, пишет ZIP и рядом `.sha256`, печатает сводку.

### Вариант 2 — Linux/macOS/Proton

```bash
python tools/collect_dota2_win64.py \
  --game-dir "$HOME/.steam/steamapps/common/dota 2 beta" \
  --out dota2-win64-bins.zip --include-optional --force
```

### Вариант 3 — без локальной копии игры

Если Steam не установлен, точный список файлов депо можно получить утилитой
[SteamTracking/SteamFileDownloader](https://github.com/SteamTracking/SteamFileDownloader)
(команды `SteamFileDownloader ls 570 373303` и
`SteamFileDownloader get 570 373303 -- "game/bin/win64/*"`) — без суффикса манифеста
берётся последний манифест, скачиваются только совпавшие файлы, а не весь депо. Требуется ваш
Steam-аккаунт с игрой; [синтаксис target](https://github.com/SteamTracking/SteamFileDownloader).

### Проверка перед отправкой

```bash
python -m venv .venv && .venv/bin/pip install -r tools/requirements.txt
.venv/bin/python tools/validate_archive.py --zip dota2-win64-bins.zip --strict
.venv/bin/python tools/analyze_pe.py --input dota2-win64-bins.zip --out report --deep
```

---

## 5. Как передать (критично: юридически и технически)

### ✅ Рекомендуется: приватный Release asset

```bash
# репозиторий на время работ лучше сделать приватным
gh repo edit --visibility private

gh release create dota2-bins --private \
  --title "Dota 2 win64 binaries (analysis input)" \
  dota2-win64-bins.zip

# сообщить CI, откуда скачать
gh variable set DOTA2_BINS_URL --body \
  "https://github.com/ronansonir-a11y/Bhgjb/releases/download/dota2-bins/dota2-win64-bins.zip"
```

`pe-analysis.yml` скачивает его через `gh release download` с `GH_TOKEN` (для
приватного репозитория это работает). Альтернатива для публичного репозитория —
внешнее приватное хранилище с короткоживущим signed URL в **repository secret**
`DOTA2_BINS_URL`.

### ✅ Альтернатива: вообще не загружать в GitHub

Положите ZIP в `assets/incoming/` (директория уже в `.gitignore`), запустите анализ
**локально** и закоммитьте только `report/*.md` + `report/*.json`. Это самый
безопасный вариант: в Git не будет ни одного байта Valve.

### ❌ Чего не делать

```bash
git add dota2-win64-bins.zip        # >100 МБ → push отклонён; даже через LFS — DMCA
git add game/bin/win64/client.dll   # то же
```

| Ограничение | Значение |
|---|---|
| Обычный файл в Git | 100 МБ (жёстко) |
| GitHub LFS (бесплатно) | ~1 ГБ storage / 1 ГБ bandwidth в месяц |
| Release asset | до 2 ГБ на файл, но **публичный** = доступен всем |
| Actions artifact | не предназначен для проприетарных бинарников, логи/артефакты видны |
| Steam Subscriber Agreement | запрещает публикацию файлов игры |

См. [06-LEGAL-AND-RISKS](06-LEGAL-AND-RISKS.md).

---

## 6. Что произойдёт после загрузки

1. `pe-analysis.yml` → `report/MANIFEST-CHECK.md`, `PE-REPORT.md`,
   `pe-analysis.json`, `glue-inventory.md`, `api-surface.json`, `glue-stubs.h`,
   `import-graph.dot`, `llvm-readobj/*.txt`.
2. Я обновлю числа в [02](02-PATH-A-STATIC-RECOMPILATION.md) и
   [03](03-PATH-B-CONTAINER.md): вместо оценок появятся **фактические**
   количества уникальных Win32 API, записей `.pdata`, косвенных вызовов,
   `LoadLibrary/GetProcAddress`, Vulkan-entry-points и внутренних рёбер графа.
3. `path-a-probe.yml` покажет, удаётся ли `disasm64.py` восстановить каталог
   функций `dota2.exe` / `engine2.dll`.
4. `build-apk.yml` соберёт APK (уже может работать без вашего ZIP).

**Чек-лист перед отправкой:** 96 PE · все 10 критических на месте · `steam_api64.dll`
оригинальный · размеры отличаются не критично · ZIP открывается · sha256 записан ·
в Git не попал ни один `.dll`/`.exe`.
