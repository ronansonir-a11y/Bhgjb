# Путь А: статическая рекомпиляция x86-64 PE32+ → C++/LLVM IR → ARM64

## 0. Прямой ответ на вопрос

> «Сможешь ли ты (или скрипт в GitHub Actions) дизассемблировать/рекомпилировать
> `dota2.exe` и ключевые `.dll` в код под Android NDK (`arm64-v8a`), написав прослойку
> glue для Win32 API и Vulkan (`rendersystemvulkan.dll`)?»

| Операция | Ответ | Реализовано в этом репозитории |
|---|---|---|
| Дизассемблировать / снять таблицы импортов-экспортов, `.pdata`, TLS, delay-imports, Guard CF | **Да** | `tools/analyze_pe.py` (pefile + capstone) + `llvm-readobj` в `.github/workflows/pe-analysis.yml` |
| Построить каталог функций PE32+ (без IDA) | **Да, для небольших модулей** | `.github/workflows/path-a-probe.yml` запускает `pcrecomp/tools/disasm/disasm64.py` на `dota2.exe` и `engine2.dll` |
| Сгенерировать C из машинного кода | **Формально да** (`pcrecomp lift64_cpu`, Remill, rev.ng) — но **не исполнимый порт** | Пробный джоб пишет отчёт об ошибках, а не «готовый APK» |
| Слинковать это под `aarch64-linux-android` с NDK | **Нет для Dota 2** | — |
| Написать glue для **Win32 API** | **Нет**: это задача объёма Wine (`ntdll`+`kernel32`+`user32`+COM+…) | `tools/gen_glue_inventory.py` лишь **измеряет** объём и генерирует скелет таблицы импортов |
| Написать glue для **Vulkan** | **Частично**: нужен Vk-on-Vk танк + WSI-шим, а не «прямой проброс» | См. раздел 6 и [03-PATH-B](03-PATH-B-CONTAINER.md) |

**Итог:** Path A для актуальной Dota 2 (Source 2, 96 PE-модулей, 624.73 МиБ кода) —
**не инженерная задача, а исследовательская программа на годы**. Ниже — почему именно,
с привязкой к конкретным файлам вашего депо.

---

## 1. Как выглядел бы конвейер и где он ломается

```
[OK]  ZIP → validate_archive.py        → 96 PE32+/AMD64, sha256, размеры
[OK]  analyze_pe.py                    → imports/exports/.pdata/TLS/CFG/delay
[OK]  llvm-readobj --coff-imports ...  → независимая сверка
[~]   disasm64.py (pcrecomp)           → каталог функций по .pdata + Guard CF + EH
[~]   lift64_cpu.py                    → C с гостевым CPU-контекстом
[XX]  generate64.py                    → гигабайты C, кросс-компиляция clang/ARM64
[XX]  рекомпиляция 94 DLL + связывание кросс-модульных указателей
[XX]  Win32 HLE + Vulkan/WSI + JIT-host + SEH-unwinder
[XX]  APK с 25–40 ГБ контента и 8–12 ГБ ОЗУ во время работы
```

`[OK]` уже работает (см. `tools/selftest.py`). `[~]` — только на малых модулях и без
гарантии корректности. `[XX]` — непреодолимые на горизонте 2026 года барьеры.

### Что именно можно сделать в CI уже сейчас

`.github/workflows/path-a-probe.yml` (экспериментальный, запускается вручную):

1. клонирует `sp00nznet/pcrecomp` на зафиксированном коммите;
2. берёт из вашего ZIP **только** `dota2.exe` (964.65 КиБ) и `engine2.dll` (6.10 МиБ);
3. выполняет `python tools/pe/pe_analyze.py --json` и
   `python tools/disasm/disasm64.py <image> -o funcs.json --funcs-txt funcs.txt`;
4. сохраняет каталог функций и лог; запускает `generate64.py`/`lift64_cpu.py`
   **в режиме отчёта** (любая ошибка ≠ падение всего пайплайна);
5. публикует артефакт `path-a-probe/`.

