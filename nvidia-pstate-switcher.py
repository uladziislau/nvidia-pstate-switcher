#!/usr/bin/env python3
"""
System Tuning Tray — GPU P-state, CPU governor, Power Profile integration,
and per-unit power monitoring (instantaneous + 1-min average).

Uses async QProcess to never block the UI thread.
"""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
from collections import deque
from statistics import mean
from typing import Optional

from PyQt6 import QtCore, QtGui, QtNetwork, QtWidgets
from PyQt6 import QtDBus

# ── constants ──────────────────────────────────────────────

# KDE Power Profile → GPU P-state + CPU governor
PROFILE_MAP = {
    "power-saver":  {"pstate": "5",  "governor": "powersave"},
    "balanced":     {"pstate": "2",  "governor": "powersave"},
    "performance":  {"pstate": "0",  "governor": "performance"},
}

PROFILE_LABELS = {
    "power-saver": "🔋 Power Saver",
    "balanced":    "⚖️  Balanced",
    "performance": "🚀 Performance",
}

GOVERNOR_LABELS = {
    "powersave":    "powersave (dynamic)",
    "performance":  "performance (max freq)",
}

DEFAULT_PSTATES = {
    "0": "Max perf",
    "2": "Balanced",
    "3": "Medium",
    "5": "Idle",
    "8": "Deep idle",
}

CONFIG_DIR = os.path.expanduser("~/.config")
CONFIG_FILE = os.path.join(CONFIG_DIR, "nvidia-pstate-switcher.conf")
AUTOSTART_FILE = os.path.expanduser(
    "~/.config/autostart/nvidia-pstate-switcher.desktop"
)
AUTOSTART_ENTRY = (
    "[Desktop Entry]\n"
    "Type=Application\n"
    "Name=System Tuning Tray\n"
    "Comment=GPU P-state, CPU governor, Power Profiles, Power Monitor\n"
    f"Exec=/usr/local/bin/nvidia-pstate-switcher\n"
    "Icon=nvidia-pstate-switcher\n"
    "Categories=System;Hardware;\n"
    "Terminal=false\n"
    "StartupNotify=false\n"
    "X-KDE-autostart-condition=true\n"
)
APP_DESKTOP_PATH = os.path.expanduser(
    "~/.local/share/applications/nvidia-pstate-switcher.desktop"
)
APP_DESKTOP_ENTRY = (
    "[Desktop Entry]\n"
    "Type=Application\n"
    "Name=System Tuning Tray\n"
    "Comment=GPU P-state, CPU governor, Power Profiles, Power Monitor\n"
    "Exec=/usr/local/bin/nvidia-pstate-switcher\n"
    "Icon=nvidia-pstate-switcher\n"
    "Categories=System;Hardware;\n"
    "Terminal=false\n"
    "StartupNotify=false\n"
)
IPC_SERVER = "nvidia-pstate-switcher"
IPC_SOCKET = os.path.join("/tmp", IPC_SERVER)

CPU_GOVERNOR_PATH = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"

PP_SERVICE = "net.hadess.PowerProfiles"
PP_PATH    = "/net/hadess/PowerProfiles"
PP_IFACE   = "net.hadess.PowerProfiles"
PP_PROPS   = "org.freedesktop.DBus.Properties"

POWER_HISTORY_SECONDS = 60  # rolling window for 1-min average


# ── helpers ────────────────────────────────────────────────

def _resolve_bin(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    local = os.path.expanduser(f"~/.local/bin/{name}")
    if os.path.isfile(local) and os.access(local, os.X_OK):
        return local
    return name


def _load_config() -> dict:
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"pstate": "16", "autostart": True}


def _save_config(cfg: dict) -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f)


def _autostart_enabled() -> bool:
    return os.path.isfile(AUTOSTART_FILE)


