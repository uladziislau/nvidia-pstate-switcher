# NVIDIA P-State Switcher

A lightweight system tray tool to manually force NVIDIA GPU performance states (P-states) on Linux.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://python.org)
[![PyQt6](https://img.shields.io/badge/PyQt-6-green.svg)](https://riverbankcomputing.com/software/pyqt/)

---

## Why?

NVIDIA's GSP firmware can keep the GPU in a high-performance P-state (P0) even at idle, consuming ~45W on the desktop. This typically happens on Wayland with KWin, where the kernel driver sees ~2 atomic KMS commits per frame — enough to fool the firmware's activity heuristic.

This tool lets you manually force a lower P-state (like P5 at ~21W) when you don't need GPU performance.

> This is a **workaround**, not a fix. The root cause is in NVIDIA's closed-source GSP firmware (bug #5474539). See [the investigation notes](#investigation) for details.

## Features

- System tray icon showing current P-state (e.g. `P0`, `P5`)
- Right-click menu to force any P-state or reset to Auto (driver‑controlled)
- Persists your P-state preference across reboots
- Autostart integration with your desktop environment
- `--oneshot` mode for scripting
- Non‑blocking UI — uses `QProcess` internally, never freezes on slow `nvidia-smi`

## Requirements

- **Linux** with an NVIDIA GPU
- **nvidia-pstate** — part of NVIDIA driver package (ships with the proprietary driver)
- **nvidia-smi** — also part of the NVIDIA driver
- **Python 3.12+**
- **PyQt6** — `python3-pyqt6` on Fedora / `python3-pyqt6` on Arch / `pyqt6` on pip

## Installation

```bash
# Install PyQt6 (Fedora)
sudo dnf install python3-pyqt6

# Download the script
curl -LO https://raw.githubusercontent.com/uladziislau/nvidia-pstate-switcher/main/nvidia-pstate-switcher.py

# Make it executable and place it in PATH
chmod +x nvidia-pstate-switcher.py
sudo mv nvidia-pstate-switcher.py /usr/local/bin/nvidia-pstate-switcher

# Run it
/usr/local/bin/nvidia-pstate-switcher
```

## Usage

### System tray

Right-click the tray icon to:
- Select a P-state (P0 / P2 / P3 / P5 / P8) — a checkmark appears on the active mode
- Choose **Auto (driver control)** to return control to the NVIDIA driver
- Toggle **Run at startup**
- **Refresh** the display
- **Quit** the app

Double-click the icon to refresh immediately.

The tooltip shows the current P-state and power draw, updated every 2 seconds.

### Command line

```bash
# Force P5 (idle, ~21W)
nvidia-pstate-switcher --oneshot 5

# Reset to driver-controlled Auto mode
nvidia-pstate-switcher --oneshot 16
```

## P-States

| P-State | Label           | Typical Power |
|---------|-----------------|---------------|
| P0      | Max performance | ~45–65 W      |
| P2      | Balanced        | ~40 W         |
| P3      | Medium          | ~37 W         |
| P5      | Idle            | ~21–27 W      |
| P8      | Deep idle       | ~21 W         |
| Auto    | Driver control  | dynamic       |

## How it works

The script calls `nvidia-pstate -ps <id>` under the hood — the same command `nvidia-pstate` exposes for manual P-state control. `nvidia-smi --query-gpu=pstate,power.draw` is polled every 2 seconds to update the icon and tooltip.

The key implementation choices:
- **QProcess instead of `subprocess`** — all external commands run asynchronously so the UI never blocks
- **Icon cache** — each P-state label is rendered once into a `QPixmap` and reused
- **`showMessage()` on errors** — if `nvidia-pstate` or `nvidia-smi` fail, you get a native desktop notification

## Investigation

This tool was born out of a deep investigation into why the GTX 1660 SUPER stays in P0 on Wayland. Key findings:

- **Root cause**: NVIDIA GSP firmware bug #5474539 — the firmware treats `TEST_ONLY` atomic KMS commits as GPU load
- **KWin generates 2 commits per frame**: 1 `TEST_ONLY` + 1 `REAL` → ~126 ioctls/sec at 63 FPS
- The firmware's activity threshold is around 102–114 commits/sec, so even a static desktop crosses it
- An LD_PRELOAD filter was prototyped (return 0 on `TEST_ONLY` to halve the commits) but caused rendering artifacts (ghost cursor, stutter)
- A 1-line KWin patch (`return true` in `drm_commit.cpp:test()`) would fix this permanently, but requires building a patched `kwin` package
- Warp Terminal keeps a CUDA compute context alive, adding ~45W regardless of P-state

See the full log at [xeon-gtx-fedora-workstation](https://github.com/uladziislau/xeon-gtx-fedora-workstation) (private).

## License

MIT

---

# NVIDIA P-State Switcher

Утилита для ручного принудительного переключения P-состояний (производительности) видеокарт NVIDIA из системного трея.

[![Лицензия: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://python.org)
[![PyQt6](https://img.shields.io/badge/PyQt-6-green.svg)](https://riverbankcomputing.com/software/pyqt/)

---

## Зачем?

GSP-прошивка NVIDIA может оставлять GPU в высокопроизводительном P-состоянии (P0) даже в простое, потребляя ~45 Вт на рабочем столе. Это типично для Wayland + KWin: драйвер видит ~2 атомарных KMS-коммита на кадр, что превышает порог активности прошивки.

Утилита позволяет вручную форсировать пониженное P-состояние (например, P5 ~21 Вт), когда производительность GPU не нужна.

> Это **временное решение**, а не исправление. Корень проблемы — в закрытой GSP-прошивке NVIDIA (баг #5474539). Подробности — в [разделе расследования](#расследование).

## Возможности

- Иконка в трее с текущим P-состоянием (например, `P0`, `P5`)
- Меню по правому клику: выбор любого P-состояния или возврат в Auto (управление драйвером)
- Сохранение выбранного P-состояния между перезагрузками
- Автозапуск вместе с рабочим столом
- Режим `--oneshot` для скриптов
- Неблокирующий UI — используется `QProcess`, интерфейс не зависает

## Требования

- **Linux** с видеокартой NVIDIA
- **nvidia-pstate** — часть пакета проприетарного драйвера NVIDIA
- **nvidia-smi** — тоже часть драйвера
- **Python 3.12+**
- **PyQt6** — `python3-pyqt6` в Fedora / `python3-pyqt6` в Arch / `pyqt6` через pip

## Установка

```bash
# Установка PyQt6 (Fedora)
sudo dnf install python3-pyqt6

# Скачать скрипт
curl -LO https://raw.githubusercontent.com/uladziislau/nvidia-pstate-switcher/main/nvidia-pstate-switcher.py

# Сделать исполняемым и поместить в PATH
chmod +x nvidia-pstate-switcher.py
sudo mv nvidia-pstate-switcher.py /usr/local/bin/nvidia-pstate-switcher

# Запуск
/usr/local/bin/nvidia-pstate-switcher
```

## Использование

### Системный трей

Правый клик по иконке:
- Выбрать P-состояние (P0 / P2 / P3 / P5 / P8) — галочка показывает активный режим
- **Auto (driver control)** — вернуть управление драйверу NVIDIA
- Включить/выключить **Run at startup**
- **Refresh** — обновить данные
- **Quit** — выйти

Двойной клик по иконке — немедленное обновление.

Подсказка при наведении показывает текущее P-состояние и потребляемую мощность, обновляется каждые 2 секунды.

### Командная строка

```bash
# Форсировать P5 (idle, ~21 Вт)
nvidia-pstate-switcher --oneshot 5

# Сбросить в Auto (управление драйвером)
nvidia-pstate-switcher --oneshot 16
```

## P-Состояния

| P-State | Описание           | Типичная мощность |
|---------|--------------------|-------------------|
| P0      | Максимальная произв.| ~45–65 Вт         |
| P2      | Сбалансированный   | ~40 Вт            |
| P3      | Средний            | ~37 Вт            |
| P5      | Простой            | ~21–27 Вт         |
| P8      | Глубокий простой   | ~21 Вт            |
| Auto    | Управление драйвером| динамически       |

## Как это работает

Скрипт вызывает `nvidia-pstate -ps <id>` — ту же команду, которую `nvidia-pstate` предоставляет для ручного управления P-состояниями. `nvidia-smi --query-gpu=pstate,power.draw` опрашивается каждые 2 секунды для обновления иконки и подсказки.

Ключевые решения в коде:
- **QProcess вместо `subprocess`** — все внешние команды запускаются асинхронно, UI не блокируется
- **Кэш иконок** — каждое P-состояние рендерится в `QPixmap` один раз и переиспользуется
- **`showMessage()` при ошибках** — если `nvidia-pstate` или `nvidia-smi` упали, вы получите нативное уведомление

## Расследование

Этот инструмент родился из глубокого исследования причин, по которым GTX 1660 SUPER остаётся в P0 на Wayland. Ключевые находки:

- **Корень**: баг GSP-прошивки NVIDIA #5474539 — прошивка считает `TEST_ONLY` атомарные KMS-коммиты за нагрузку GPU
- **KWin генерирует 2 коммита на кадр**: 1 `TEST_ONLY` + 1 `REAL` → ~126 ioctl/сек при 63 FPS
- Порог активности прошивки — около 102–114 коммитов/сек, так что даже статический рабочий стол его превышает
- Был прототип LD_PRELOAD-фильтра (возвращать 0 на `TEST_ONLY`, уменьшая вдвое число коммитов), но он вызывал артефакты рендеринга (призрак курсора, статтеры)
- Патч KWin в 1 строку (`return true` в `drm_commit.cpp:test()`) исправил бы проблему навсегда, но требует сборки модифицированного пакета `kwin`
- Warp Terminal держит активным CUDA-контекст, добавляя ~45 Вт независимо от P-состояния

Полный лог расследования: [xeon-gtx-fedora-workstation](https://github.com/uladziislau/xeon-gtx-fedora-workstation) (приватный).

## Лицензия

MIT
