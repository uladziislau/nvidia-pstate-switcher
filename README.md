# NVIDIA P-State Switcher

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://python.org)
[![PyQt6](https://img.shields.io/badge/PyQt-6-green.svg)](https://riverbankcomputing.com/software/pyqt/)

> **Русский**: [README.ru.md](README.ru.md)

A lightweight system tray tool to manually force NVIDIA GPU performance states (P-states) on Linux.

---

## Quick Start

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

---

## Why?

NVIDIA's GSP firmware can keep the GPU in a high-performance P-state (P0) even at idle, consuming ~45W on the desktop. This typically happens on Wayland with KWin, where the kernel driver sees ~2 atomic KMS commits per frame — enough to fool the firmware's activity heuristic.

This tool lets you manually force a lower P-state (like P5 at ~21W) when you don't need GPU performance.

> This is a **workaround**, not a fix. The root cause is in NVIDIA's closed-source GSP firmware (bug #5474539). See [the investigation section](#investigation) for details.

## Features

- System tray icon showing current P-state (e.g. `P0`, `P5`)
- Right-click menu to force any P-state or reset to Auto (driver‑controlled)
- Persists your P-state preference across reboots
- Autostart integration with your desktop environment
- `--oneshot` mode for scripting
- Non‑blocking UI — uses `QProcess` internally, never freezes on slow `nvidia-smi`

## Requirements

- **Linux** with an NVIDIA GPU
- **nvidia-pstate** + **nvidia-smi** — part of the proprietary NVIDIA driver
- **Python 3.12+**
- **PyQt6** (see distro table below)

## Installation

### PyQt6 by distro

| Distro         | Command                              |
|----------------|--------------------------------------|
| Fedora         | `sudo dnf install python3-pyqt6`     |
| Arch / CachyOS | `sudo pacman -S python-pyqt6`        |
| openSUSE       | `sudo zypper install python3-pyqt6`  |
| Debian / Ubuntu| `sudo apt install python3-pyqt6`     |
| pip (any)      | `pip install pyqt6`                  |

### The script

```bash
curl -LO https://raw.githubusercontent.com/uladziislau/nvidia-pstate-switcher/main/nvidia-pstate-switcher.py
chmod +x nvidia-pstate-switcher.py
sudo mv nvidia-pstate-switcher.py /usr/local/bin/nvidia-pstate-switcher

# Run
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

| P-State | Label           | Description                  |
|---------|-----------------|------------------------------|
| P0      | Max perf        | Maximum performance          |
| P2      | Balanced        | Balanced performance/power   |
| P3      | Medium          | Medium power saving          |
| P5      | Idle            | Idle / low power             |
| P8      | Deep idle       | Deep idle (maximum saving)   |
| Auto    | Driver control  | Dynamic (NVIDIA driver decides) |

> Power draw varies by GPU model. Check your actual power via the tooltip (hover the tray icon) or `nvidia-smi`.

### Custom P-state list

Your GPU may support a different set of P-states. You can override the menu items by adding a `pstates` list to the config file:

```json
{
  "pstate": "16",
  "autostart": true,
  "pstates": ["0", "2", "3", "5", "8", "12", "15"]
}
```

Edit `~/.config/nvidia-pstate-switcher.conf` and restart the app.

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
