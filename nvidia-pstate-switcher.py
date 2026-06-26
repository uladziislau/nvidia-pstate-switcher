#!/usr/bin/env python3
"""
NVIDIA P-State Switcher — system tray app for manually setting GPU performance state.
P-state and autostart preferences persist across reboots.
Uses async QProcess to avoid blocking the UI thread.
"""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys

from PyQt6 import QtCore, QtGui, QtNetwork, QtWidgets

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
    "Name=NVIDIA P-State Switcher\n"
    "Comment=Manually set NVIDIA GPU performance state from system tray\n"
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
    "Name=NVIDIA P-State Switcher\n"
    "Comment=Manually control NVIDIA GPU performance state from system tray\n"
    "Exec=/usr/local/bin/nvidia-pstate-switcher\n"
    "Icon=nvidia-pstate-switcher\n"
    "Categories=System;Hardware;\n"
    "Terminal=false\n"
    "StartupNotify=false\n"
)
# QLocalServer("nvidia-pstate-switcher") creates /tmp/nvidia-pstate-switcher on Linux
IPC_SERVER = "nvidia-pstate-switcher"
IPC_SOCKET = os.path.join("/tmp", IPC_SERVER)


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
    """Run shell commands without blocking the UI thread."""

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

    def __init__(self, parent=None):
        super().__init__(parent)

        self._cfg = _load_config()

        self._nvidia_pstate_bin = _resolve_bin("nvidia-pstate")
        self._nvidia_smi_bin = _resolve_bin("nvidia-smi")
        _ensure_desktop_entry()

        custom = self._cfg.get("pstates")
        self._pstates = (
            {p: DEFAULT_PSTATES.get(p, "") for p in custom}
            if custom
            else dict(DEFAULT_PSTATES)
        )

        self._runner = CommandRunner()
        self._runner.finished.connect(self._on_smi_ok)
        self._runner.failed.connect(self._on_smi_fail)

        self._setter = CommandRunner()
        self._setter.finished.connect(lambda _: self._refresh())
        self._setter.failed.connect(self._on_setter_fail)

        self.setIcon(_render_icon("\u2014"))

        self.monitor_timer = QtCore.QTimer(self)
        self.monitor_timer.timeout.connect(self._refresh)
        self.monitor_timer.start(2000)

        self._build_menu()

        saved_pstate = self._cfg.get("pstate", "16")
        self._mark_active_pstate(saved_pstate)
        if saved_pstate != "16":
            self._run_pstate_setter(saved_pstate)

        self._refresh()

        self._ipc_server = QtNetwork.QLocalServer(self)
        self._ipc_server.setSocketOptions(
            QtNetwork.QLocalServer.SocketOption.WorldAccessOption
        )
        QtNetwork.QLocalServer.removeServer(IPC_SERVER)
        if not self._ipc_server.listen(IPC_SERVER):
            print("IPC server failed to listen", file=sys.stderr)
        self._ipc_server.newConnection.connect(self._on_ipc_connection)

        self.setToolTip("NVIDIA P-State\n(right-click for menu)")
        self.activated.connect(self._on_activate)
        self.show()

    # ── public ────────────────────────────────────────────

    def set_state(self, ps_id: str) -> None:
        self._cfg["pstate"] = ps_id
        _save_config(self._cfg)
        self._mark_active_pstate(ps_id)
        self._run_pstate_setter(ps_id)

    # ── menu ──────────────────────────────────────────────

    def _build_menu(self):
        self._menu = QtWidgets.QMenu()
        self._ps_actions = []

        for ps_id, label in self._pstates.items():
            text = f"P{ps_id} \u2014 {label}" if label else f"P{ps_id}"
            action = self._menu.addAction(text)
            action.setData(ps_id)
            action.setCheckable(True)
            self._ps_actions.append(action)

        self._menu.addSeparator()

        auto_action = self._menu.addAction("Auto (driver control)")
        auto_action.setData("16")
        auto_action.setCheckable(True)
        self._ps_actions.append(auto_action)

        self._menu.addSeparator()

        as_action = self._menu.addAction("Run at startup")
        as_action.setCheckable(True)
        as_action.setChecked(_autostart_enabled())
        as_action.triggered.connect(self._toggle_autostart)

        self._menu.addSeparator()
        self._menu.addAction("Refresh", self._refresh)
        self._menu.addAction("Quit", QtWidgets.QApplication.quit)

        self._menu.triggered.connect(self._on_menu_trigger)
        self.setContextMenu(self._menu)

    def _mark_active_pstate(self, active_ps: str) -> None:
        raw = active_ps.replace("P", "")
        for a in self._ps_actions:
            a.setChecked(a.data() == raw)

    def _toggle_autostart(self, checked: bool) -> None:
        _set_autostart(checked)
        self._cfg["autostart"] = checked
        _save_config(self._cfg)

    def _on_menu_trigger(self, action: QtGui.QAction):
        ps_id = action.data()
        if isinstance(ps_id, str):
            self.set_state(ps_id)

    def _on_ipc_connection(self):
        conn = self._ipc_server.nextPendingConnection()
        if conn and conn.waitForReadyRead(2000):
            if conn.readAll().data() == b"show_menu":
                self._show_notification()
        if conn:
            conn.close()

    def _show_notification(self):
        self.showMessage(
            "NVIDIA P-State Switcher",
            "Already running \u2014 check the system tray.",
            QtWidgets.QSystemTrayIcon.MessageIcon.Information,
            3000,
        )

    def _on_activate(self, reason):
        if reason == QtWidgets.QSystemTrayIcon.ActivationReason.DoubleClick:
            self._refresh()

    # ── async refresh ─────────────────────────────────────

    def _run_pstate_setter(self, ps_id: str) -> None:
        self._setter.run([self._nvidia_pstate_bin, "-ps", ps_id])

    def _refresh(self):
        self._runner.run(
            [
                self._nvidia_smi_bin, "--query-gpu=index,power.draw,pstate",
                "--format=csv,noheader,nounits",
            ]
        )

    def _on_smi_ok(self, raw: str):
        parts = [p.strip() for p in raw.split(",")]
        if len(parts) < 3:
            return
        _idx, power, pstate = parts
        self.setToolTip(
            f"NVIDIA GPU\n"
            f"  P-state:  {pstate}\n"
            f"  Power:    {power} W"
        )
        if pstate != self._current_label:
            self._current_label = pstate
            self.setIcon(_render_icon(pstate))

    def _on_smi_fail(self, msg: str):
        pass  # next poll will retry

    def _on_setter_fail(self, msg: str):
        self.showMessage(
            "NVIDIA P-State",
            f"Failed to set P-state:\n{msg}",
            QtWidgets.QSystemTrayIcon.MessageIcon.Critical,
            5000,
        )


# ── entry point ───────────────────────────────────────────

def _try_activate_existing() -> bool:
    """Try to signal the running instance. Returns True if it exists."""
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(1)
        s.connect(IPC_SOCKET)
        s.sendall(b"show_menu")
        s.close()
        return True
    except (FileNotFoundError, ConnectionRefusedError, OSError):
        return False


def main():
    parser = argparse.ArgumentParser(
        description="NVIDIA P-State system tray switcher"
    )
    parser.add_argument(
        "--oneshot", metavar="P",
        help="Set P-state and exit (e.g. --oneshot 5).",
    )
    args = parser.parse_args()

    if args.oneshot:
        subprocess.check_call([_resolve_bin("nvidia-pstate"), "-ps", args.oneshot])
        return

    if _try_activate_existing():
        return

    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("nvidia-pstate-switcher")
    app.setQuitOnLastWindowClosed(False)

    _ = PStateSwitcher()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
