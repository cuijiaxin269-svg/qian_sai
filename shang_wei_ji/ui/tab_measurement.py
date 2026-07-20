from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from models.measurement import MeasurementRecord, format_capacitance
from services.device_service import DeviceService
from services.measurement_service import MeasurementService
from ui.widgets import group


class MeasurementTab(QWidget):
    def __init__(self, device: DeviceService, measurement: MeasurementService, notify) -> None:
        super().__init__()
        self._device = device
        self._measurement = measurement
        self._notify = notify
        self._waiting_task: str | None = None
        self._waiting_route_reply: str | None = None
        self._waiting_bias_reply = False
        self._build_ui()
        self._measurement.measurement_received.connect(self._on_measurement)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        title = QLabel("单一路径数据采集")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        control_box, control_layout = group("测量控制")
        line = QHBoxLayout()
        self.cap_type = QComboBox()
        self.cap_type.addItems(["Ciss", "Coss", "Crss"])
        self.start_button = QPushButton("开始单次采集")
        self.start_button.setObjectName("primaryAction")
        self.start_button.clicked.connect(self._start)
        line.addWidget(QLabel("测量类型："))
        line.addWidget(self.cap_type)
        line.addStretch()
        line.addWidget(self.start_button)
        control_layout.addLayout(line)
        self.status = QLabel("状态：等待开始采集")
        self.status.setObjectName("statusText")
        control_layout.addWidget(self.status)
        layout.addWidget(control_box)

        result_box, result_layout = group("最新测量结果")
        self.result_value = QLabel("--")
        self.result_value.setObjectName("resultValue")
        self.result_value.setAlignment(Qt.AlignCenter)
        self.result_detail = QLabel("等待单片机返回测量数据")
        self.result_detail.setAlignment(Qt.AlignCenter)
        result_layout.addWidget(self.result_value)
        result_layout.addWidget(self.result_detail)
        layout.addWidget(result_box)

        history_box, history_layout = group("测量记录")
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["时间", "类型", "电容", "偏压", "质量"])
        self.table.horizontalHeader().setStretchLastSection(True)
        history_layout.addWidget(self.table)
        layout.addWidget(history_box, 1)
        self._apply_style()

    def _start(self) -> None:
        try:
            cap_type = self.cap_type.currentText()
            self._device.require_dds()
            if self._device.confirmed_bias_v is None:
                raise RuntimeError("请先在 Tab1 设置偏压，并等待 STM32 返回 OK,bias=...")
            self.start_button.setEnabled(False)
            route = f"{cap_type.upper()}_MEAS"
            if self._device.ensure_measurement_route(route):
                self._waiting_route_reply = cap_type.lower()
                self.status.setText("状态：已请求切换测量回路，等待 STM32 回路确认…")
                self._notify(f"开始单次测量：已请求切换到 {cap_type} 回路")
            else:
                self._request_bias(cap_type)
        except Exception as exc:
            self.status.setText(f"状态：采集请求失败：{exc}")

    def handle_relay_reply(self, command: str) -> bool:
        """仅在 STM32 确认回路切换完成后，开始等待该回路的 MEAS 数据。"""
        if command != self._waiting_route_reply:
            return False
        cap_type = self.cap_type.currentText()
        self._waiting_route_reply = None
        self._request_bias(cap_type)
        return True

    def handle_bias_reply(self, command: str) -> bool:
        if not self._waiting_bias_reply or not command.lower().startswith("bias="):
            return False
        self._waiting_bias_reply = False
        cap_type = self.cap_type.currentText()
        self._waiting_task = self._measurement.start(cap_type)
        self.status.setText("状态：偏压已确认，等待 STM32 上报有效测量数据…")
        return True

    def _request_bias(self, cap_type: str) -> None:
        bias_v = self._device.confirmed_bias_v
        if bias_v is None:
            raise RuntimeError("未找到已确认的偏压设置")
        self._device.set_bias(bias_v)
        self._waiting_bias_reply = True
        self.status.setText("状态：回路已确认，正在确认偏压设置…")
        self._notify(f"{cap_type} 回路已确认，已发送 bias={bias_v:.2f}")

    def _on_measurement(self, record: MeasurementRecord) -> None:
        if record.task_id != self._waiting_task:
            return
        if not record.valid:
            self.status.setText("状态：当前测量数据无效，继续等待下一条有效数据…")
            return
        self._waiting_task = None
        self.start_button.setEnabled(True)
        self.status.setText("状态：采集完成")
        self.result_value.setText(format_capacitance(record.capacitance_f))
        quality = "--" if record.quality is None else f"{record.quality:.3f}"
        if record.bias_actual_v is not None:
            bias_text = f"{record.bias_actual_v:.2f} V（实际）"
        elif record.bias_set_v is not None:
            bias_text = f"{record.bias_set_v:.2f} V（已确认设置）"
        else:
            bias_text = "未回传"
        self.result_detail.setText(f"{record.cap_type}　|　偏压 {bias_text}　|　质量 {quality}")
        row = self.table.rowCount()
        self.table.insertRow(row)
        for column, text in enumerate([record.timestamp, record.cap_type, format_capacitance(record.capacitance_f), bias_text, quality]):
            self.table.setItem(row, column, QTableWidgetItem(text))

    def _apply_style(self) -> None:
        self.setStyleSheet("""
            QWidget { background: #f4f7fb; color: #162033; font-size: 14px; }
            QLabel#pageTitle { font-size: 28px; font-weight: 700; color: #12213d; }
            QGroupBox { background: white; border: 1px solid #dfe7f2; border-radius: 12px; margin-top: 12px; padding: 14px; font-weight: 700; color: #1e3a5f; }
            QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px; }
            QLabel#statusText { color: #60708b; font-weight: 500; }
            QLabel#resultValue { font-size: 34px; font-weight: 700; color: #1677d2; padding: 12px; }
            QPushButton { border-radius: 7px; padding: 9px 16px; font-weight: 600; }
            QPushButton#primaryAction { background: #1677d2; border: 1px solid #1677d2; color: white; }
            QComboBox { background: white; border: 1px solid #bdcadb; border-radius: 6px; padding: 7px; min-width: 130px; }
            QTableWidget { border: 1px solid #e2e8f0; gridline-color: #e9eef5; }
        """)
