from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.constants import ROUTES
from services.device_service import DeviceService
from ui.widgets import group


class RelayTab(QWidget):
    def __init__(self, device: DeviceService, notify) -> None:
        super().__init__()
        self._device = device
        self._notify = notify
        self._buttons: dict[str, QPushButton] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("继电器矩阵控制")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        status_box, status_layout = group("当前回路状态")
        self.current_route = QLabel("等待单片机状态回传")
        self.current_route.setObjectName("routeStatus")
        self.current_route.setAlignment(Qt.AlignCenter)
        status_layout.addWidget(self.current_route)
        layout.addWidget(status_box)

        measurement_box, measurement_layout = group("测量回路")
        measurement_layout.addWidget(QLabel("选择需要测量的电容回路"))
        measurement_layout.addLayout(self._route_grid(ROUTES[:3], "measureAction"))
        layout.addWidget(measurement_box)

        discharge_box, discharge_layout = group("放电回路")
        discharge_layout.addWidget(QLabel("测量完成后选择对应放电回路"))
        discharge_layout.addLayout(self._route_grid(ROUTES[3:6], "dischargeAction"))
        layout.addWidget(discharge_box)

        safety_box, safety_layout = group("安全状态")
        safety_line = QHBoxLayout()
        safety_line.addWidget(QLabel("需要断开全部继电器时使用："))
        safety_line.addStretch()
        label, route = ROUTES[6]
        safe_button = self._button(label, route, "safeAction")
        safety_line.addWidget(safe_button)
        safety_layout.addLayout(safety_line)
        layout.addWidget(safety_box)
        layout.addStretch(1)
        self._apply_style()

    def _route_grid(self, routes, style_name: str) -> QGridLayout:
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(12)
        for index, (label, route) in enumerate(routes):
            grid.addWidget(self._button(label, route, style_name), index // 3, index % 3)
        return grid

    def _button(self, label: str, route: str, style_name: str) -> QPushButton:
        button = QPushButton(label)
        button.setObjectName(style_name)
        button.setMinimumHeight(54)
        button.clicked.connect(lambda _=False, value=route: self._set_route(value))
        self._buttons[route] = button
        return button

    def _set_route(self, route: str) -> None:
        try:
            self._device.set_relay(route)
            self.current_route.setText(f"已发送切换请求：{route}（等待单片机确认）")
            self._notify(f"已发送继电器切换请求：{route}")
        except Exception as exc:
            self.current_route.setText(f"切换失败：{exc}")
            self._notify(f"继电器操作失败：{exc}")

    def update_route(self, route: str) -> None:
        self.current_route.setText(f"当前确认回路：{route}")

    def _apply_style(self) -> None:
        self.setStyleSheet("""
            QWidget { background: #f4f7fb; color: #162033; font-size: 14px; }
            QLabel#pageTitle { font-size: 28px; font-weight: 700; color: #12213d; }
            QGroupBox { background: white; border: 1px solid #dfe7f2; border-radius: 12px; margin-top: 12px; padding: 14px; font-weight: 700; color: #1e3a5f; }
            QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px; }
            QLabel#routeStatus { background: #eef6ff; color: #1258a7; border: 1px solid #d5e8ff; border-radius: 9px; padding: 16px; font-size: 18px; font-weight: 700; }
            QPushButton { border-radius: 8px; padding: 10px 12px; font-size: 15px; font-weight: 700; }
            QPushButton#measureAction { background: #eaf4ff; color: #1261b0; border: 1px solid #b9dcff; }
            QPushButton#measureAction:hover { background: #cfe8ff; }
            QPushButton#dischargeAction { background: #fff8e8; color: #9a6200; border: 1px solid #f2d49a; }
            QPushButton#dischargeAction:hover { background: #ffedc2; }
            QPushButton#safeAction { background: #fff1f1; color: #b42318; border: 1px solid #f3bbbb; min-width: 230px; }
            QPushButton#safeAction:hover { background: #ffdede; }
        """)