def _set_autostart(enabled: bool) -> None:
    if enabled:
        os.makedirs(os.path.dirname(AUTOSTART_FILE), exist_ok=True)
        with open(AUTOSTART_FILE, "w") as f:
            f.write(AUTOSTART_ENTRY)
    else:
        try:
            os.remove(AUTOSTART_FILE)
        except FileNotFoundError:
            pass


def _ensure_desktop_entry():
    if os.path.isfile(APP_DESKTOP_PATH):
        return
    os.makedirs(os.path.dirname(APP_DESKTOP_PATH), exist_ok=True)
    with open(APP_DESKTOP_PATH, "w") as f:
        f.write(APP_DESKTOP_ENTRY)


def _read_cpu_governor() -> str:
    try:
        with open(CPU_GOVERNOR_PATH) as f:
            return f.read().strip()
    except (FileNotFoundError, OSError):
        return "N/A"


def _read_power_profile_db() -> Optional[str]:
    try:
        bus = QtDBus.QDBusConnection.systemBus()
        iface = QtDBus.QDBusInterface(PP_SERVICE, PP_PATH, PP_PROPS, bus)
        reply = iface.call("Get", PP_IFACE, "ActiveProfile")
        if reply.arguments():
            val = reply.arguments()[0]
            return str(val).strip("\"'")
    except Exception:
        pass
    return None
def _windscribe_traffic() -> tuple[Optional[float], Optional[str]]:
    """Fetch Windscribe remaining traffic (MB) and account name."""
    try:
        result = subprocess.run(
            ["/usr/bin/windscribe-cli", "status"],
            capture_output=True, text=True, timeout=8,
        )
        if result.returncode != 0:
            return None, None

        # Parse traffic: "Использование данных: 8,65 ГБ / 10,00 ГБ"
        remaining = None
        for line in result.stdout.split('\n'):
            if '\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435 \u0434\u0430\u043d\u043d\u044b\u0445' in line:
                import re
                m = re.search(r'([\d.,]+)\s*\S+\s*/\s*([\d.,]+)\s*(\S+)', line)
                if m:
                    total_val = float(m.group(2).replace(',', '.'))
                    used_val = float(m.group(1).replace(',', '.'))
                    total_unit = m.group(3).replace('\u0411', '').upper()
                    remaining = _to_mb(total_val, total_unit) - _to_mb(used_val, total_unit)
                    remaining = max(0, remaining)
                    break

        # Account from state file
        account = None
        current_file = os.path.expanduser("~/.config/windscribe/current")
        if os.path.isfile(current_file):
            account = open(current_file).read().strip() or None

        return remaining, account
    except Exception:
        return None, None


def _to_mb(value: float, unit: str) -> float:
    """Convert value to MB. Unit: G=ГБ, M=МБ, K=КБ."""
    u = unit.upper()
    if u in ('G', '\u0413'):
        return value * 1000
    if u in ('M', '\u041c'):
        return value
    if u in ('K', '\u041a'):
        return value / 1000
    return value



# ── power monitor (rolling 1-min average) ─────────────────

