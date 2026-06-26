# NVIDIA P-State Switcher

[![Лицензия: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://python.org)
[![PyQt6](https://img.shields.io/badge/PyQt-6-green.svg)](https://riverbankcomputing.com/software/pyqt/)

> **English**: [README.md](README.md)

Утилита для ручного принудительного переключения P-состояний (производительности) видеокарт NVIDIA из системного трея.

---

## Быстрый старт

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
- **nvidia-pstate** + **nvidia-smi** — часть проприетарного драйвера NVIDIA
- **Python 3.12+**
- **PyQt6** (см. таблицу ниже)

## Установка

### PyQt6 по дистрибутиву

| Дистрибутив    | Команда                              |
|----------------|--------------------------------------|
| Fedora         | `sudo dnf install python3-pyqt6`     |
| Arch / CachyOS | `sudo pacman -S python-pyqt6`        |
| openSUSE       | `sudo zypper install python3-pyqt6`  |
| Debian / Ubuntu| `sudo apt install python3-pyqt6`     |
| pip (любой)    | `pip install pyqt6`                  |

### Скрипт

```bash
curl -LO https://raw.githubusercontent.com/uladziislau/nvidia-pstate-switcher/main/nvidia-pstate-switcher.py
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

| P-State | Описание           | Пояснение                     |
|---------|--------------------|-------------------------------|
| P0      | Max perf           | Максимальная производительность|
| P2      | Balanced           | Сбалансированный режим        |
| P3      | Medium             | Среднее энергосбережение      |
| P5      | Idle               | Простой / низкое потребление  |
| P8      | Deep idle          | Глубокий простой              |
| Auto    | Driver control     | Динамически (решает драйвер)  |

> Потребление зависит от модели GPU. Актуальная мощность отображается в подсказке при наведении на иконку в трее или в `nvidia-smi`.

### Пользовательский список P-state

Ваша видеокарта может поддерживать другой набор P-состояний. Список в меню можно переопределить в конфиге:

```json
{
  "pstate": "16",
  "autostart": true,
  "pstates": ["0", "2", "3", "5", "8", "12", "15"]
}
```

Отредактируйте `~/.config/nvidia-pstate-switcher.conf` и перезапустите приложение.

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
