"""单次采集服务，以及单片机测量结果的集中解析。"""

from __future__ import annotations

from datetime import datetime
import re

from PySide6.QtCore import QObject, Signal

from communication.serial_manager import SerialManager
from models.measurement import MeasurementRecord


class MeasurementService(QObject):
    measurement_received = Signal(object)
    protocol_message = Signal(str)

    def __init__(self, serial_manager: SerialManager) -> None:
        super().__init__()
        self._serial = serial_manager
        self._sequence = 0
        self._confirmed_bias_v: float | None = None

    def set_confirmed_bias(self, voltage_v: float | None) -> None:
        self._confirmed_bias_v = voltage_v

    def new_task_id(self, prefix: str) -> str:
        self._sequence += 1
        stamp = datetime.now().strftime("%H%M%S")
        return f"{prefix}-{stamp}-{self._sequence:03d}"

    def start(self, cap_type: str, task_id: str | None = None) -> str:
        """在切换回路后等待 STM32 主动上报下一条有效 MEAS 数据。"""
        task_id = task_id or self.new_task_id("single")
        self._pending_task_id = task_id
        self._pending_cap_type = cap_type
        return task_id

    def handle_serial_line(self, text: str) -> bool:
        """解析 STM32 UART4 的周期上报：MEAS,...,C=...pF,CAP_VALID=...。"""
        if text.upper().startswith("MEAS,"):
            return self._handle_periodic_measurement(text)
        parts = [part.strip() for part in text.split(",")]
        if len(parts) < 5 or parts[0].upper() != "MEAS_RESULT":
            return False
        try:
            quality = float(parts[5]) if len(parts) > 5 and parts[5] else None
            record = MeasurementRecord(
                task_id=parts[1], cap_type=parts[2], capacitance_f=float(parts[3]),
                bias_actual_v=float(parts[4]), quality=quality,
            )
        except ValueError:
            self.protocol_message.emit(f"无法解析测量结果：{text}")
            return True
        self.measurement_received.emit(record)
        return True

    def parse_point_measurement(self, text: str, task_prefix: str = "point") -> MeasurementRecord | None:
        """解析 point_ciss/coss/crss/point_all 返回的 POINT_MEAS 完整结果。"""
        if not text.upper().startswith("POINT_MEAS,"):
            return None
        fields = self._parse_fields(text)
        path = {"CISS": "Ciss", "COSS": "Coss", "CRSS": "Crss"}.get(fields.get("PATH", "").upper())
        if path is None:
            self.protocol_message.emit(f"无法解析 POINT_MEAS 路径：{text}")
            return None
        try:
            capacitance_f = self._parse_capacitance_f(fields["C"])
        except (KeyError, ValueError):
            self.protocol_message.emit(f"无法解析 POINT_MEAS 数据：{text}")
            return None
        return MeasurementRecord(
            task_id=self.new_task_id(task_prefix),
            cap_type=path,
            capacitance_f=capacitance_f,
            bias_set_v=self._parse_voltage(fields.get("VSET")),
            bias_actual_v=self._parse_voltage(fields.get("VBIAS")),
            valid=fields.get("CAP_VALID", "0") == "1",
            gear=self._parse_int(fields.get("GEAR")),
            range_status=fields.get("RANGE"),
        )

    def _handle_periodic_measurement(self, text: str) -> bool:
        fields = self._parse_fields(text)
        try:
            cap_match = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)\s*pF", fields["C"], re.IGNORECASE)
            if cap_match is None:
                raise ValueError("C 字段不是 pF 数值")
            capacitance_f = float(cap_match.group(1)) * 1e-12
            valid = fields.get("CAP_VALID", "0") == "1"
        except (KeyError, ValueError):
            self.protocol_message.emit(f"无法解析 STM32 测量数据：{text}")
            return True
        task_id = getattr(self, "_pending_task_id", None) or self.new_task_id("periodic")
        reported_path = fields.get("PATH", "").upper()
        reported_cap_type = {"CISS": "Ciss", "COSS": "Coss", "CRSS": "Crss"}.get(reported_path)
        cap_type = getattr(self, "_pending_cap_type", None) or reported_cap_type or "未指定"
        record = MeasurementRecord(
            task_id=task_id, cap_type=cap_type, capacitance_f=capacitance_f,
            bias_set_v=self._parse_voltage(fields.get("VSET")) or self._confirmed_bias_v,
            bias_actual_v=self._parse_voltage(fields.get("VBIAS")),
            valid=valid,
            gear=self._parse_int(fields.get("GEAR")),
            range_status=fields.get("RANGE"),
        )
        self.measurement_received.emit(record)
        if valid and getattr(self, "_pending_task_id", None) == task_id:
            self._pending_task_id = None
            self._pending_cap_type = None
        return True

    @staticmethod
    def _parse_int(value: str | None) -> int | None:
        try:
            return int(value) if value is not None else None
        except ValueError:
            return None

    @staticmethod
    def _parse_voltage(value: str | None) -> float | None:
        if not value:
            return None
        match = re.search(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", value)
        return float(match.group(0)) if match else None

    @staticmethod
    def _parse_fields(text: str) -> dict[str, str]:
        fields: dict[str, str] = {}
        for item in text.split(",")[1:]:
            if "=" not in item:
                continue
            key, value = item.split("=", 1)
            fields[key.strip().upper()] = value.strip()
        return fields

    @staticmethod
    def _parse_capacitance_f(value: str) -> float:
        match = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)\s*(pF|nF|uF|F)", value, re.IGNORECASE)
        if match is None:
            raise ValueError("C 字段不是有效电容")
        factor = {"pf": 1e-12, "nf": 1e-9, "uf": 1e-6, "f": 1.0}[match.group(2).lower()]
        return float(match.group(1)) * factor
