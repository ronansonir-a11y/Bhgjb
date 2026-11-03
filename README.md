# Bhgjb — Dota 2 win64 → Android ARM64: техническая разведка и пайплайн

> Исследовательский проект по переносу **актуальной Windows-версии Dota 2**
> (`game/bin/win64/dota2.exe`, `engine2.dll`, `rendersystemvulkan.dll`,
> `game/dota/bin/win64/client.dll`, `server.dll`; Source 2, x86-64 PE32+) на
> Android/`arm64-v8a`. **Не содержит файлов Valve, не обходит DRM, не аффилирован
> с Valve.** Снимок состояния: **3 ноября 2026**.

## TL;DR

| | |
|---|---|
| **Путь А** — статическая рекомпиляция PE32+ → C++/LLVM IR → ARM64 | ❌ Не реализуемо для этого билда: JIT V8, 94 динамических DLL, MSVC x64 SEH/C++ EH, ~625 МиБ кода, нет PDB, нужен HLE объёмом с Wine. Разбор: [`docs/02`](docs/02-PATH-A-STATIC-RECOMPILATION.md) |
| **Путь Б** — Wine + Box64/FEX + Vulkan-танк + Goldberg | ⚠️ Единственный реалистичный путь; в репозитории собран **установливаемый APK-каркас** и CI, но «играбельный матч с ботами» — цель M5–M6 с проверкой на устройстве. Разбор: [`docs/03`](docs/03-PATH-B-CONTAINER.md) |
| **Что загрузить** | Один ZIP: `game/bin/win64/**` (93 PE) + `game/dota/bin/win64/**` (3 PE) = 96 файлов / 624.73 МиБ. Точный список и способ передачи: [`docs/04`](docs/04-FILE-MANIFEST.md) |

**Начните здесь:** [`docs/00-EXECUTIVE-SUMMARY.md`](docs/00-EXECUTIVE-SUMMARY.md) — три прямых ответа на ваши три вопроса.

## Что уже работает (проверено в этом репозитории)

```bash
python -m venv .venv && .venv/bin/pip install -r tools/requirements.txt
.venv/bin/python tools/selftest.py      # → PASS на синтетическом PE32+
```

* `tools/analyze_pe.py` — полный PE32+ инвентарь: импорты (вкл. ординалы), экспорты,
  delay-imports, `.pdata`/SEH, TLS, Guard CF, PDB-пути, секции, граф зависимостей,
  оценка `.text` через capstone, детектор блокирующих API.
* `tools/validate_archive.py` — валидация вашего ZIP до анализа (структура, sha256,
  PE32+/AMD64, zip-slip, дрейф размеров).
* `tools/gen_glue_inventory.py` — измерение реального объёма Win32/Vulkan glue.
* `tools/gen_touch_profile.py` — 28 сенсорных элементов в форматах нашего оверлея
  и Winlator `.icp` (ПКМ-движение, Q/W/E/D/F/R, предметы 1–6, камера, магазин, глиф…).
* `tools/collect_dota2_win64.ps1` / `.py` — сборщик ZIP на вашей машине.
* `.github/workflows/` — `selftest`, `pe-analysis`, `path-a-probe`, `build-apk`.
* `android/` — Gradle-проект APK: имя/иконка «Dota 2», `targetSdk 28` (обязательно
  для `execve`), `arm64-v8a`, тач-оверлей, bootstrap с автозапуском из `/sdcard/Dota2/`.

## Быстрый старт

### 1. Соберите ZIP на машине с актуальной Dota 2

```powershell
powershell -ExecutionPolicy Bypass -File tools\collect_dota2_win64.ps1 `
  -GameDir "C:\Program Files (x86)\Steam\steamapps\common\dota 2 beta" `
  -OutZip dota2-win64-bins.zip -IncludeOptional -Force
```

### 2. НЕ коммитьте ZIP в публичный репозиторий

```bash
gh repo edit --visibility private
gh release create dota2-bins --private --title "Dota 2 win64 binaries" dota2-win64-bins.zip
gh variable set DOTA2_BINS_URL --body "https://github.com/<owner>/<repo>/releases/download/dota2-bins/dota2-win64-bins.zip"
```

Альтернатива: положите ZIP в `assets/incoming/` (в `.gitignore`) и анализируйте
локально, закоммитив только текстовые отчёты.

