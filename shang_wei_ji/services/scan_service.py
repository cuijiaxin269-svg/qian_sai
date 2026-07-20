"""STM32 UART4 C-V 扫压：逐帧校验 SWEEP_POINT，并实时更新界面。"""

from __future__ import annotations

import re
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal

from communication import commands
from communication.serial_manager import SerialManager
from models.measurement import MeasurementRecord
from services.device_service import DeviceService


@dataclass(frozen=True)
class ScanConfig:
    cap_types: tuple[str, ...]
    stop_v: float

    @property
    def is_all_paths(self) -> bool:
        return self.cap_types == ("Ciss", "Coss", "Crss")


class ScanService(QObject):
    point_received = Signal(object)
    progress_changed = Signal(int, str)
    finished = Signal(object)
    failed = Signal(str)
    running_changed = Signal(bool)

    _PATH_NAMES = {"CISS": "Ciss", "COSS": "Coss", "CRSS": "Crss"}

    def __init__(self, serial_manager: SerialManager, device: DeviceService) -> None:
        super().__init__()
        self._serial = serial_manager
        self._device = device
        self._running = False
        self._stop_requested = False
        self._config: ScanConfig | None = None
        self._records: list[MeasurementRecord] = []
        self._seen_points: set[tuple[str, int]] = set()
        self._nacked_points: set[tuple[str, int]] = set()
        self._completed_paths: set[str] = set()
        self._active_path: str | None = None
        self._partial_frame = ""

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self, config: ScanConfig) -> None:
        if self._running:
            raise RuntimeError("当前已有扫描任务正在运行")
        if not config.cap_types:
            raise ValueError("请至少选择一条待扫描曲线")
        if not 0.1 < config.stop_v <= 99.2:
            raise ValueError("终止偏压必须大于 0.1 V，且不超过 99.20 V（固件扫描缓存最多 200 点）")
        self._device.assert_ready()
        self._config = config
        self._records = []
        self._seen_points = set()
        self._nacked_points = set()
        self._completed_paths = set()
        self._active_path = None
        self._partial_frame = ""
        self._stop_requested = False
        self._running = True
        command = commands.cv_scan_all(config.stop_v) if config.is_all_paths else commands.cv_scan_start(config.cap_types[0], config.stop_v)
        self._serial.send(command)
        self.running_changed.emit(True)
        mode = "三条曲线连续扫描" if config.is_all_paths else f"{config.cap_types[0]} 单条扫描"
        self.progress_changed.emit(0, f"已发送 {mode} 请求：0.1 V → {config.stop_v:.2f} V")

    def stop(self) -> None:
        if not self._running or self._stop_requested:
            return
        self._stop_requested = True
        self._serial.send(commands.cv_scan_stop())
        self.progress_changed.emit(0, "已发送停止请求，等待 STM32 安全收尾")

    def abort_for_reset(self) -> None:
        """MCU 复位会中断扫描；保留已收数据并恢复界面按钮。"""
        if not self._running:
            return
        self._stop_requested = True
        self._finish()

    def handle_serial_line(self, text: str) -> bool:
        line = text.strip()
        if line.startswith("@SEQ="):
            # 新 @SEQ 到来表示旧帧已经不可能完整，按协议要求丢弃旧暂存帧。
            self._partial_frame = line
            self._try_finish_partial_frame()
            return True
        if self._partial_frame:
            if self._is_status_or_other_message(line):
                self._partial_frame = ""
            else:
                self._partial_frame += line
                self._try_finish_partial_frame()
                return True
        if line.startswith("SWEEP_"):
            self._handle_status(line)
            return True
        if line.upper().startswith("E,SWEEP_BUSY"):
            self.failed.emit("STM32 正在扫压，拒绝新的控制请求")
            return True
        return False

    def _try_finish_partial_frame(self) -> None:
        if len(self._partial_frame) > 2048:
            self.failed.emit("扫描帧超过合理长度仍不完整，已丢弃")
            self._partial_frame = ""
            return
        if not re.search(r",CRC=[0-9A-Fa-f]{4}$", self._partial_frame):
            return
        frame = self._partial_frame
        self._partial_frame = ""
        self._handle_point_frame(frame)

    @staticmethod
    def _is_status_or_other_message(line: str) -> bool:
        upper = line.upper()
        return upper.startswith(("SWEEP_", "MEAS,", "POINT_", "OK,", "E,", "X", "DDS_", "SAFETY_", "MCU_"))

    def _handle_point_frame(self, frame: str) -> None:
        parsed = self._parse_point_frame(frame)
        if parsed is None:
            self.failed.emit("无法解析 SWEEP_POINT 数据帧")
            return
        fields, frame_ok = parsed
        sequence = self._parse_int(fields.get("SEQ"))
        if not frame_ok:
            # STM32 扫压开始后自行连续执行；上位机只负责接收和展示，
            # 仅对已完整但校验失败的帧请求一次补发；不会对不完整暂存片段发送。
            path_key = fields.get("PATH", "").upper()
            identity = (path_key, sequence) if sequence is not None else None
            if sequence is not None and identity not in self._nacked_points:
                self._nacked_points.add(identity)
                self._serial.send(commands.nack(sequence))
                self.failed.emit(f"扫描帧校验失败，已请求补发：SEQ={sequence}")
            else:
                detail = f"SEQ={sequence}" if sequence is not None else "未找到有效序号"
                self.failed.emit(f"已忽略重复校验失败的扫描帧：{detail}")
            return
        path = self._PATH_NAMES.get(fields.get("PATH", "").upper())
        if path is None or self._config is None or path not in self._config.cap_types:
            self.failed.emit(f"收到非当前扫描任务的路径：{fields.get('PATH', '未知')}")
            return
        point_index, point_total = self._parse_index(fields.get("IDX"))
        if sequence is None:
            sequence = point_index
        identity = (path, sequence)
        if identity in self._seen_points:
            return
        self._seen_points.add(identity)
        self._active_path = path
        valid = fields.get("CAP_VALID", "0") == "1"
        record = MeasurementRecord(
            task_id=f"sweep-{path.lower()}-{sequence:03d}",
            cap_type=path,
            capacitance_f=self._parse_capacitance_f(fields.get("C", "0pF")),
            bias_set_v=self._parse_voltage(fields.get("VSET")),
            bias_actual_v=self._parse_voltage(fields.get("VBIAS")),
            valid=valid,
            scan_sequence=sequence,
            point_index=point_index,
            point_total=point_total,
            gear=self._parse_int(fields.get("GEAR")),
            range_status=fields.get("RANGE"),
        )
        self._records.append(record)
        self.point_received.emit(record)
        progress = self._progress(path, point_index, point_total)
        validity = "有效" if valid else "无效"
        self.progress_changed.emit(progress, f"{path}：第 {point_index}/{point_total} 点，{record.bias_actual_v or 0:.3f} V，数据{validity}")

    def _handle_status(self, line: str) -> None:
        name, fields = self._parse_status(line)
        path = self._PATH_NAMES.get(fields.get("PATH", "").upper())
        if name == "SWEEP_PREPARING":
            self._active_path = path
            self.progress_changed.emit(self._progress(path), f"STM32 正在准备 {path or '扫描'} 回路")
        elif name == "SWEEP_STARTED":
            self.progress_changed.emit(self._progress(path), f"STM32 已开始 {path or '扫描'}")
        elif name == "SWEEP_DONE" and path:
            self._completed_paths.add(path)
            self._device.confirm_route(f"{path.upper()}_MEAS")
            self.progress_changed.emit(self._progress(path, 1, 1), f"{path} 扫描完成，STM32 正在执行安全切换")
            if self._config and not self._config.is_all_paths:
                self._finish()
        elif name == "SWEEP_ALL_DONE":
            self._device.confirm_route("CRSS_MEAS")
            self._finish()
        elif name in {"SWEEP_ABORTED", "SWEEP_ALL_STOPPED"}:
            if self._active_path:
                self._device.confirm_route(f"{self._active_path.upper()}_MEAS")
            self._finish()
        elif name == "SWEEP_STOPPING":
            self.progress_changed.emit(self._progress(path), "STM32 正在安全停止扫描")

    def _finish(self) -> None:
        if not self._running:
            return
        self._running = False
        self.running_changed.emit(False)
        self.finished.emit(self._records)

    def _progress(self, path: str | None, point_index: int | None = None, point_total: int | None = None) -> int:
        if self._config is None:
            return 0
        paths = self._config.cap_types
        path_index = paths.index(path) if path in paths else len(self._completed_paths)
        fraction = (point_index / point_total) if point_index and point_total else 0.0
        return min(99, int((path_index + fraction) / len(paths) * 100))

    @staticmethod
    def _parse_point_frame(frame: str) -> tuple[dict[str, str], bool] | None:
        fields: dict[str, str] = {}
        for item in frame.split(","):
            if "=" not in item:
                continue
            key, value = item.split("=", 1)
            fields[key.lstrip("@").strip().upper()] = value.strip()
        if "SWEEP_POINT" not in frame or "SEQ" not in fields:
            return None
        payload_start = frame.find("SWEEP_POINT")
        crc_marker = frame.rfind(",CRC=")
        if payload_start < 0 or crc_marker < 0:
            return fields, False
        payload = frame[payload_start:crc_marker]
        payload_bytes = payload.encode("ascii", errors="ignore")
        expected_length = ScanService._parse_int(fields.get("LEN"))
        # 协议文档写的是仅计算 SWEEP_POINT 载荷；实际固件日志表明它会把
        # 行尾 CRLF 也计入 LEN 和 CRC。两种格式均兼容，避免对正确帧误发 NACK。
        length_ok = expected_length in {len(payload_bytes), len(payload_bytes + b"\r\n")}
        received_crc = fields.get("CRC", "").upper()
        crc_ok = received_crc in {
            f"{ScanService._crc16_ccitt(payload_bytes):04X}",
            f"{ScanService._crc16_ccitt(payload_bytes + b'\r\n'):04X}",
        }
        return fields, length_ok and crc_ok

    @staticmethod
    def _parse_status(line: str) -> tuple[str, dict[str, str]]:
        parts = [part.strip() for part in line.split(",")]
        fields: dict[str, str] = {}
        for item in parts[1:]:
            if "=" in item:
                key, value = item.split("=", 1)
                fields[key.strip().upper()] = value.strip()
        return parts[0].upper(), fields

    @staticmethod
    def _parse_voltage(value: str | None) -> float | None:
        if not value:
            return None
        match = re.search(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", value)
        return float(match.group(0)) if match else None

    @staticmethod
    def _parse_capacitance_f(value: str) -> float:
        match = re.search(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)\s*(pF|nF|uF|µF|F)?", value, re.IGNORECASE)
        if not match:
            return 0.0
        number = float(match.group(1))
        unit = (match.group(2) or "pF").lower()
        return number * {"pf": 1e-12, "nf": 1e-9, "uf": 1e-6, "µf": 1e-6, "f": 1.0}[unit]

    @staticmethod
    def _parse_int(value: str | None) -> int | None:
        try:
            return int(value) if value is not None else None
        except ValueError:
            return None

    @staticmethod
    def _parse_index(value: str | None) -> tuple[int | None, int | None]:
        if not value or "/" not in value:
            return None, None
        try:
            index, total = value.split("/", 1)
            return int(index), int(total)
        except ValueError:
            return None, None

    @staticmethod
    def _crc16_ccitt(data: bytes) -> int:
        crc = 0xFFFF
        for byte in data:
            crc ^= byte << 8
            for _ in range(8):
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
        return crc
