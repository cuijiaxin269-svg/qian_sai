from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
    QPushButton, QVBoxLayout, QWidget,
)

from app.constants import BAUDRATES, DEFAULT_BAUDRATE
from communication.serial_manager import SerialManager
from services.device_service import DeviceService
from ui.widgets import group


class InitializationTab(QWidget):
    def __init__(self, serial_manager: SerialManager, device: DeviceService) -> None:
        super().__init__()
        self._serial = serial_manager
        self._device = device
        self._build_ui()
        self.refresh_ports()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        title = QLabel("系统控制台")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        serial_box, serial_layout = group("01  单片机串口连接")
        serial_box.setObjectName("controlCard")
        form = QFormLayout()
        self.port_combo = QComboBox()
        self.baud_combo = QComboBox()
        for baudrate in BAUDRATES:
            self.baud_combo.addItem(str(baudrate), baudrate)
        self.baud_combo.setCurrentText(str(DEFAULT_BAUDRATE))
        form.addRow("识别到的串口：", self.port_combo)
        form.addRow("波特率：", self.baud_combo)
        serial_layout.addLayout(form)
        buttons = QHBoxLayout()
        refresh = QPushButton("刷新串口")
        refresh.clicked.connect(self.refresh_ports)
        self.connect_button = QPushButton("连接单片机")
        self.connect_button.clicked.connect(self.toggle_connection)
        buttons.addWidget(refresh)
        buttons.addWidget(self.connect_button)
        serial_layout.addLayout(buttons)
        self.connection_label = QLabel("状态：未连接")
        self.connection_label.setObjectName("connectionStatus")
        serial_layout.addWidget(self.connection_label)
        layout.addWidget(serial_box)

        dds_box, dds_layout = group("02  DDS 输出控制")
        dds_box.setObjectName("controlCard")
        fixed_frequency = QLabel("固定输出频率：1 MHz")
        fixed_frequency.setObjectName("fixedValue")
        fixed_frequency.setAlignment(Qt.AlignCenter)
        dds_layout.addWidget(fixed_frequency)
        dds_buttons = QHBoxLayout()
        on_button = QPushButton("▶  开始输出")
        on_button.setObjectName("primaryAction")
        on_button.clicked.connect(lambda: self.run_device_action(lambda: self._device.set_dds_output(True)))
        off_button = QPushButton("■  停止输出")
        off_button.setObjectName("secondaryAction")
        off_button.clicked.connect(lambda: self.run_device_action(lambda: self._device.set_dds_output(False)))
        dds_buttons.addWidget(on_button)
        dds_buttons.addWidget(off_button)
        dds_layout.addLayout(dds_buttons)
        layout.addWidget(dds_box)

        bias_box, bias_layout = group("03  偏压设置")
        bias_box.setObjectName("controlCard")
        bias_layout.addWidget(QLabel("设置范围：0~100 V"))
        bias_buttons = QHBoxLayout()
        self.bias_voltage = QDoubleSpinBox()
        self.bias_voltage.setRange(0.0, 100.0)
        self.bias_voltage.setDecimals(2)
        self.bias_voltage.setSuffix(" V")
        self.bias_voltage.setMinimumWidth(220)
        set_bias = QPushButton("设置偏压")
        set_bias.setObjectName("primaryAction")
        set_bias.clicked.connect(lambda: self.run_device_action(lambda: self._device.set_bias(self.bias_voltage.value())))
        bias_buttons.addWidget(self.bias_voltage)
        bias_buttons.addWidget(set_bias)
        bias_buttons.addStretch()
        bias_layout.addLayout(bias_buttons)
        layout.addWidget(bias_box)

        reset_box, reset_layout = group("04  MCU 复位")
        reset_box.setObjectName("controlCard")
        reset_button = QPushButton("复位 STM32")
        reset_button.setObjectName("secondaryAction")
        reset_button.clicked.connect(lambda: self.run_device_action(self._device.reset_mcu))
        reset_layout.addWidget(reset_button)
        layout.addWidget(reset_box)

        layout.addStretch(1)
        self.setStyleSheet("""
            QWidget { background: #f4f7fb; color: #162033; font-size: 14px; }
            QLabel#pageTitle { font-size: 28px; font-weight: 700; color: #12213d; }
            QGroupBox#controlCard {
                background: white; border: 1px solid #dfe7f2; border-radius: 12px;
                margin-top: 12px; padding: 16px;
                font-size: 16px; font-weight: 700; color: #1e3a5f;
            }
            QGroupBox#controlCard::title { subcontrol-origin: margin; left: 14px; padding: 0 6px; }
            QLabel#connectionStatus { color: #2563a8; font-weight: 600; padding-top: 4px; }
            QLabel#fixedValue { background: #eef6ff; color: #1258a7; border-radius: 8px; padding: 13px; font-size: 20px; font-weight: 700; }
            QPushButton { border: 1px solid #bdcadb; background: #ffffff; border-radius: 7px; padding: 9px 16px; font-weight: 600; }
            QPushButton:hover { background: #f0f6ff; }
            QPushButton#primaryAction { background: #1677d2; border-color: #1677d2; color: white; }
            QPushButton#primaryAction:hover { background: #0d65b7; }
            QPushButton#secondaryAction { background: #fff5f5; border-color: #f1b5b5; color: #b42318; }
            QComboBox, QDoubleSpinBox { background: white; border: 1px solid #bdcadb; border-radius: 6px; padding: 7px; min-height: 20px; }
        """)

    def refresh_ports(self) -> None:
        self.port_combo.clear()
        for device, description in self._serial.available_ports():
            self.port_combo.addItem(f"{device} — {description}", device)
        if self.port_combo.count() == 0:
            self.port_combo.addItem("未识别到串口", None)

    def toggle_connection(self) -> None:
        if self._serial.is_connected:
            self._serial.disconnect()
            return
        port = self.port_combo.currentData()
        if not port:
            self.connection_label.setText("状态：没有可连接的串口")
            return
        try:
            self._serial.connect(port, int(self.baud_combo.currentData()))
        except Exception as exc:
            self.connection_label.setText(f"状态：连接失败：{exc}")

    def run_device_action(self, action) -> None:
        try:
            action()
        except Exception as exc:
            self.connection_label.setText(f"状态：操作失败：{exc}")

    def set_connection_state(self, connected: bool, detail: str = "") -> None:
        self.connect_button.setText("断开单片机" if connected else "连接单片机")
        text = "状态：已连接" if connected else "状态：未连接"
        self.connection_label.setText(f"{text}{detail}")

    def set_boot_state(self, ready: bool, message: str) -> None:
        color = "#16803c" if ready else "#a16207"
        self.connection_label.setStyleSheet(f"color: {color}; font-weight: 600; padding-top: 4px;")
        self.connection_label.setText(f"状态：{message}")
