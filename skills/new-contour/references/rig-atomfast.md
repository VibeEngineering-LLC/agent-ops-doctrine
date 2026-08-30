# Rig pack: AtomFast dosimeter + Android phone + adb

Доменный пакет для исполнительного контура «AtomFast-tester», поднимаемого скиллом
`new-contour`. Описывает железо/софт, карту обратимости adb-команд, BLE-поверхность
дозиметра, первый рабочий сценарий и анти-паттерны, специфичные для этого стенда.

## 1. Overview

Стенд: PC под управлением Claude Code, к нему USB-шнуром привязан Android-телефон,
к телефону по Bluetooth Low Energy подключён персональный дозиметр AtomFast.
Дозиметр обменивается данными только с приложением AtomFast на телефоне; PC к
дозиметру напрямую не ходит, только через `adb` → телефон → BLE → дозиметр.

Контур-tester выполняет на этом стенде проверочные задачи: ставит test-APK, гоняет
приложение AtomFast, снимает показания и при наличии — спектры, собирает логи,
наблюдает поведение pairing/disconnect. Оператор включается в петлю ТОЛЬКО на
необратимых шагах (нет автоматического merge/push, никакой factory-reset, никакого
касания пользовательских данных без явного chat-да). Read-only и обратимое — контур
делает сам, отчитываясь по факту.

