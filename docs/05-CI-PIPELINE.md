# Пайплайн GitHub Actions: что собирается, что нет

Все воркфлоу живут на ветке `arena/52486527-bhgjb` и не требуют от раннера Windows:
`ubuntu-latest` + Python 3.11 + Android SDK/NDK. Ни один джоб не коммитит бинарники
Valve обратно в репозиторий.

| Workflow | Триггер | Вход | Артефакт | Что доказывает |
|---|---|---|---|---|
| `selftest.yml` | каждый `push`/PR | — | лог | Анализатор работает без файлов Valve |
| `pe-analysis.yml` | `workflow_dispatch` или push в `assets/incoming/**` | ZIP (URL / private release / локальный) | `dota2-pe-report` | Реальные таблицы импортов, `.pdata`, glue-инвентарь |
| `path-a-probe.yml` | `workflow_dispatch` | тот же ZIP | `path-a-probe` | Эксперимент `pcrecomp disasm64` на малых модулях |
| `build-apk.yml` | `workflow_dispatch` / изменения `android/**` | — | **`Dota2.apk`** | Установливаемый APK-каркас |

---

## 1. `selftest.yml` — зелёный на каждом push

```yaml
- uses: actions/setup-python@v5  # 3.11
- run: pip install -r tools/requirements.txt
- run: python tools/selftest.py
- run: python -m compileall -q tools runtime
```

`tools/selftest.py` синтезирует валидный PE32+ (импорты `kernel32`/`ntdll`/
`vulkan-1`/`steam_api64`, ординал, экспорт, `.pdata`, Guard CF), раскладывает его по
10 путям депо, архивирует и прогоняет всю цепочку. **Локально проверено: PASS.**

---

## 2. `pe-analysis.yml` — главный измерительный джоб

Порядок шагов:

1. **Поиск архива** (приоритеты):
   `inputs.archive_url` → локальный `assets/incoming/*.zip` → `vars.DOTA2_BINS_URL`
   → `gh release download dota2-bins -p dota2-win64-bins.zip` (для приватного репозитория
   с `GH_TOKEN`).
2. `tools/validate_archive.py --zip … --strict` → `report/MANIFEST-CHECK.md`.
   Проверяет 10 критических файлов, PE32+/AMD64-сигнатуры, zip-slip, sha256, дрейф
   размеров относительно `data/depot-373303-2026-11-03.tsv`.
3. `tools/analyze_pe.py --input … --out report --deep` → `pe-analysis.json`,
   `PE-REPORT.md`, `import-graph.dot`.
   `--deep` = линейный sweep `.text` через capstone (оценка числа инструкций,
   косвенных `call`/`jmp`); на `client.dll` 102 МиБ это минуты, джобу дан `timeout-minutes: 60`.
4. `tools/gen_glue_inventory.py` → `glue-inventory.md`, `api-surface.json`,
   `glue-stubs.h`.
5. `tools/llvm_readobj_dump.sh` → независимая сверка `llvm-readobj` по 9 ключевым
   модулям (`--coff-imports --coff-exports --sections --file-headers …`).
6. `actions/upload-artifact@v4` → `dota2-pe-report` (только текст/JSON, без PE).

Запуск:

```bash
# вариант с приватным release asset
gh variable set DOTA2_BINS_URL --body "https://github.com/…/releases/download/dota2-bins/dota2-win64-bins.zip"
gh workflow run pe-analysis.yml

# вариант с внешним signed URL
gh workflow run pe-analysis.yml -f archive_url="https://…/signed-url" -f deep=true
```

### Что именно мы узнаем из отчёта

* точное число уникальных Win32/CRT API (объём будущего HLE);
* есть ли статический импорт `vulkan-1.dll` и какие `vk*` entry points видны;
* сколько записей `.pdata` (SEH) в каждом модуле;
* кто из 94 DLL импортирует кого (граф late-bound-зависимостей);
* какие модули тянут `LoadLibrary/GetProcAddress`, `VirtualProtect`, `_CxxThrowException`;
* есть ли delay-imports, PDB-пути, CFG (`GuardFlags`), TLS-callback'ы.

Эти числа заменяют оценки в [02](02-PATH-A-STATIC-RECOMPILATION.md) и
[03](03-PATH-B-CONTAINER.md).

---

## 3. `path-a-probe.yml` — честный эксперимент Пути А

Клонирует `sp00nznet/pcrecomp` на зафиксированном коммите и запускает на **двух
самых маленьких** модулях:

```bash
python tools/pe/pe_analyze.py dota2.exe --json dota2.exe.pe.json
python tools/disasm/disasm64.py --selftest
python tools/disasm/disasm64.py dota2.exe -o dota2.exe.funcs.json --funcs-txt dota2.exe.funcs.txt
python tools/disasm/disasm64.py engine2.dll -o engine2.dll.funcs.json --funcs-txt engine2.dll.funcs.txt
python tools/lift/lift64_cpu.py dota2.exe dota2.exe.funcs.txt dota2.lift.c 0x140001000
# каждый шаг с `|| true`: ошибки и есть результат эксперимента
```

Цель — не «собрать порт», а получить измеримый ответ: сколько функций восстановилось
в настоящем Source 2 PE32+, сколько `RECOMP_TODO`, где анализатор упирается. Джоб
намеренно **не** пытается лифтить `client.dll` (102 МиБ) — это бессмысленно в 6-часовом
лимите Actions.

---

## 4. `build-apk.yml` — установливаемый APK