class PowerMonitor:
    """Tracks GPU / CPU package / DRAM power with a rolling average."""

    def __init__(self, window: int = POWER_HISTORY_SECONDS, interval: float = 2.0):
        size = max(1, int(window / interval))
        self._window = size
        self._interval = interval
        self.gpu_now = 0.0
        self.gpu: deque[float] = deque(maxlen=size)
        self.pkg: deque[float] = deque(maxlen=size)
        self.dram: deque[float] = deque(maxlen=size)

        self._last_pkg_uj: Optional[int] = None
        self._last_dram_uj: Optional[int] = None

    def add_gpu_sample(self, watts: float):
        self.gpu_now = watts
        self.gpu.append(watts)

    def add_rapl_samples(self, pkg_uj: int, dram_uj: int):
        if self._last_pkg_uj is not None and self._last_dram_uj is not None:
            dt = self._interval
            # microjoules → watts
            pkg_w = (pkg_uj - self._last_pkg_uj) / 1_000_000 / dt
            dram_w = (dram_uj - self._last_dram_uj) / 1_000_000 / dt
            # Clamp and sanity check (avoid counter wrap or outlier)
            pkg_w = max(0.0, min(pkg_w, 300.0))
            dram_w = max(0.0, min(dram_w, 50.0))
        else:
            pkg_w = 0.0
            dram_w = 0.0

        self._last_pkg_uj = pkg_uj
        self._last_dram_uj = dram_uj
        self.pkg.append(pkg_w)
        self.dram.append(dram_w)

    @property
    def gpu_avg(self) -> float:
        return mean(self.gpu) if self.gpu else 0.0

    @property
    def pkg_avg(self) -> float:
        return mean(self.pkg) if self.pkg else 0.0

    @property
    def dram_avg(self) -> float:
        return mean(self.dram) if self.dram else 0.0

    @property
    def total_now(self) -> float:
        return self.gpu_now + (self.pkg[-1] if self.pkg else 0) \
               + (self.dram[-1] if self.dram else 0)

    @property
    def total_avg(self) -> float:
        return self.gpu_avg + self.pkg_avg + self.dram_avg

    def summary(self) -> str:
        """Multi-line summary for tooltip."""
        pkg_w = f"{self.pkg[-1]:.1f}" if self.pkg else "?"
        dram_w = f"{self.dram[-1]:.1f}" if self.dram else "?"
        lines = [
            f"GPU:   {self.gpu_now:.1f} W  |  avg {self.gpu_avg:.1f} W",
            f"PKG:   {pkg_w} W  |  avg {self.pkg_avg:.1f} W",
            f"DRAM:  {dram_w} W  |  avg {self.dram_avg:.1f} W",
            f"TOTAL: {self.total_now:.1f} W  |  avg {self.total_avg:.1f} W",
        ]
        return "\n".join(lines)


# ── icon cache ────────────────────────────────────────────

_icon_cache: dict[str, QtGui.QIcon] = {}


