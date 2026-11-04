# Краткий ответ (техническая разведка, 3 ноября 2026)

> Контекст: репозиторий `ronansonir-a11y/Bhgjb`, ветка `arena/52486527-bhgjb`.
> Репозиторий на момент начала работ содержал только `README.md` из 8 байт — весь
> пайплайн ниже создан с нуля. Никаких файлов Valve в Git не добавлено.

> **Обновление 4 ноября 2026 (phone-only):** вы работаете только с телефона. > Проект перестроен: подписанный `Dota2.apk` и два runtime-ZIP публикуются в > [Release `mobile`](https://github.com/ronansonir-a11y/Bhgjb/releases/tag/mobile), > приложение само скачивает их с ProgressBar, сразу после установки работает ДЕМО > с 28 кнопками, а `pe-analysis` больше не ждёт локальный ZIP. > См. [07-MOBILE-ONLY](07-MOBILE-ONLY.md). Три вердикта ниже по-прежнему верны.

## Вердикт в трёх строках

| Вопрос | Ответ |
|---|---|
| **Путь А** (статическая рекомпиляция x86-64 PE → C++/LLVM IR → ARM64) | **Нет, не реализуемо для актуальной Dota 2 в 2026 году.** Инструменты существуют и активно развиваются, но для этого билда упираются в 6 непреодолимых барьеров: JIT-код V8, 94 динамически загружаемых PE-модуля, MSVC x64 SEH/C++-исключения, ~625 МиБ машинного кода, восстановление CFG без PDB и Win32/Vulkan HLE объёмом с Wine. Подробности и числа — [02-PATH-A](02-PATH-A-STATIC-RECOMPILATION.md). |
| **Путь Б** (контейнер Wine + Box64/FEX + Vulkan-танки + Goldberg) | **Технически наиболее реалистичный, но «рабочий Dota2.apk с матчем с ботами» на сегодня — исследовательский проект на месяцы, а не задача для одного CI-джоба.** Все 필요한 открытые компоненты существуют (Winlator 11.2, FEX-2610, Box64 0.4.4/0.4.5, Vortek, libadrenotools, Goldberg `release-2026_09_27`). В этом репозитории собран **реально собираемый APK-каркас** (имя/иконка, сенсорный оверлей, bootstrap, автостарт, профиль `.icp`), а также CI, который упаковывает пинованные апстрим-рантаймы. Честно перечисленные недостающие части — [03-PATH-B](03-PATH-B-CONTAINER.md) и [05-CI](05-CI-PIPELINE.md). |
| **Что загрузить прямо сейчас** | Один ZIP **только** с `game/bin/win64/**` (93 PE) и `game/dota/bin/win64/**` (3 PE) = **96 файлов / 624.73 МиБ** по манифесту депо 373303 от сегодняшнего числа, плюс 3–4 мелких текстовых файла. Точный список, скрипт-сборщик и способ передачи без нарушения Steam ToS — [04-FILE-MANIFEST](04-FILE-MANIFEST.md). |

## Что я могу и не могу сделать без вашего архива

**Не могу:** disassemble/рекомпилировать `dota2.exe`, `engine2.dll`, `client.dll` — их просто нет в репозитории. Любые числа по таблицам импортов/экспортов, `.pdata`, косвенным вызовам до загрузки архива были бы выдумкой. Поэтому первым делом написан **исполняемый пайплайн измерений**, а не отчёт «по памяти»:

```
ваш ZIP → validate_archive.py → analyze_pe.py (pefile + capstone + llvm-readobj)
        → gen_glue_inventory.py → report/*.md, *.json, import-graph.dot, glue-stubs.h
```

Он уже прогнан на синтетическом PE32+ (`tools/selftest.py`, **PASS**): 10 модулей, импорты, ординалы, экспорты, `.pdata`, сигналы `LoadLibrary/GetProcAddress/VirtualProtect/vkGetInstanceProcAddr` детектируются. Как только архив появится, отчёт даст **реальные** числа вместо оценок.

**Могу прямо сейчас:** собрать в GitHub Actions установливаемый `Dota2.apk`-каркас (иконка + имя «Dota 2» + 28 сенсорных элементов + автозапуск из `/sdcard/Dota2/`), а также CI-джоб, который скачивает и упаковывает пинованные Box64/Wine/Turnip/Goldberg-артефакты. См. `.github/workflows/build-apk.yml`.

## Ключевые факты разведки (проверяемые)

* Актуальный депо **373303 «Dota 2 Win64»** обновлён **3 ноября 2026, 20:26 UTC**, манифест `997906608877980277`: **96 файлов, 624.73 МиБ на диске, 94 DLL (618.89 МиБ) + 2 EXE (5.84 МиБ)** ([SteamDB depot 373303](https://steamdb.info/depot/373303/), [манифесты](https://steamdb.info/depot/373303/manifests/)). Снапшот с точными размерами зафиксирован в `data/depot-373303-2026-11-03.tsv`.
* `client.dll` = **102.55 МиБ**, `server.dll` = **84.11 МиБ**, `engine2.dll` = **6.10 МиБ**, `rendersystemvulkan.dll` = **5.99 МиБ**, `dota2.exe` = **964.65 КиБ**, `steam_api64.dll` = **309.65 КиБ**. В депо есть и `rendersystemdx11.dll`, и `d3dcompiler_47.dll`, и `SDL3.dll`, и `v8.dll` (48.14 МиБ) — то есть **Vulkan — не единственный и не «голый» рендерер**, а часть большого Source 2-рантайма.
* `-vulkan` в 2026 году всё ещё документирован, но **требует отдельно установленного DLC «Dota 2 – Vulkan support» (AppID 476580)** ([PCGamingWiki](https://www.pcgamingwiki.com/wiki/Dota_2), [SteamDB DLC](https://steamdb.info/app/476580/)). Без файлов этого DLC флаг не даст Vulkan-рендерер.
* Ваше предположение «DXVK не нужен» **верно**, но «вызовы Vulkan можно пробросить напрямую» — **нет**: нужен танк/обёртка. Причины: `vkCreateWin32SurfaceKHR` против `VK_KHR_android_surface` на телефоне, x86-64 указатели на функции внутри `VkInstance`/`VkDevice` (ARM64 ICD их не исполнит), `ANativeWindow` вместо `HWND`/`HINSTANCE`. Готовые реализации существуют: FEX `ThunkLibs/libvulkan`, Box64 `src/wrapped/wrappedvulkan.c`, Winlator **Vortek** ([репозиторий](https://github.com/brunodev85/vortek)), `leegao/bionic-vulkan-wrapper`.
* Официальный Winlator — **v11.2.0 от 19.08.2026**, Box64 — **v0.4.4 от 02.08.2026**, FEX — **FEX-2610 от 07.10.2026**, Goldberg `gbe_fork` — **release-2026_09_27** ([Winlator](https://github.com/brunodev85/winlator/releases/tag/v11.2.0), [Box64](https://github.com/ptitSeb/box64/releases/tag/v0.4.4), [FEX](https://github.com/FEX-Emu/FEX/releases/tag/FEX-2610), [gbe_fork](https://github.com/Detanup01/gbe_fork/releases)). Метаданные 28 репозиториев — `data/upstream-sources.json`.
* Свежая академическая оценка статических лифтеров (2026): **Mctoll, RetDec и rev.ng не прошли ни один из 23 тестов**; отдельно отмечено, что C++-исключения и виртуальные функции ломают восстановление CFG ([arXiv 2610.05999](https://arxiv.org/html/2610.05999)). Это не «я так думаю», а измерение.

## Что реально лежит в репозитории

| Путь | Назначение |
|---|---|
| `docs/01-RECON-2026.md` | Фактура, таблицы инструментов, версии, лицензии |
| `docs/02-PATH-A-STATIC-RECOMPILATION.md` | Разбор Пути А, 12 барьеров, оценка трудоёмкости |
| `docs/03-PATH-B-CONTAINER.md` | Архитектура контейнера, Vulkan/WSI, Goldberg, тач-управление, milestones |
| `docs/04-FILE-MANIFEST.md` | **Часть 3 вашего запроса**: что положить в ZIP |
| `docs/05-CI-PIPELINE.md` | Что именно собирает GitHub Actions и чего он не умеет |
| `docs/06-LEGAL-AND-RISKS.md` | DMCA / Steam ToS / VAC / лицензии апстримов |
| `data/depot-373303-2026-11-03.tsv` | 96 файлов с размерами (эталон для валидатора) |
| `data/upstream-sources.json` | Снимок GitHub API по 28 проектам |
| `tools/*.py`, `tools/collect_dota2_win64.ps1` | Сбор архива, валидация, PE-анализ, инвентарь glue, генерация тач-профиля, selftest |
| `.github/workflows/*.yml` | `selftest`, `pe-analysis`, `path-a-probe`, `build-apk` |
| `android/` | Gradle-проект APK-каркаса (Java, arm64-v8a, targetSdk 28) |
| `runtime/` | `sources.json` с пинованными URL, `fetch.py`, README (без Valve-файлов) |

## Порядок действий

1. На Windows: `powershell -ExecutionPolicy Bypass -File tools\collect_dota2_win64.ps1 -GameDir "…\dota 2 beta" -IncludeOptional`.
2. **Не делайте `git add` на ZIP в публичный репозиторий.** Залейте как приватный Release asset (`gh release create dota2-bins --private …`) и задайте переменную `DOTA2_BINS_URL`, либо положите в `assets/incoming/` (директория в `.gitignore`) и запустите воркфлоу вручную. Подробности — [04-FILE-MANIFEST](04-FILE-MANIFEST.md).
3. Запустите `pe-analysis` → получите `report/PE-REPORT.md` с реальными таблицами импортов и перечнем блокирующих API. После этого вернёмся к цифрам и уточним оба пути.
4. Параллельно `build-apk` соберёт установливаемый каркас; тестировать его можно уже без бинарников Valve (он честно покажет «game files not found»).

## Оговорка

Проект — техническое исследование совместимости, не обход DRM и не распространение игры. Все бинарники Valve остаются у вас; в Git хранятся только скрипты, метаданные и отчёты. См. [06-LEGAL-AND-RISKS](06-LEGAL-AND-RISKS.md).