```yaml
- uses: actions/setup-java@v4          # Temurin 17
- uses: android-actions/setup-android@v3
- run: sdkmanager "platforms;android-34" "build-tools;34.0.0" "ndk;26.3.11579264"
- uses: gradle/actions/setup-gradle@v4  # Gradle 8.9
- run: cd android && gradle wrapper --gradle-version 8.9   # wrapper.jar НЕ коммитится
- run: python runtime/fetch.py …        # опционально, continue-on-error
- run: cd android && ./gradlew assembleDebug -PwithNdk
- run: cp android/app/build/outputs/apk/debug/app-debug.apk Dota2.apk
- uses: actions/upload-artifact@v4      # Dota2.apk
```

Ключевые решения:

| Решение | Причина |
|---|---|
| `compileSdk 34`, **`targetSdk 28`**, `minSdk 26` | targetSdk ≥ 29 запрещает `execve` ELF из writable app-data — контейнер не запустится. Так делают все рабочие форки Winlator [3](https://github.com/The412Banner/Bannerlator) |
| `abiFilters 'arm64-v8a'` | только ARM64; x86_64-код исполняет Box64/FEX, а не CPU |
| Чистый Java, без AndroidX/Kotlin | минимум зависимостей → сборка предсказуема в CI |
| `gradle wrapper` генерируется в джобе | не храним бинарный `gradle-wrapper.jar` в Git |
| `-PwithNdk` (флаг) | собирает `libdota2bridge.so` через CMake/NDK; если NDK недоступен — APK собирается без JNI-библиотеки, Java это обрабатывает |
| Debug-подпись (`apksigner` из AGP) | sideload; release-ключ в CI не храним |
| `runtime/fetch.py` — **опциональный** шаг | скачивает 157 МБ Winlator APK и 13 МБ Goldberg, распаковывает `rootfs.tzst`, `container_pattern.tzst`, `box64-*.tzst`, `turnip-*.tzst`, `vortek-*.tzst` и `steam_api64.dll` в `assets/runtime/`. Ошибка сети не роняет сборку APK |

### Границы ответственности CI

| CI делает | CI **не** делает |
|---|---|
| Компилирует Java + JNI, пакет ресурсов, иконку, подписывает APK | Не собирает Wine/Box64/FEX **с нуля под bionic** (нужен AOSP-тулчейн и часы кросс-сборки) |
| Упаковывает пинованные апстрим-артефакты | Не содержит ни одного байта Valve |
| Проверяет `selftest`, валидирует ZIP, строит отчёты | Не доказывает играбельность: M4–M6 проверяются только на устройстве |
| Готовит `launch.json` / `controls.icp` / `bootstrap.sh` | Не знает ваш SoC, версию Turnip и свободные 30 ГБ на телефоне |

---

## 5. Структура APK

```
Dota2.apk
├── AndroidManifest.xml          label "Dota 2", landscape, targetSdk 28
├── classes.dex                  MainActivity, TouchOverlayView, InputBridge,
│                                RuntimeBootstrap, LaunchConfig
├── res/                         иконка (adaptive + vector), тема, layout
├── assets/dota2/
│   ├── launch.json              3 пресета (requested / bots / diagnostic)
│   ├── controls.json            наш оверлей (28 элементов)
│   ├── controls.icp             профиль Winlator
│   ├── bootstrap.sh             проверка рантайма + запуск Wine/Box64
│   └── steam_appid.txt          570
├── assets/runtime/              (опционально) rootfs.tzst, container_pattern.tzst,
│                                box64, vortek, turnip, goldberg/*
└── lib/arm64-v8a/libdota2bridge.so  (при -PwithNdk)
```

---

## 6. Локальная проверка перед пушем

```bash
python -m venv .venv && .venv/bin/pip install -r tools/requirements.txt
.venv/bin/python tools/selftest.py
.venv/bin/python - <<'PY'
import yaml, glob, json
for f in glob.glob('.github/workflows/*.yml'):
    yaml.safe_load(open(f)); print('yaml OK', f)
for f in ['runtime/sources.json','android/app/src/main/assets/dota2/launch.json',
          'android/app/src/main/assets/dota2/controls.json']:
    json.load(open(f)); print('json OK', f)
PY
```

Если Android SDK установлен локально:

```bash
cd android && gradle wrapper --gradle-version 8.9 && ./gradlew assembleDebug -PwithNdk
```

---

## 7. Известные «недоделки» (намеренно задокументированы, а не спрятаны)

1. **Инжектор ввода.** `InputBridge` открывает `LocalServerSocket` и описывает
   протокол, но Wine/XTest-мост на стороне контейнера — задача M4. Профиль `.icp`
   уже совместим с Winlator, поэтому можно стартовать с готового Winlator-контейнера.
2. **WSI-шим `vkCreateWin32SurfaceKHR` → `vkCreateAndroidSurfaceKHR`** не реализован;
   берётся из Vortek/FEX-танка или пишется отдельно (раздел 3 документа 03).
3. **Goldberg ≠ Game Coordinator.** Генерация `steam_interfaces.txt` из оригинального
   DLL делается на устройстве (`bootstrap.sh`), а не в CI, чтобы не хранить чужие
   бинарники.
4. **Full game content** (25–40 ГБ) никогда не проходит через CI: копируется на
   `/sdcard/Dota2/` пользователем.
5. **Ни один workflow не запускает Dota 2** — для этого нужен физический ARM64-девайс.

→ [06-LEGAL-AND-RISKS](06-LEGAL-AND-RISKS.md)
