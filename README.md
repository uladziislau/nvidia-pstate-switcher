# NVIDIA P-State Switcher

A lightweight system tray tool to manually force NVIDIA GPU performance states (P-states) on Linux.

Утилита для ручного принудительного переключения P-состояний видеокарт NVIDIA из системного трея.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](/LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://python.org)
[![PyQt6](https://img.shields.io/badge/PyQt-6-green.svg)](https://riverbankcomputing.com/software/pyqt/)

---

## Quick Start · Быстрый старт

**EN** — Install and run in 3 steps:

```bash
# 1. Install PyQt6
sudo dnf install python3-pyqt6          # Fedora
# sudo pacman -S python-pyqt6           # Arch
# sudo apt install python3-pyqt6        # Ubuntu/Debian

# 2. Download & install
curl -LO https://raw.githubusercontent.com/uladziislau/nvidia-pstate-switcher/main/nvidia-pstate-switcher.py
chmod +x nvidia-pstate-switcher.py
sudo mv nvidia-pstate-switcher.py /usr/local/bin/nvidia-pstate-switcher

# 3. Run
/usr/local/bin/nvidia-pstate-switcher
```

> **GNOME users**: you need `gnome-shell-extension-appindicator` for tray icons.

**RU** — Установка и запуск в 3 шага:

```bash
# 1. Установка PyQt6
sudo dnf install python3-pyqt6             # Fedora
# sudo pacman -S python-pyqt6              # Arch
# sudo apt install python3-pyqt6           # Ubuntu/Debian

# 2. Скачать и установить
curl -LO https://raw.githubusercontent.com/uladziislau/nvidia-pstate-switcher/main/nvidia-pstate-switcher.py
chmod +x nvidia-pstate-switcher.py
sudo mv nvidia-pstate-switcher.py /usr/local/bin/nvidia-pstate-switcher

# 3. Запуск
/usr/local/bin/nvidia-pstate-switcher
```

> **Пользователям GNOME**: требуется расширение `gnome-shell-extension-appindicator` для иконок в трее.

---

## Why? · Зачем?

**EN** — NVIDIA's GSP firmware can keep the GPU in a high-performance P-state (P0) even at idle, consuming ~45W on the desktop. This typically happens on Wayland with KWin, where the kernel driver sees ~2 atomic KMS commits per frame — enough to fool the firmware's activity heuristic.

This tool lets you manually force a lower P-state (like P5 at ~21W) when you don't need GPU performance.

> This is a **workaround**, not a fix. The root cause is in NVIDIA's closed-source GSP firmware (bug #5474539). See [the investigation section](#investigation--расследование) for details.

**RU** — GSP-прошивка NVIDIA может оставлять GPU в высокопроизводительном P-состоянии (P0) даже в простое, потребляя ~45 Вт на рабочем столе. Это типично для Wayland + KWin: драйвер видит ~2 атомарных KMS-коммита на кадр, что превышает порог активности прошивки.

Утилита позволяет вручную форсировать пониженное P-состояние (например, P5 ~21 Вт), когда производительность GPU не нужна.

> Это **временное решение**, а не исправление. Корень проблемы — в закрытой GSP-прошивке NVIDIA (баг #5474539). Подробности — в [разделе расследования](#investigation--расследование).

---

## Features · Возможности

**EN**
- System tray icon showing current P-state (e.g. `P0`, `P5`)
- Right-click menu to force any P-state or reset to Auto (driver‑controlled)
- Persists your P-state preference across reboots
- Autostart integration with your desktop environment
- `--oneshot` mode for scripting
- Non‑blocking UI — uses `QProcess` internally, never freezes on slow `nvidia-smi`

**RU**
- Иконка в трее с текущим P-состоянием (например, `P0`, `P5`)
- Меню по правому клику: выбор любого P-состояния или возврат в Auto (управление драйвером)
- Сохранение выбранного P-состояния между перезагрузками
- Автозапуск вместе с рабочим столом
- Режим `--oneshot` для скриптов
- Неблокирующий UI — используется `QProcess`, интерфейс не зависает

---

## Requirements · Требования

**EN**
- **Linux** with an NVIDIA GPU
- **nvidia-pstate** + **nvidia-smi** — part of the proprietary NVIDIA driver
- **Python 3.12+**
- **PyQt6** (see distro table below)

**RU**
- **Linux** с видеокартой NVIDIA
- **nvidia-pstate** + **nvidia-smi** — часть проприетарного драйвера NVIDIA
- **Python 3.12+**
- **PyQt6** (см. таблицу ниже)

---

## Installation · Установка

### PyQt6 by distro · PyQt6 по дистрибутиву

| Distro · Дистрибутив    | Command · Команда                     |
|-------------------------|---------------------------------------|
| Fedora                  | `sudo dnf install python3-pyqt6`      |
| Arch / CachyOS          | `sudo pacman -S python-pyqt6`         |
| openSUSE                | `sudo zypper install python3-pyqt6`   |
| Debian / Ubuntu         | `sudo apt install python3-pyqt6`      |
| pip (any)               | `pip install pyqt6`                   |

### The script · Скрипт

```bash
curl -LO https://raw.githubusercontent.com/uladziislau/nvidia-pstate-switcher/main/nvidia-pstate-switcher.py
chmod +x nvidia-pstate-switcher.py
sudo mv nvidia-pstate-switcher.py /usr/local/bin/nvidia-pstate-switcher

# Run · Запуск
/usr/local/bin/nvidia-pstate-switcher
```

---

## Usage · Использование

### System tray · Системный трей

**EN** — Right-click the tray icon to:
- Select a P-state (P0 / P2 / P3 / P5 / P8) — a checkmark appears on the active mode
- Choose **Auto (driver control)** to return control to the NVIDIA driver
- Toggle **Run at startup**
- **Refresh** the display
- **Quit** the app

Double-click the icon to refresh immediately.

The tooltip shows the current P-state and power draw, updated every 2 seconds.

**RU** — Правый клик по иконке:
- Выбрать P-состояние (P0 / P2 / P3 / P5 / P8) — галочка показывает активный режим
- **Auto (driver control)** — вернуть управление драйверу NVIDIA
- Включить/выключить **Run at startup**
- **Refresh** — обновить данные
- **Quit** — выйти

Двойной клик по иконке — немедленное обновление.

Подсказка при наведении показывает текущее P-состояние и потребляемую мощность, обновляется каждые 2 секунды.

### Command line · Командная строка

```bash
# Force P5 (idle, ~21W) · Форсировать P5 (простой, ~21 Вт)
nvidia-pstate-switcher --oneshot 5

# Reset to driver-controlled Auto mode · Сбросить в Auto
nvidia-pstate-switcher --oneshot 16
```

---

## P-States · P-Состояния

| P-State | EN Label      | RU описание                  |
|---------|---------------|------------------------------|
| P0      | Max perf      | Максимальная производительность|
| P2      | Balanced      | Сбалансированный режим        |
| P3      | Medium        | Среднее энергосбережение      |
| P5      | Idle          | Простой / низкое потребление  |
| P8      | Deep idle     | Глубокий простой              |
| Auto    | Driver control| Динамически (решает драйвер)  |

> Power draw varies by GPU model. Check your actual power via the tooltip or `nvidia-smi`.
> Потребление зависит от модели GPU. Актуальная мощность — в подсказке при наведении или в `nvidia-smi`.

### Custom P-state list · Пользовательский список

**EN** — Your GPU may support a different set of P-states. Override the menu by adding `pstates` to the config file:

```json
{
  "pstate": "16",
  "autostart": true,
  "pstates": ["0", "2", "3", "5", "8", "12", "15"]
}
```

Edit `~/.config/nvidia-pstate-switcher.conf` and restart the app.

**RU** — Ваша видеокарта может поддерживать другой набор P-состояний. Список в меню можно переопределить в конфиге:

```json
{
  "pstate": "16",
  "autostart": true,
  "pstates": ["0", "2", "3", "5", "8", "12", "15"]
}
```

Отредактируйте `~/.config/nvidia-pstate-switcher.conf` и перезапустите приложение.

---

## How it works · Как это работает

**EN** — The script calls `nvidia-pstate -ps <id>` — the same command `nvidia-pstate` exposes for manual P-state control. `nvidia-smi --query-gpu=pstate,power.draw` is polled every 2 seconds to update the icon and tooltip.

Key implementation choices:
- **QProcess instead of `subprocess`** — all external commands run asynchronously so the UI never blocks
- **Icon cache** — each P-state label is rendered once into a `QPixmap` and reused
- **`showMessage()` on errors** — if `nvidia-pstate` or `nvidia-smi` fail, you get a native desktop notification

**RU** — Скрипт вызывает `nvidia-pstate -ps <id>` — ту же команду, которую `nvidia-pstate` предоставляет для ручного управления P-состояниями. `nvidia-smi --query-gpu=pstate,power.draw` опрашивается каждые 2 секунды для обновления иконки и подсказки.

Ключевые решения в коде:
- **QProcess вместо `subprocess`** — все внешние команды запускаются асинхронно, UI не блокируется
- **Кэш иконок** — каждое P-состояние рендерится в `QPixmap` один раз и переиспользуется
- **`showMessage()` при ошибках** — если `nvidia-pstate` или `nvidia-smi` упали, вы получите нативное уведомление

---

## Investigation · Расследование

**EN** — This tool was born out of a deep investigation into why the GTX 1660 SUPER stays in P0 on Wayland. Key findings:

- **Root cause**: NVIDIA GSP firmware bug #5474539 — the firmware treats `TEST_ONLY` atomic KMS commits as GPU load
- **KWin generates 2 commits per frame**: 1 `TEST_ONLY` + 1 `REAL` → ~126 ioctls/sec at 63 FPS
- The firmware's activity threshold is around 102–114 commits/sec, so even a static desktop crosses it
- An LD_PRELOAD filter was prototyped (return 0 on `TEST_ONLY` to halve the commits) but caused rendering artifacts (ghost cursor, stutter)
- A 1-line KWin patch (`return true` in `drm_commit.cpp:test()`) would fix this permanently, but requires building a patched `kwin` package
- Warp Terminal keeps a CUDA compute context alive, adding ~45W regardless of P-state

See the full log at [xeon-gtx-fedora-workstation](https://github.com/uladziislau/xeon-gtx-fedora-workstation) (private).

**RU** — Этот инструмент родился из глубокого исследования причин, по которым GTX 1660 SUPER остаётся в P0 на Wayland. Ключевые находки:

- **Корень**: баг GSP-прошивки NVIDIA #5474539 — прошивка считает `TEST_ONLY` атомарные KMS-коммиты за нагрузку GPU
- **KWin генерирует 2 коммита на кадр**: 1 `TEST_ONLY` + 1 `REAL` → ~126 ioctl/сек при 63 FPS
- Порог активности прошивки — около 102–114 коммитов/сек, статический рабочий стол его превышает
- Был прототип LD_PRELOAD-фильтра (возвращать 0 на `TEST_ONLY`) — вызывал артефакты рендеринга (призрак курсора, статтеры)
- Патч KWin в 1 строку (`return true` в `drm_commit.cpp:test()`) исправил бы проблему навсегда, но требует сборки модифицированного пакета `kwin`
- Warp Terminal держит активным CUDA-контекст, добавляя ~45 Вт независимо от P-состояния

Полный лог расследования: [xeon-gtx-fedora-workstation](https://github.com/uladziislau/xeon-gtx-fedora-workstation) (приватный).

---

## License · Лицензия

MIT