def _render_icon(label: str, size: int = 48) -> QtGui.QIcon:
    if label in _icon_cache:
        return _icon_cache[label]

    pm = QtGui.QPixmap(size, size)
    pm.fill(QtCore.Qt.GlobalColor.transparent)

    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QtGui.QPainter.RenderHint.TextAntialiasing)

    font = QtGui.QFont("sans-serif", size // 2, QtGui.QFont.Weight.Bold)
    path = QtGui.QPainterPath()
    path.addText(0, 0, font, label)

    bounds = path.boundingRect()
    tx = (size - bounds.width()) / 2 - bounds.x()
    ty = (size - bounds.height()) / 2 - bounds.y()
    path.translate(tx, ty)

    p.setPen(QtGui.QPen(QtGui.QColor("white"), 2))
    p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
    p.drawPath(path)

    p.setBrush(QtGui.QColor("white"))
    p.setPen(QtCore.Qt.PenStyle.NoPen)
    p.drawPath(path)

    p.end()

    icon = QtGui.QIcon(pm)
    _icon_cache[label] = icon
    return icon


# ── runner: async QProcess wrapper ────────────────────────

class CommandRunner(QtCore.QObject):
    finished = QtCore.pyqtSignal(str)
    failed = QtCore.pyqtSignal(str)

    def run(self, cmd: list[str]):
        self._proc = QtCore.QProcess(self)
        self._proc.setProgram(cmd[0])
        self._proc.setArguments(cmd[1:])
        self._proc.setProcessChannelMode(
            QtCore.QProcess.ProcessChannelMode.MergedChannels
        )
        self._proc.finished.connect(self._on_done)
        self._proc.errorOccurred.connect(self._on_error)
        self._proc.start()

    def _on_done(self, exit_code: int):
        out = self._proc.readAllStandardOutput().data().decode().strip()
        if exit_code == 0:
            self.finished.emit(out)
        else:
            self.failed.emit(out or f"exit code {exit_code}")

    def _on_error(self, err):
        self.failed.emit(f"cannot launch: {self._proc.program()} ({err.name})")


# ── tray app ──────────────────────────────────────────────

class PStateSwitcher(QtWidgets.QSystemTrayIcon):

    _current_label = "\u2014"
    _current_profile: Optional[str] = None
    _current_governor = "N/A"

    def __init__(self, parent=None):
        super().__init__(parent)

        self._cfg = _load_config()
        self._nvidia_pstate_bin = _resolve_bin("nvidia-pstate")
        self._nvidia_smi_bin = _resolve_bin("nvidia-smi")
        self._rapl_read_bin = _resolve_bin("power-rapl-read.sh")
        _ensure_desktop_entry()

        custom = self._cfg.get("pstates")
        self._pstates = (
            {p: DEFAULT_PSTATES.get(p, "") for p in custom}
            if custom
            else dict(DEFAULT_PSTATES)
        )

        # Power monitor (rolling 1-min average)
        self._power = PowerMonitor()

        # ── Runners ──
        self._smi_runner = CommandRunner()
        self._smi_runner.finished.connect(self._on_smi_ok)
        self._smi_runner.failed.connect(lambda _: None)

        self._pstate_setter = CommandRunner()
        self._pstate_setter.finished.connect(lambda _: self._refresh_later())
        self._pstate_setter.failed.connect(self._on_setter_fail)

        self._gov_setter = CommandRunner()
        self._gov_setter.finished.connect(lambda _: self._refresh_later())
        self._gov_setter.failed.connect(
            lambda m: self.showMessage("CPU Governor", f"Failed:\n{m}",
                                       QtWidgets.QSystemTrayIcon.MessageIcon.Warning, 3000)
        )

        self._rapl_runner = CommandRunner()
        self._rapl_runner.finished.connect(self._on_rapl_ok)
        self._rapl_runner.failed.connect(lambda _: None)

        # ── Tray setup ──
        self.setIcon(_render_icon("\u2014"))
        self.setToolTip("System Tuning Tray\n(right-click for menu)")

        self.monitor_timer = QtCore.QTimer(self)
        self.monitor_timer.timeout.connect(self._refresh)
        self.monitor_timer.start(2000)

        # Read initial states
        self._current_governor = _read_cpu_governor()
        self._current_profile = _read_power_profile_db()

        self._build_menu()

        saved_pstate = self._cfg.get("pstate", "16")
        self._mark_active_pstate(saved_pstate)
        if saved_pstate != "16":
            self._run_pstate_setter(saved_pstate)

        # DBus listener for KDE Power Profiles
        self._connect_power_profiles()

        # First refresh
        self._refresh()

        # ── IPC ──
        self._ipc_server = QtNetwork.QLocalServer(self)
        self._ipc_server.setSocketOptions(
            QtNetwork.QLocalServer.SocketOption.WorldAccessOption
        )
        QtNetwork.QLocalServer.removeServer(IPC_SERVER)
        if not self._ipc_server.listen(IPC_SERVER):
            print("IPC server failed to listen", file=sys.stderr)
        self._ipc_server.newConnection.connect(self._on_ipc_connection)

        self.activated.connect(self._on_activate)
        self.show()

    # ── public API ────────────────────────────────────────

    def set_state(self, ps_id: str) -> None:
        """Manually set GPU P-state from menu."""
        self._cfg["pstate"] = ps_id
        _save_config(self._cfg)
        self._mark_active_pstate(ps_id)
        self._run_pstate_setter(ps_id)

    def set_power_profile(self, profile: str) -> None:
        """Set KDE Power Profile via DBus (two-way sync)."""
        bus = QtDBus.QDBusConnection.systemBus()
        iface = QtDBus.QDBusInterface(PP_SERVICE, PP_PATH, PP_PROPS, bus)
        iface.call("Set", PP_IFACE, "ActiveProfile",
                   QtCore.QVariant(profile))

    def set_cpu_governor(self, governor: str) -> None:
        """Set CPU governor directly."""
        self._gov_setter.run(["sudo", "cpupower", "frequency-set", "-g", governor])

    # ── DBus Power Profiles ──────────────────────────────

    def _connect_power_profiles(self):
        # Polling for profile changes in _refresh() instead of DBus signal
        # (QVariantMap type not registered in PyQt6/QtDBus)
        pass

    def _apply_profile(self, profile: str) -> None:
        self._current_profile = profile
        settings = PROFILE_MAP.get(profile)
        if settings is None:
            self._refresh_later()
            return

        self._cfg["pstate"] = settings["pstate"]
        _save_config(self._cfg)
        self._mark_active_pstate(settings["pstate"])
        self._run_pstate_setter(settings["pstate"])
        self._gov_setter.run(
            ["sudo", "cpupower", "frequency-set", "-g", settings["governor"]]
        )

    # ── menu ──────────────────────────────────────────────

    def _build_menu(self):
        self._menu = QtWidgets.QMenu()
        self._ps_actions = []
        self._gov_actions = []
        self._profile_actions = []

        # ── Power Profile section ──
        header = self._menu.addAction("Power Profile")
        header.setEnabled(False)
        self._make_bold(header)

        self._profile_actions = []
        for pid, plabel in PROFILE_LABELS.items():
            a = self._menu.addAction(plabel)
            a.setData(("profile", pid))
            a.setCheckable(True)
            self._profile_actions.append(a)

        self._menu.addSeparator()

        # ── CPU Governor section ──
        header = self._menu.addAction("CPU Governor")
        header.setEnabled(False)
        self._make_bold(header)

        for gov, glabel in GOVERNOR_LABELS.items():
            a = self._menu.addAction(glabel)
            a.setData(("governor", gov))
            a.setCheckable(True)
            self._gov_actions.append(a)

        self._menu.addSeparator()

        # ── GPU P-state section ──
        header = self._menu.addAction("GPU P-State")
        header.setEnabled(False)
        self._make_bold(header)

        for ps_id, label in self._pstates.items():
            text = f"P{ps_id} \u2014 {label}" if label else f"P{ps_id}"
            action = self._menu.addAction(text)
            action.setData(("pstate", ps_id))
            action.setCheckable(True)
            self._ps_actions.append(action)

        self._menu.addSeparator()

        auto_action = self._menu.addAction("Auto (driver control)")
        auto_action.setData(("pstate", "16"))
        auto_action.setCheckable(True)
        self._ps_actions.append(auto_action)

        self._menu.addSeparator()

        # ── Status info (read-only) ──
        self._info_gov = self._menu.addAction(f"CPU: {self._current_governor}")
        self._info_gov.setEnabled(False)
        self._info_profile = self._menu.addAction(
            f"Profile: {self._current_profile or 'N/A'}"
        )
        self._info_profile.setEnabled(False)

        # ── Power meter section ──
        self._menu.addSeparator()
        header = self._menu.addAction("Power (now / 1min avg)")
        header.setEnabled(False)
        self._make_bold(header)

        self._info_power_gpu = self._menu.addAction("GPU: -- W")
        self._info_power_gpu.setEnabled(False)
        self._info_power_pkg = self._menu.addAction("PKG: -- W")
        self._info_power_pkg.setEnabled(False)
        self._info_power_dram = self._menu.addAction("DRAM: -- W")
        self._info_power_dram.setEnabled(False)
        self._info_power_total = self._menu.addAction("TOTAL: -- W")
        self._info_power_total.setEnabled(False)

        # ── Windscribe VPN ──
        self._menu.addSeparator()
        header = self._menu.addAction("Windscribe VPN")
        header.setEnabled(False)
        self._make_bold(header)

        self._info_windscribe = self._menu.addAction("VPN: -- GB")
        self._info_windscribe.setEnabled(False)

        self._menu.addSeparator()

        # ── Settings ──
        as_action = self._menu.addAction("Run at startup")
        as_action.setCheckable(True)
        as_action.setChecked(_autostart_enabled())
        as_action.triggered.connect(self._toggle_autostart)

        self._menu.addSeparator()
        self._menu.addAction("Refresh", self._refresh)
        self._menu.addAction("Quit", QtWidgets.QApplication.quit)

        self._menu.triggered.connect(self._on_menu_trigger)
        self.setContextMenu(self._menu)

    @staticmethod
    def _make_bold(action: QtGui.QAction):
        f = action.font()
        f.setBold(True)
        action.setFont(f)

    def _mark_active_pstate(self, active_ps: str) -> None:
        raw = active_ps.replace("P", "")
        for a in self._ps_actions:
            a.setChecked(a.data()[1] == raw)

    def _mark_active_governor(self, gov: str) -> None:
        for a in self._gov_actions:
            a.setChecked(a.data()[1] == gov)

    def _mark_active_profile(self, profile: str) -> None:
        for a in self._profile_actions:
            a.setChecked(a.data()[1] == profile)

    def _toggle_autostart(self, checked: bool) -> None:
        _set_autostart(checked)
        self._cfg["autostart"] = checked
        _save_config(self._cfg)

    def _on_menu_trigger(self, action: QtGui.QAction):
        data = action.data()
        if not isinstance(data, tuple) or len(data) != 2:
            return
        kind, value = data

        if kind == "profile":
            self.set_power_profile(value)
            # Profile change will be picked up by DBus listener
        elif kind == "governor":
            self.set_cpu_governor(value)
        elif kind == "pstate":
            self.set_state(value)

    def _on_ipc_connection(self):
        conn = self._ipc_server.nextPendingConnection()
        if conn and conn.waitForReadyRead(2000):
            if conn.readAll().data() == b"show_menu":
                self.showMessage(
                    "System Tuning Tray",
                    "Already running \u2014 check the system tray.",
                    QtWidgets.QSystemTrayIcon.MessageIcon.Information, 3000)
        if conn:
            conn.close()

    def _on_activate(self, reason):
        if reason == QtWidgets.QSystemTrayIcon.ActivationReason.DoubleClick:
            self._refresh()

    # ── async refresh (every 2s) ──────────────────────────

    def _run_pstate_setter(self, ps_id: str) -> None:
        self._pstate_setter.run([self._nvidia_pstate_bin, "-ps", ps_id])

    def _refresh_later(self):
        """Schedule a refresh on the next timer tick (debounce)."""
        QtCore.QTimer.singleShot(100, self._refresh)

    def _refresh(self):
        """Fetch all metrics in parallel."""
        # GPU stats
        self._smi_runner.run([
            self._nvidia_smi_bin, "--query-gpu=index,power.draw,pstate",
            "--format=csv,noheader,nounits",
        ])
        # RAPL energy counters
        self._rapl_runner.run(["sudo", "/usr/local/bin/power-rapl-read.sh"])
        # CPU governor + profile (fast local reads)
        self._current_governor = _read_cpu_governor()
        new_profile = _read_power_profile_db()
        if new_profile and new_profile != self._current_profile:
            self._current_profile = new_profile
            self._apply_profile(new_profile)

    # ── GPU result handler ────────────────────────────────

    def _on_smi_ok(self, raw: str):
        parts = [p.strip() for p in raw.split(",")]
        if len(parts) < 3:
            return
        _idx, power, pstate = parts
        try:
            gpu_w = float(power)
        except ValueError:
            gpu_w = 0.0

        self._power.add_gpu_sample(gpu_w)

        # Update icon if P-state changed
        if pstate != self._current_label:
            self._current_label = pstate
            self.setIcon(_render_icon(pstate))

        self._update_display()

    # ── RAPL result handler ───────────────────────────────    # ── Windscribe result handler ──────────────────────────