### 3. Запустите анализ и сборку

```bash
gh workflow run pe-analysis.yml                 # → артефакт dota2-pe-report
gh workflow run path-a-probe.yml                # эксперимент pcrecomp disasm64
gh workflow run build-apk.yml                   # → артефакт Dota2.apk
```

Локально:

```bash
.venv/bin/python tools/validate_archive.py --zip dota2-win64-bins.zip --strict
.venv/bin/python tools/analyze_pe.py --input dota2-win64-bins.zip --out report --deep
.venv/bin/python tools/gen_glue_inventory.py --analysis report/pe-analysis.json --out report
```

## Структура

```
docs/                   00 вердикт · 01 разведка · 02 Путь А · 03 Путь Б ·
                        04 что загрузить · 05 CI · 06 риски и лицензии
data/                   depot-373303-2026-11-03.tsv (96 файлов), upstream-sources.json (28 репо)
tools/                  сбор/валидация/анализ/glue/тач/selftest/llvm-readobj
runtime/                sources.json (пинованные URL), fetch.py, README
android/                Gradle-проект APK-каркаса
.github/workflows/      4 workflow
```

## Проверено в GitHub Actions (ветка `arena/52486527-bhgjb`)

| Workflow | Фактический результат |
|---|---|
| `selftest` | ✅ `success` — синтетический PE32+ пайплайн **PASS** на каждом push |
| `build-apk` | ✅ `success` — собран и подписан **`Dota2.apk`** (`arm64-v8a`, `targetSdk 28`, debug-ключ), артефакт `Dota2-apk`, 29 936 байт |
| `pe-analysis` | ✅ зарегистрирован; без вашего ZIP честно пропускает измерение и не падает |
| `path-a-probe` | ✅ зарегистрирован; без вашего ZIP пропускает эксперимент `pcrecomp` |

`runtime/fetch.py` отдельно проверен локально на синтетических APK/`7z`: извлечение
`rootfs.tzst`, `container_pattern.tzst`, `box64-*.tzst`, `vortek-*.tzst` и
`goldberg/steam_api64.dll` + `steam_settings.EXAMPLE/` работает. Реальные 157 МБ
Winlator и 13 МБ Goldberg скачиваются только при `bundle_runtime=true` в CI.

> APK **не проверен на физическом устройстве** и не содержит файлов игры: это
> установливаемый каркас/лаунчер, а не играбельный Dota 2. См. M2–M6 ниже.

## Статус milestone'ов

| M | Описание | Статус |
|---|---|---|
| M0 | Репозиторий, анализатор, APK-каркас, CI | ✅ сделано |
| M1 | Реальные таблицы импортов 96 PE | ⏳ ждёт вашего ZIP |
| M2 | APK на устройстве, статус файлов, лог | ⏳ |
| M3 | Контейнер: Wine/Box64/Turnip/Vulkan ICD | ⏳ |
| M4 | `dota2.exe` грузит DLL, тач доходит до Wine | ⏳ |
| M5 | Vulkan-поверхность и первое меню | ⏳ |
| M6 | Главное меню + локальный матч с ботами оффлайн | ⏳ исследовательская цель |

## Ссылки на ключевые апстримы

[Winlator](https://github.com/brunodev85/winlator) ·
[Vortek](https://github.com/brunodev85/vortek) ·
[Box64](https://github.com/ptitSeb/box64) ·
[FEX-Emu](https://github.com/FEX-Emu/FEX) ·
[Goldberg gbe_fork](https://github.com/Detanup01/gbe_fork) ·
[libadrenotools](https://github.com/bylaws/libadrenotools) ·
[pcrecomp](https://github.com/sp00nznet/pcrecomp) ·
[XenonRecomp](https://github.com/hedge-dev/XenonRecomp) ·
[rev.ng](https://github.com/revng/revng) ·
[GameNative](https://github.com/utkarshdalal/GameNative)

Полный снимок с датами/звёздами/лицензиями: [`data/upstream-sources.json`](data/upstream-sources.json).

## Лицензия

Наш код — MIT ([`LICENSE`](LICENSE)). Сторонние компоненты остаются под своими
лицензиями и **не включены** в репозиторий. Читайте
[`docs/06-LEGAL-AND-RISKS.md`](docs/06-LEGAL-AND-RISKS.md) перед любым распространением.