> ⚠ **Устарело с 2026-08-16 и 2026-08-30.** Шина `cc-interchat-bus` ЗАКРЫТА (§9,
> замена — файловый ящик `_interchat\inbox\`, #BUS-2). Пошаговая отчётность Цензору
> через `step_report.py` ОТМЕНЕНА вместе с сужением его роли (оператор, 2026-08-30):
> Цензор не часть рабочего процесса и работу контуров не контролирует. Контур
> закрывает цикл разработка→проверка САМ (§31.D, ярусы 0–1); надзорному контуру идёт
> только эскалация «не справляюсь». Упоминания `step_report.py` ниже по тексту —
> исторические, инструментом больше не пользоваться.

## 2. Hardware/software inventory

- Телефон: модель — `<phone-model>` (проверить `adb shell getprop ro.product.model`
  во время Phase 0).
- Android: версия — `<android-version>` (проверить `adb shell getprop
  ro.build.version.release` и `ro.build.version.sdk`).
- adb: версия — `<adb-version>` (`adb version` на PC; зафиксировать в Phase 0,
  чтобы исключить дрейф между сессиями).
- USB-debugging: должен быть включён, отпечаток PC авторизован на телефоне.
  Зафиксировать стартовое состояние developer-options и больше его не трогать.
- Дозиметр: AtomFast, конкретная модель — `<atomfast-model>` (проверить надпись
  на устройстве или в about-экране приложения; известные модели семейства —
  Atom Fast, Atom Tag, Atom Swift, см. Gammaspectacular product pages).
- Firmware дозиметра: `<firmware-version>` — проверить во время Phase 0 через
  about-экран приложения или, если экспонирован, через BLE Device Information
  Service (UUID 0x180A, характеристика Firmware Revision String 0x2A26).
- Приложение AtomFast на телефоне: package name — **проверить во время Phase 0**.
  Кандидаты, известные публично:
  - `com.youratom.scid` — это legacy-приложение «Dosimeter Atom»; было снято с
    Google Play 2023-03-07, поддерживало в том числе AtomFast 8055 (источник:
    AppBrain/Google Play cached listing, accessed via web search).
  - Текущая линейка приложений производителя называется ATOM-SWIFT / ATOM-SPECTRA
    / Atom Radiometer (iOS) — для этих приложений конкретный Android package
    name публично не нашёлся, проверить во время Phase 0 командой
    `adb shell pm list packages -f | grep -i atom`.
  - До подтверждения — использовать плейсхолдер `com.atomfast.*` в скриптах и
    разрешать совпадение по любому `*atom*` package, найденному на телефоне.
- BLE-характеристики дозиметра: проверить во время Phase 0 (см. секцию 4).
  Никаких UUID здесь не зафиксировано, т.к. публичной спеки производителя на
  GATT-уровне найти не удалось.

## 3. adb safety map — reversible vs irreversible

Главная таблица контура. Перед КАЖДОЙ adb-командой контур определяет
action_class по этой таблице. `read_only` и `reversible` — выполняются сразу,
`irreversible` — стоп, step_report со статусом `needs_approval`, ждать
chat-да оператора. `BLOCKED` — не выполнять никогда, даже с одобрением
(оператор должен сам сделать руками на стенде).

Правило для приложений: контур может чистить свои собственные артефакты
(test-APK, который САМ поставил; файлы в своей scratch-папке) — это
reversible. Артефакты, которые существовали до контура или которые положил
оператор — irreversible.

| Команда | Class | Notes |
|---|---|---|
| `adb devices` | read_only | Просто список подключённых устройств. |
| `adb version` | read_only | Версия adb на PC. |
| `adb shell getprop` | read_only | Системные свойства, состояние сборки. |
| `adb shell getprop ro.product.model` | read_only | Модель телефона. |
| `adb shell dumpsys battery` | read_only | Состояние батареи, до/после теста. |
| `adb shell dumpsys bluetooth_manager` | read_only | Состояние BT-стека, paired devices. |
| `adb shell pm list packages` | read_only | Список установленных пакетов. |
| `adb shell pm list packages -f \| grep -i atom` | read_only | Поиск package name приложения AtomFast. |
| `adb shell pm path <pkg>` | read_only | Путь APK на устройстве. |
| `adb shell dumpsys package <pkg>` | read_only | Метаданные пакета, permissions. |
| `adb logcat -d -t 200` | read_only | Дамп последних 200 строк лога. Read-only. |
| `adb logcat -d -s <TAG>` | read_only | Фильтр по тегу, дамп. |
| `adb shell screencap -p /sdcard/Android/data/<contour-scratch>/files/x.png` | reversible | Скриншот В свою scratch-папку. Cleanup в конце задачи. |
| `adb pull <contour-scratch-path> ~/lab/...` | reversible | Скачать со своей scratch-папки. |
| `adb install <test.apk>` | reversible | Установка test-APK, который контур контролирует. `adb uninstall` откатывает. |
| `adb install -r -t <test.apk>` | reversible | Replace + allow test packages, того же класса. |
| `adb uninstall <test-pkg-контура>` | reversible | Удаление пакета, который сам же поставил. |
| `adb shell am start -n <pkg>/<activity>` | reversible | Запуск activity; force-stop откатывает. |
| `adb shell am force-stop <pkg>` | reversible | Остановка процесса, без потери данных. |
| `adb shell input tap X Y` | reversible | Имитация тапа. |
| `adb shell input swipe X1 Y1 X2 Y2` | reversible | Имитация свайпа. |
| `adb shell input keyevent <KEY>` | reversible | Имитация системной кнопки (BACK, HOME). |
| `adb shell svc bluetooth enable` | reversible | Включить BT-радио. Парная операция к disable. |
| `adb shell svc bluetooth disable` | reversible | Выключить BT-радио. Зафиксировать стартовое состояние, вернуть. |
| `adb shell settings put global bluetooth_on 1` | reversible | Альтернативный путь включения BT. То же, что svc. |
| `adb shell settings put global bluetooth_on 0` | reversible | Выключение BT. Вернуть в финале. |
| `adb shell cmd bluetooth_manager <subcmd>` | проверить в Phase 0 | Поведение зависит от Android-версии; subcmd `enable`/`disable` — reversible; subcmd, чистящие paired-list — irreversible. До Phase 0 — обращаться как с irreversible. |
| `adb reboot` | reversible | Ребут без потери данных. Записать факт в step_report. |
| `adb shell pm clear <test-pkg-контура>` | reversible | Wipe data СВОЕГО test-APK. |
| `adb shell rm <contour-scratch-file>` | reversible | Удаление из своей scratch-папки. |
| `adb shell pm clear com.youratom.scid` | **irreversible** | Wipe данных приложения AtomFast — потеря калибровки/истории измерений оператора. |
| `adb shell pm clear <atomfast-pkg>` | **irreversible** | То же для любого пакета AtomFast/Atom Swift/Atom Spectra. |
| `adb shell pm clear <любой не-test pkg>` | **irreversible** | Wipe пользовательских данных. |
| `adb uninstall <atomfast-pkg>` | **irreversible** | Снос приложения оператора. |
| `adb shell pm uninstall <любой не-test pkg>` | **irreversible** | То же. |
| `adb shell pm uninstall --user 0 <pkg>` | **irreversible** | Disable системного приложения. |
| `adb shell rm -rf /sdcard/...` вне scratch-папки контура | **irreversible** | Касается пользовательского хранилища. |
| `adb push <file> /sdcard/DCIM/` | **irreversible** | DCIM = реальная галерея пользователя. |
| `adb push <file> /sdcard/Pictures/` | **irreversible** | Pictures = реальное хранилище фото. |
| `adb push <file> /sdcard/Download/` | **irreversible** | Download = реальное хранилище пользователя; класть только в scratch. |
| `adb shell settings put <table> <key> <val>` вне test-зоны | **irreversible** | Системные/secure/global таблицы — менять только то, что точно вернёшь, иначе irreversible. |
| `adb shell content insert ...` в provider'ы пользователя | **irreversible** | Контакты, календарь, медиа — трогать нельзя. |
| `adb reboot bootloader` | **irreversible** | Телефон уходит в bootloader, контур не вытащит без оператора. |
| `adb reboot recovery` | **irreversible** | То же, recovery. |
| `adb shell bluetoothctl remove <MAC>` / `bt-device --remove` | **irreversible** | Развязывание дозиметра; повторное pairing может требовать физического подтверждения на устройстве. |
| `fastboot flash <partition> <img>` | **BLOCKED** | Прошивка разделов — оператор делает руками, не контур. |
| `fastboot erase <partition>` | **BLOCKED** | То же. |
| `adb shell recovery --wipe_data` | **BLOCKED** | Factory reset. |
| `adb shell pm clear --user 0 android` | **BLOCKED** | Сброс ядра системы. |
| `adb shell svc power shutdown` | **BLOCKED** | Без оператора рядом контур не сможет вернуть телефон в строй. |
| `adb root` / `adb disable-verity` | **BLOCKED** | Меняет режим устройства, оператор делает руками. |

Граница «test-pkg контура» / «не-test pkg» жёстко: test-pkg — это APK, который
именно ЭТОТ контур установил в ТЕКУЩЕМ task'е, по пути, который оператор явно
передал в step-prompt'е. Всё остальное — не-test, включая прошлые test-APK от
прошлых сессий контура. Если есть сомнение «мой ли это APK» — это уже не мой.

## 4. Bluetooth Low Energy — что экспонирует AtomFast

Публичной GATT-спеки производителя в открытых источниках найти не удалось
(производственный сайт Gammaspectacular указывает только «Bluetooth 4.0
wireless interface», без UUID и описания характеристик). Поэтому конкретные
UUID сервисов/характеристик в этом файле НЕ зафиксированы — **проверить во
время Phase 0** одним из способов:

- На PC через `bluetoothctl` (Linux/WSL) или `Bluetooth LE Explorer` (Windows)
  — соединиться напрямую с дозиметром, перечислить services и
  characteristics.
- На телефоне через приложение nRF Connect (Nordic Semiconductor) — увидеть
  GATT-дерево, описания характеристик, формат notify-пакетов. Это
  read-only-обзор, дозиметр от этого не страдает.
- Через Android HCI snoop log: включить «Enable Bluetooth HCI snoop log» в
  developer-options, воспроизвести сессию с приложением AtomFast, забрать
  `/sdcard/btsnoop_hci.log`, разобрать Wireshark'ом. Если developer-option
  была выключена при старте контура — это касание состояния, фиксируем как
  irreversible и идём за оператором.

Generic-процедура GATT-discovery, которую контур использует:
1. Просканировать (scan) с устройства-наблюдателя, найти advertisment
   AtomFast по locally significant имени (плейсхолдер — то, что покажет
   само устройство, ловить через scan).
2. Подключиться, выполнить service-discovery.
3. Перечислить characteristics, прочитать descriptors (CCCD), найти те, что
   имеют свойство `notify` или `indicate` — это, скорее всего, поток
   измерений.
4. Подписаться на notify, записать сырые байты ≥30 секунд, отдать в отчёт.
5. Если в дереве присутствует стандартный сервис Device Information (UUID
   0x180A) — прочитать Manufacturer Name (0x2A29), Model Number (0x2A24),
   Firmware Revision (0x2A26), Hardware Revision (0x2A27). Это стандартный
   read, безопасен.

Важно про обратимость с BLE-стороны: дозиметр AtomFast — измерительный
прибор. С точки зрения контура операции «прочитать характеристику», «подписаться
на notify» — пассивны для дозиметра, дозиметр не теряет состояние от того,
что его читают. Поэтому BLE-чтения через приложение AtomFast или напрямую с
GATT — это read_only с точки зрения оператора.

Что НЕ read-only на BLE-стороне:
- Запись в characteristic, если такая существует и принимает команды
  конфигурации. До тех пор, пока неизвестно, что именно она конфигурирует,
  любые `gatttool char-write-req` / эквиваленты на write-characteristic
  AtomFast — **irreversible** (могут менять калибровку или режим). Не делать
  без явного «go» оператора.
- Pairing/bonding на уровне Android: pairing — reversible (можно повторить).
  Unpair/forget — **irreversible**, если повторное pairing требует
  физического нажатия кнопки на дозиметре, которого контур сделать не может.
  По умолчанию контур считает unpair дозиметра AtomFast irreversible.
- Любые попытки OTA firmware update через приложение — **BLOCKED**.
  Контур не запускает firmware-update сценарий ни при каких условиях,
  даже если приложение его само предложит — контур делает back и рапортует
  step_report со статусом `needs_approval`.

## 5. First worked task — example

Сценарий, который оператор может выдать контуру день-один:

> «Установи test-APK X (лежит у меня в `~/lab/test-apk-x.apk`), запусти его,
> прогони через 5 последовательных считываний с дозиметра, скачай app-логи
> в `~/lab/logs/`. По done — отправь Цензору step_report с: dumpsys battery
> до/после, 5 значениями измерений, SHA256 этого APK, хвостом logcat.»

Шаги контура и их action_class:

1. `step_report.py --status running --note "phase 0 inventory"` — отметить
   старт.
2. `adb devices` → read_only. Убедиться, что телефон видится, серийник
   совпадает с зафиксированным в Phase 0.
3. `adb shell getprop ro.product.model` / `ro.build.version.release` →
   read_only. Записать в отчёт.
4. `adb shell dumpsys battery > ~/lab/logs/battery_before.txt` → read_only.
5. `sha256sum ~/lab/test-apk-x.apk` (на PC) → read_only. Записать SHA256 в
   отчёт.
6. `adb install ~/lab/test-apk-x.apk` → reversible. Зафиксировать пакет
   `<test-pkg>`, который этот APK регистрирует (через `aapt dump badging`
   на PC ИЛИ `adb shell pm list packages -3` до/после).
7. `adb shell am start -n <test-pkg>/<main-activity>` → reversible. Запуск.
8. Для каждого из 5 считываний:
   - `adb shell input tap X Y` → reversible. Тап на «измерить» (координаты
     X Y определить через `adb shell uiautomator dump` + парсинг XML —
     это read-only).
   - Дождаться завершения считывания (sleep + проверка через uiautomator
     dump).
   - `adb shell screencap -p /sdcard/Android/data/<test-pkg>/files/r<N>.png`
     → reversible (скрин кладётся в private-папку test-приложения, не в
     DCIM).
   - `adb pull /sdcard/Android/data/<test-pkg>/files/r<N>.png ~/lab/logs/`
     → reversible.
9. `adb logcat -d -t 500 > ~/lab/logs/logcat_tail.txt` → read_only.
10. `adb shell dumpsys battery > ~/lab/logs/battery_after.txt` → read_only.
11. `adb shell am force-stop <test-pkg>` → reversible.
12. `adb uninstall <test-pkg>` → reversible (контур чистит то, что сам
    установил).
13. `step_report.py --status done --note "5 readings collected" \
    --attach ~/lab/logs/battery_before.txt \
    --attach ~/lab/logs/battery_after.txt \
    --attach ~/lab/logs/logcat_tail.txt \
    --field sha256=<...> --field readings='[v1,v2,v3,v4,v5]'`

Оператор-гейт в этом сценарии: **не срабатывает ни разу**. Все шаги либо
read_only, либо reversible (контур ставит/сносит СВОЙ test-APK, кладёт
файлы в private-папку этого же test-APK, читает системные dump'ы). Цензор
получает done-репорт и адъюдицирует факты.

Если на любом шаге адаптация потребует irreversible (например,
определилось, что приложение AtomFast не открывается из-за устаревшей
версии BT-стека, и контур хочет сделать `pm clear` или `uninstall`
системного компонента) — контур СТОПается, шлёт `--status needs_approval
--note "<точное действие, action_class=irreversible, причина>"` и ждёт
chat-да оператора.

## 6. Anti-patterns specific to this rig

- Не делать `adb shell pm clear com.youratom.scid` / `pm clear
  <atomfast-pkg>` чтобы «сбросить состояние» приложения AtomFast. Это
  стирает калибровочную историю и предыдущие измерения, которые могут быть
  нужны оператору. Хочешь чистого состояния — используй СВОЙ test-APK,
  не приложение оператора.
- Не делать unpair/forget дозиметра, чтобы «починить» залипшую BT-связь.
  Повторное pairing у BLE-устройств часто требует физического нажатия
  кнопки на самом устройстве, которого контур через adb сделать не может;
  оператор может остаться с развязанным дозиметром и без удалённого
  способа его подцепить обратно. Сначала пробовать `svc bluetooth
  disable` + `enable` (это reversible toggle), потом ребут телефона, и
  только после этого — поход к оператору за подтверждением unpair.
- Не ставить НЕ test-APK ни из какого источника, кроме пути, который
  оператор явно указал в step-prompt'е. Никаких `wget`/`curl` за APK,
  никаких репозиториев, никаких сайдлоадов «найденного в интернете
  фикса».
- Не включать developer-options, ADB-over-WiFi, OEM unlock, USB-config
  modes, которые были выключены при старте контура. Зафиксировать
  стартовое состояние developer-options в Phase 0 (`adb shell settings
  get global development_settings_enabled` и т.п.) и в конце задачи
  убедиться, что оно совпадает.
- Не пушить файлы в `/sdcard/DCIM/`, `/sdcard/Pictures/`,
  `/sdcard/Movies/`, `/sdcard/Music/`, `/sdcard/Documents/`,
  `/sdcard/Download/` — это реальное пользовательское хранилище. Контур
  работает в своей scratch-папке: `/sdcard/Android/data/<contour-scratch
  -pkg>/files/` (private-storage test-APK, который контур поставил и
  снесёт), и чистит её в конце задачи через `adb shell rm` или
  `pm clear <test-pkg>`.
- Не запускать OTA firmware update на дозиметре, даже если приложение
  само предложит. Это BLOCKED — оператор делает руками или говорит
  явное «go».
- Не пытаться писать в неизвестные write-характеристики GATT-дерева
  AtomFast — это потенциально меняет калибровку или режим работы
  прибора. Read и notify — пассивны и безопасны, write — irreversible
  до явного разрешения.

## 7. Закрытие

Дозиметр AtomFast пассивен по отношению к контуру: он измеряет ионизирующее
излучение, контур наблюдает результат через приложение или GATT-notify.
На стороне дозиметра у контура НЕТ командной поверхности, которой можно
было бы что-то непоправимо сломать — read и подписка на notify не
оставляют следа. Все живые провода необратимости — на стороне телефона:
системные настройки, пользовательские данные в `/sdcard/`, чужие
установленные приложения, операции с разделами через fastboot/recovery.
Карта обратимости из секции 3 — про телефон, не про дозиметр; читай её
как «что я могу испортить на стенде оператора», не как «что я могу
испортить на дозиметре».
