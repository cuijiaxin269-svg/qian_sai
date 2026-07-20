import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMainWindow, QPlainTextEdit, QPushButton,
    QScrollArea, QTabWidget, QVBoxLayout, QWidget,
)

from app.constants import APP_TITLE
from communication import commands
from communication.serial_manager import SerialManager
from services.device_service import DeviceService
from services.measurement_service import MeasurementService
from services.one_key_service import OneKeyService
from services.scan_service import ScanService
from ui.tab_initialization import InitializationTab
from ui.tab_measurement import MeasurementTab
from ui.tab_one_key import OneKeyTab
from ui.tab_relay import RelayTab
from ui.tab_scan import ScanTab


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1080, 760)
        self._serial = SerialManager()
        self._device = DeviceService(self._serial)
        self._measurement = MeasurementService(self._serial)
        self._scan = ScanService(self._serial, self._device)
        self._one_key = OneKeyService(self._serial, self._device, self._measurement)
        self._build_ui()
        self._bind_signals()

    def _build_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)
        self.tabs = QTabWidget()
        self.init_tab = InitializationTab(self._serial, self._device)
        self.relay_tab = RelayTab(self._device, self.log)
        self.tabs.addTab(self._scrollable(self.init_tab), "Tab1 串口与参数设置")
        self.measurement_tab = MeasurementTab(self._device, self._measurement, self.log)
        self.tabs.addTab(self._scrollable(self.measurement_tab), "Tab2 单一路径数据采集")
        self.tabs.addTab(self._scrollable(ScanTab(self._scan, self.log)), "Tab3 C-V 曲线扫描")
        self.tabs.addTab(self._scrollable(OneKeyTab(self._one_key, self.log)), "Tab4 一键测量")
        self.tabs.addTab(self._scrollable(self.relay_tab), "Tab5 继电器矩阵控制")
        layout.addWidget(self.tabs)

        self.log_panel = QWidget()
        log_layout = QVBoxLayout(self.log_panel)
        log_layout.setContentsMargins(0, 0, 0, 0)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(5000)
        self.log_view.setMinimumHeight(150)
        self.log_view.setPlaceholderText("串口发送和接收信息会显示在这里")
        log_header = QHBoxLayout()
        log_header.addWidget(QLabel("通信日志"))
        log_header.addStretch()
        clear_log = QPushButton("清空日志")
        clear_log.clicked.connect(self.log_view.clear)
        log_header.addWidget(clear_log)
        layout.addLayout(log_header)
        log_layout.addWidget(self.log_view)
        self.log_toggle = QPushButton("展开通信日志")
        self.log_toggle.clicked.connect(self._toggle_log_panel)
        log_header.addWidget(self.log_toggle)
        layout.addWidget(self.log_panel)
        self.log_panel.setVisible(False)
        safe_button = QPushButton("安全停止：关闭 DDS / 偏压设置为 0 V")
        safe_button.setStyleSheet("font-weight: bold; color: #9b111e;")
        safe_button.clicked.connect(self._safe_stop)
        layout.addWidget(safe_button)
        self.setCentralWidget(central)
        self.statusBar().showMessage("未连接单片机")

    @staticmethod
    def _scrollable(widget: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(widget)
        return scroll

    def _toggle_log_panel(self) -> None:
        show_panel = self.log_panel.isHidden()
        self.log_panel.setVisible(show_panel)
        self.log_toggle.setText("隐藏通信日志" if show_panel else "展开通信日志")

    def _bind_signals(self) -> None:
        self._serial.connected.connect(self._on_connected)
        self._serial.disconnected.connect(self._on_disconnected)
        self._serial.received.connect(self._on_received)
        self._serial.sent.connect(lambda text: self.log(f"发送 → {text}"))
        self._serial.communication_error.connect(lambda message: self.log(f"串口错误：{message}"))

    def _on_connected(self, port: str) -> None:
        self._device.set_control_ready(False)
        self._measurement.set_confirmed_bias(None)
        self.init_tab.set_connection_state(True, f"：{port}")
        self.init_tab.set_boot_state(False, "已连接，等待 STM32 安全自检完成")
        self.statusBar().showMessage(f"已连接 {port}，等待 SAFETY_BOOT_DONE")
        self.log(f"已连接：{port}；控制功能已锁定，等待 SAFETY_BOOT_DONE")

    def _on_disconnected(self) -> None:
        self._device.set_control_ready(False)
        self._measurement.set_confirmed_bias(None)
        self.init_tab.set_connection_state(False)
        self.statusBar().showMessage("未连接单片机")

    def _on_received(self, text: str) -> None:
        self.log(f"接收 ← {text}")
        upper = text.strip().upper()
        if upper.startswith("SAFETY_BOOT_START"):
            self._device.set_control_ready(False)
            self._measurement.set_confirmed_bias(None)
            self.init_tab.set_boot_state(False, "STM32 正在进行安全自检，请等待约 6 秒")
            self.statusBar().showMessage("STM32 安全自检中，控制已锁定")
            return
        if upper.startswith("SAFETY_BOOT_DONE"):
            self._device.set_control_ready(True)
            self._device.confirm_route("CISS_MEAS")
            self.relay_tab.update_route("CISS_MEAS")
            self.init_tab.set_boot_state(True, "STM32 安全自检完成，可以操作")
            self.statusBar().showMessage("STM32 就绪")
            return
        if upper == "MCU_RESETTING":
            self._scan.abort_for_reset()
            self._one_key.abort_for_reset()
            self._device.set_control_ready(False)
            self._measurement.set_confirmed_bias(None)
            self.init_tab.set_boot_state(False, "STM32 正在复位，等待安全自检完成")
            self.statusBar().showMessage("STM32 正在复位")
            return
        if upper.startswith("DDS_ON"):
            self._device.confirm_dds(True)
            self.statusBar().showMessage(f"DDS 状态：{text}")
            return
        if upper.startswith("DDS_OFF"):
            self._device.confirm_dds(False)
            self.statusBar().showMessage(f"DDS 状态：{text}")
            return
        if text.lower().startswith("ok,"):
            command = text.split(",", 1)[1].strip().lower()
            route = commands.route_from_reply(command)
            if route:
                self._device.confirm_route(route)
                self.relay_tab.update_route(route)
            bias_match = re.search(r"\bbias=([+-]?(?:\d+(?:\.\d*)?|\.\d+))v", command, re.IGNORECASE)
            if bias_match:
                bias_v = float(bias_match.group(1))
                self._device.confirm_bias(bias_v)
                self._measurement.set_confirmed_bias(bias_v)
            self.measurement_tab.handle_relay_reply(command)
            self.measurement_tab.handle_bias_reply(command)
            return
        if self._scan.handle_serial_line(text):
            if self._device.current_route:
                self.relay_tab.update_route(self._device.current_route)
            return
        if self._one_key.handle_serial_line(text):
            if self._device.current_route:
                self.relay_tab.update_route(self._device.current_route)
            return
        if self._measurement.handle_serial_line(text):
            return
        # 后续在这里补充状态、回路、故障等单片机回传信息的解析。

    def _safe_stop(self) -> None:
        try:
            # 扫压期间 STM32 会拒绝普通控制命令；此时只能使用协议允许的 sweep_stop。
            if self._scan.is_running:
                self._scan.stop()
                self.log("安全停止：扫压进行中，已发送 sweep_stop，等待 STM32 安全收尾")
                return
            self._device.safe_stop()
        except Exception as exc:
            self.log(f"安全停止失败：{exc}")

    def log(self, message: str) -> None:
        self.log_view.appendPlainText(message)
        scrollbar = self.log_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def closeEvent(self, event) -> None:
        if self._serial.is_connected:
            try:
                self._device.safe_stop()
            except Exception:
                pass
            self._serial.disconnect()
        event.accept()