Это честный эксперимент: он покажет, сколько функций вообще восстанавливается в
реальном Source 2 PE32+ и где лифтер сдаётся. Никакого «успешного порта» джоб не
заявляет.

---

## 2. Барьер №1 — объём кода (не «5 млн строк», а на порядок больше)

| Бинарник | Размер | Комментарий |
|---|---:|---|
| `client.dll` | 102.55 МиБ | игровая логика, C++ |
| `server.dll` | 84.11 МиБ | сервер (нужен даже для локального матча) |
| `resourcecompiler.dll` | 53.95 МиБ | инструменты компиляции ресурсов |
| `phonon.dll` | 50.85 МиБ | аудио/физика |
| `v8.dll` | 48.14 МиБ | **JIT-движок JavaScript** |
| `assetpreview.dll` | 46.33 МиБ | превью ассетов |
| **Весь депо** | **624.73 МиБ** | 94 DLL + 2 EXE |

Для масштаба:

* GTA IV / rexglue: **35 888 функций**, ~86 `.cpp`, **~170 МБ** сгенерированного C++,
  сборка требует ~40 ГБ диска и ручных TOML с ~795 vtable/callback-входами, 1454
  конструкторами, правками границ функций [1](https://github.com/luisxl15/GTA-IV-RECOMP-XBOX-360).
* Star Wars Battle Pods (UE3, x86-64, pcrecomp): **3.6 млн инструкций / 92 552 функции /
  0 ошибок лифтинга** — но это аркадный билд 2013 года с Win64-хостом.
* NFSU2 (x86-32, 4.8 МБ EXE): **27 742 функции → 8.9 млн строк C**
  [1](https://allnight.city/need-for-speed-underground-2-statically-recompiled-pc-pcrecomp/).

Линейная экстраполяция: ~625 МиБ PE → **десятки миллионов инструкций, сотни тысяч
функций, 1–3 ГБ сгенерированного C++**. GitHub Actions `ubuntu-latest` — 4 vCPU /
16 ГБ ОЗУ / 6 ч на джоб; один `clang++ -O2` по такому объёму с NDK упирается в память
и таймаут. И это до начала отладки.

`tools/analyze_pe.py --deep` даёт вам фактическое число инструкций по `.text`
(линейный sweep, оценка) вместо этой экстраполяции.

---

## 3. Барьер №2 — восстановление CFG без PDB

x86-64 PE32+ сам описывает свой код лучше, чем x86-32: `.pdata`, Guard CF, таблицы
`__CxxFrameHandler3/4`, DIR64-релоки. Новый `pcrecomp/tools/disasm/disasm64.py`
использует именно это и **не требует IDA**; на `ntdll` из Windows 11 24H2 он даёт
~96.5% точных концов функций. Но:

* эта точность **измерена по PDB вендора** (`pdb_ref.py`); у Dota 2 публичных PDB нет —
  в депо лежат `dbghelp.dll` и `symsrv.dll`, но это клиенты символьного сервера, а не
  сами символы. Значит, **нечем верифицировать каталог**: пропущенная функция
  всплывёт как краш «30 000 вызовов спустя»;
* Source 2 активно использует `CreateInterface`-фабрики, vtables, callback-ы,
  `std::function`, Lua/V8-обвязки — адреса функций часто встречаются только в данных;
* `client.dll` почти наверняка собран с PGO/CFG/функлетами: cold-chunk'и
  (`UNW_FLAG_CHAININFO`), out-of-line блоки после `int3`, `jmp rel32`-танки — всё это
  требует индивидуальной настройки анализатора под конкретный компилятор.

В rexglue/GTA IV это решалось **ручными конфигами** (`gta4_functions.toml`,
`gta4_ctors.toml`, `gta4_auto.toml`, `gta4_ptrs.toml`, `gta4_thunks.toml`) — для
одного XEX. Для 94 DLL Dota 2 объём ручной работы мультиплицируется.

---

## 4. Барьер №3 — C++ SEH / исключения (ваш вопрос)

MSVC x64 не использует `setjmp`-подобную модель: у каждой функции с фреймом есть
`RUNTIME_FUNCTION_ENTRY` в `.pdata` и `UNWIND_INFO` в `.xdata`; обработчики —
`__C_specific_handler` (SEH) и `__CxxFrameHandler3/4` (C++), **funclet'ы** исполняются
на гостевом стеке, `RtlVirtualUnwind` разворачивает кадры, `_CxxThrowException`
инициирует throw.

Что требуется при переносе на AArch64:

1. Гостевой unwinder, который ходит по **гостевым** `.pdata/.xdata`, а не по
   ARM64 `.eh_frame` (в pcrecomp это `recomp64_cpu/eh64.c` — правильная идея).
2. Landing pad для каждой функции с обработчиком + `longjmp` в него.
3. Перехват `_CxxThrowException` и корректная передача `EXCEPTION_RECORD`,
   `ThrowInfo`, `FuncInfo` через гостевую память.
4. Исключения, пересекающие границу «рекомпилированный код ↔ нативный Android-код»
   (например, исключение из `std::vector` в зове Wine/glue) — ARM64 unwinder их не
   поймёт.
5. `SetUnhandledExceptionFilter`, vectored handlers, APC, fibers, `RtlCaptureContext`.

XenonRecomp честно пишет: «The recompiler currently **does not support exceptions**»
[README](https://github.com/hedge-dev/XenonRecomp). В `win32hle` pcrecomp (32-битный
HLE для Linux) прямо указано «Still out of scope: guest SEH / C++ exceptions».
Академический бенчмарк 2026 отдельно называет C++-исключения причиной провала
статических лифтеров [1](https://arxiv.org/html/2610.05999),
[2](https://dl.acm.org/doi/fullHtml/10.1145/3546096.3546112).

В Dota 2 исключения не экзотика: `client.dll`/`server.dll` — тяжёлый C++ с STL,
Panorama и сетевым кодом. `tools/analyze_pe.py` помечает модули, импортирующие
`__C_specific_handler`, `_CxxThrowException`, `RtlAddFunctionTable` (сигнал `seh_eh`)
и считает записи `.pdata`.

---

## 5. Барьер №4 — динамическая подгрузка «30+ DLL» (на самом деле 94)

В вашем ZIP будет **94 DLL**. Статическая таблица импортов описывает только
`LoadLibrary`-зависимости, объявленные на этапе линковки. Source 2 дополнительно:

* грузит рендер-систему по флагу `-vulkan` / `-dx11`
  (`rendersystemvulkan.dll` ↔ `rendersystemdx11.dll`) — **выбор делается в рантайме**;
* грузит Qt5-плагины из `qt5_plugins/platforms/`, `imageformats/`, `styles/`,
  `subtools/*.dll`;
* резолвит интерфейсы через экспорты `CreateInterface` и `GetProcAddress`
  (`engine2.dll`, `tier0.dll`, `client.dll`, `server.dll`, `host.dll`);
* использует delay-imports и `LoadLibraryExW` с путями относительно `game/`.

Для AOT-порта это означает: **нужен собственный PE-лоадер на ARM64**, который
(а) мапит гостевые образы по их `ImageBase`, (б) применяет базовые релоки, (в)
строит IAT с адресами **рекомпилированных** функций (а не x86-адресов), (г)
эмулирует `HMODULE`/`GetProcAddress`, TLS-callback'ы, `DllMain`-порядок,
(д) поддерживает `LdrLoadDll` и SxS/manifest'ы. Иными словами — вы пишете Wine PE
Loader, но с гостевым ABI.

`tools/analyze_pe.py` считает `internal_edges` (кто из модулей импортирует кого из
того же архива), перечисляет DLL, которых нет в архиве, и выделяет сигналы
`LoadLibrary*`/`GetProcAddress` (`dynamic_loading`). Полный граф — `import-graph.dot`.

---

## 6. Барьер №5 — Vulkan: «прямой проброс» — это танк + WSI-шим

Ваша посылка верна в главном: **DXVK действительно не нужен**, потому что в депо есть
`rendersystemvulkan.dll` (5.99 МиБ). Но «пробросить вызовы напрямую в драйвер телефона»
не работает по четырём причинам:

1. **ABI.** `rendersystemvulkan.dll` — x86-64 PE с Microsoft x64 calling convention
   (`RCX/RDX/R8/R9`, 32 байта shadow space, `XMM0–3`). Хостовый ARM64 ICD — AAPCS64
   (`X0–X7`, `V0–V7`). Нужен переход guest→host с упаковкой аргументов.
2. **Указатели на функции.** `vkGetInstanceProcAddr` возвращает **указатель на код ICD**.
   ARM64-адрес нельзя вызвать из сгенерированного x86-64 C (и наоборот: структуры
   `VkInstance`/`VkDevice` содержат dispatch-таблицы из guest-адресов). Нужны
   trampoline'ы на каждый `vk*` entry point.
3. **WSI.** Игра вызывает `vkCreateWin32SurfaceKHR(HINSTANCE, HWND)`. Android ICD
   экспортирует `VK_KHR_android_surface` / `vkCreateAndroidSurfaceKHR(ANativeWindow*)`.
   `HWND` не существует; нужен шим, который подменяет вызов, создаёт
   `ANativeWindow` из `Surface` и возвращает корректный `VkSurfaceKHR`. Дополнительно
   `VK_KHR_win32_surface` надо объявить поддерживаемым на стороне guest.
4. **Структуры и расширения.** `VkWin32SurfaceCreateInfoKHR` ≠
   `VkAndroidSurfaceCreateInfoKHR`; `sType`/`pNext`-цепочки, `VkAllocationCallbacks`
   с guest-указателями на функции, `VkPhysicalDeviceFeatures2`, Timeline Semaphores,
   descriptor indexing, ASTC/BCn-форматы — Turnip/системный ICD может не давать
   требуемый набор.

Готовые реализации ровно этой задачи существуют:

* **FEX** `ThunkLibs/libvulkan` ([README](https://github.com/FEX-Emu/FEX/blob/main/ThunkLibs/README.md)):
  guest packer → `OP_THUNK` → host unpacker → реальный `libvulkan`, плюс обратные
  callback'ы; генератор по `libvulkan_interface.cpp`.
* **Box64** `src/wrapped/wrappedvulkan.c` + `generated/wrappedvulkan*.h`: обёртка
  `libvulkan.so.1` с подменой `vkGet*ProcAddr` на guest-совместимые указатели.
* **Winlator Vortek** ([repo](https://github.com/brunodev85/vortek)) — Vk-on-Vk слой
  поверх хостового Android-драйвера: сериализация вызовов, эмуляция форматов,
  инспекция SPIR-V, декодирование текстур; в APK Winlator лежит `vortek-2.1.tzst`.
* **leegao/bionic-vulkan-wrapper** — Mesa-форк под Bionic для Mali/старых Adreno.

Вывод: Путь А не избавляет от Vulkan-танка, а добавляет к нему необходимость
реализовать его **внутри рекомпилированного кода** вместо проверенного FEX/Box64.

---

## 7. Барьер №6 — JIT и самогенерирующийся код

`v8.dll` (48.14 МиБ) + `v8_libbase/libplatform/icui18n/icuuc/zlib` + `v8system.dll`
+ `panorama.dll` дают полноценный V8 с JIT: код создаётся в рантайме в
`VirtualAlloc`/`VirtualProtect`-памяти. Статический рекомпилятор **по определению**
не может перевести то, чего нет в файле. Дополнительно: Shader/Pipeline cache,
`resourcecompiler.dll`,Lua/`vscript.dll`, `phonon.dll`.

В pcrecomp и recomp-studio JIT объявлен non-goal; эмуляторы (Box64/FEX) решают это
естественно — транслируют freshly-written x86-64 байты по мере их появления.
`tools/analyze_pe.py` отмечает импорты `VirtualAlloc`/`VirtualProtect` сигналом
`jit_wx`.

---

## 8. Остальные барьеры (коротко)

| # | Проблема | Почему критично |
|---|---|---|
| 7 | **ABI и память** | MS x64 vs AAPCS64: shadow space, varargs, hidden `sret`, несовпадение volatile-регистров, `MXCSR`/denormals/x87, `LOCK`-атомики и **TSO vs weak memory ordering** (нужны барьеры → просадка), `CPUID`/`FS:[]`/`GS:[]` (TEB/PEB), RIP-относительная адресация |
| 8 | **Адресное пространство гостя** | Указатели в коде — 64-битные **гостевые** VA (`ImageBase 0x140000000`), а не указатели хоста. Нужна либо 1:1-резервация гигабайт под guest image (`MAP_FIXED`, конфликтует с Android ASLR/W^X), либо программная трансляция каждой загрузки/записи |
| 9 | **SIMD** | SSE2/AVX/AVX2/FMA в `client.dll`, `embree3.dll`; `SIMDe`/скаляризация даёт корректность, но не производительность; `llvm-mctoll` SIMD не поддерживает вовсе |
| 10 | **Win32/CRT glue** | Сотни уникальных API только в `kernel32/ntdll/user32/ucrtbase/msvcp140`; плюс COM, реестр, Winsock, IOCP, threadpool, IME. По сути — написать Wine заново. `tools/gen_glue_inventory.py` даёт точное число по вашему билду |
| 11 | **Инструменты** | McSema архивирован в 2022, `llvm-mctoll` — только ELF, без C++/SIMD, последний коммит 2024; RetDec в limited maintenance; rev.ng/Rellic — декомпиляторы. В 2026 бенчмарке Mctoll/RetDec/rev.ng провалили все 23 теста [1](https://arxiv.org/html/2610.05999) |
| 12 | **Лицензии/производные работы** | Сгенерированный из проприетарного PE код — производное произведение; публикация в GitHub = прямой DMCA-риск. Даже pcrecomp добавил `audit_repo.py` и `docs/PUBLISHING.md`, чтобы **не** коммитить lifted output |

---

## 9. Сравнение с «успешными» рекомпиляциями

| | GTA IV / rexglue | NFSU2 / pcrecomp | Dota 2 Win64 / 2026 |
|---|---|---|---|
| ISA | PowerPC (Xbox360) | x86-32 | **x86-64** |
| Основных образов | 1 XEX | 1 EXE | **94 DLL + 2 EXE** |
| Размер кода | ~170 МБ сгенерированного C++ | 4.8 МБ EXE → 8.9 млн строк C | **624.73 МиБ PE** |
| Исключения | не поддерживаются | x86-32 SEH, частично | **MSVC x64 SEH + C++ EH funclets** |
| JIT | нет | нет | **V8, shader cache** |
| Динамическая загрузка | минимальна | минимальна | `LoadLibrary` + `CreateInterface` + Qt-плагины |
| Графика | Xenos → D3D12/Vulkan | D3D9 | **Vulkan + DX11 + Win32 WSI** |
| Win32 | нет (Xbox kernel) | да, HLE/реальный Win32 | **полный Win32 + COM + Steam** |
| Символы | известный ABI/компилятор | IDA/Ghidra + ручные seeds | **PDB отсутствуют** |

---

## 10. Что имеет смысл делать вместо «полного Path A»

1. **Измерить, а не фантазировать.** Запустите `pe-analysis` на своём ZIP: реальные
   числа по импортам, `.pdata`, косвенным вызовам и уникальным Win32 API заменят
   все оценки в этом документе.
2. **Эксперимент на малом модуле.** `path-a-probe.yml` на `dota2.exe` (964 КиБ) —
   единственный модуль, где полный цикл `disasm64 → lift64 → clang -target aarch64`
   может завершиться в CI. Это даст честный ответ «сколько функций и где стоп».
3. **Гибрид, а не чистый AOT.** Рекомпилировать имеет смысл только маленькие
   самодостаточные компоненты, которые вы **сами пишете** (нативный `steam_api64.dll`
   -заменитель, Vulkan-танк, input-мост, загрузчик VPK). Игровой код оставить под
   Box64/FEX — то есть прийти к Пути Б, но с нативными прослойками.
4. **Не хранить lifted output в Git** (правило `audit_repo.py` из pcrecomp).

→ Переходите к [03-PATH-B-CONTAINER.md](03-PATH-B-CONTAINER.md).
