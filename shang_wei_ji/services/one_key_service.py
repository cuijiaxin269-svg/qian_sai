"""Tab4 使用 STM32 point_all 协议的一键三参数测量服务。"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from communication import commands
from communication.serial_manager import SerialManager
from models.measurement import MeasurementRecord
from services.device_service import DeviceService
from services.measurement_service import MeasurementService


class OneKeyService(QObject):
    result_received = Signal(object)
    progress_changed = Signal(int, str)
    finished = Signal(object)
    running_changed = Signal(bool)

    _CAP_TYPES = ("Ciss", "Coss", "Crss")

    def __init__(self, serial_manager: SerialManager, device: DeviceService, measurement: MeasurementService) -> None:
        super().__init__()
        self._serial = serial_manager
        self._device = device
        self._measurement = measurement
        self._running = False
        self._records: list[MeasurementRecord] = []

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self, bias_v: float) -> None:
        if self._running:
            raise RuntimeError("一键测量正在运行")
        if not 0 <= bias_v <= 100:
            raise ValueError("偏压必须在 0~100 V 范围内")
        self._device.assert_ready()
        self._device.require_dds()
        self._records = []
        self._running = True
        self.running_changed.emit(True)
        self._serial.send(commands.point_all(bias_v))
        self.progress_changed.emit(0, f"已发送 point_all={bias_v:.2f}，等待 STM32 自动完成三回路测量")

    def stop(self) -> None:
        """point_all 期间仅 mcu_reset 可中止，交由 STM32 重新安全自检。"""
        if not self._running:
            return
        self._device.reset_mcu()
        self.progress_changed.emit(0, "已发送 mcu_reset，正在中止一键测量并等待安全自检")

    def handle_serial_line(self, text: str) -> bool:
        upper = text.strip().upper()
        if upper.startswith("POINT_ALL_STARTED"):
            self.progress_changed.emit(0, "STM32 已开始 Ciss、Coss、Crss 一键测量")
            return True
        if upper.startswith("POINT_MEAS,"):
            record = self._measurement.parse_point_measurement(text, "point-all")
            if record is None:
                return True
            if record.cap_type not in self._CAP_TYPES:
                return True
            if record.valid:
                self._records.append(record)
                self._device.confirm_route(f"{record.cap_type.upper()}_MEAS")
                self.result_received.emit(record)
            completed = len({item.cap_type for item in self._records})
            self.progress_changed.emit(int(completed / 3 * 100), f"已收到 {record.cap_type} 单点结果")
            return True
        if upper.startswith("POINT_ALL_DONE"):
            self._device.confirm_route("CRSS_MEAS")
            self._finish()
            return True
        return False

    def abort_for_reset(self) -> None:
        if self._running:
            self._finish()

    def _finish(self) -> None:
        if not self._running:
            return
        self._running = False
        self.running_changed.emit(False)
        self.finished.emit(self._records)
