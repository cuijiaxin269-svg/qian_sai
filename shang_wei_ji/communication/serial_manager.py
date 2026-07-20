"""唯一允许直接读写串口的模块。"""

from __future__ import annotations

from serial import Serial, SerialException
from serial.tools import list_ports
from PySide6.QtCore import QObject, QThread, Signal


class SerialReader(QThread):
    received = Signal(str)
    communication_error = Signal(str)

    def __init__(self, serial_port: Serial) -> None:
        super().__init__()
        self._serial_port = serial_port
        self._running = True

    def run(self) -> None:
        buffer = bytearray()
        while self._running:
            try:
                # readline() 在超时时会返回不完整内容。扫描帧较长，STM32 也可能
                # 分段写入；因此必须自行缓存，只有收齐 LF 后才交给协议层。
                raw = self._serial_port.read(self._serial_port.in_waiting or 1)
                if not raw:
                    continue
                buffer.extend(raw)
                while b"\n" in buffer:
                    line, _, remainder = buffer.partition(b"\n")
                    buffer = bytearray(remainder)
                    text = line.rstrip(b"\r").decode("utf-8", errors="replace").strip()
                    if text:
                        self.received.emit(text)
                # 防止异常固件持续输出却从不换行，导致内存无限增长。
                if len(buffer) > 8192:
                    buffer.clear()
                    self.communication_error.emit("串口接收缓存超过 8192 字节且未收到换行，已丢弃异常数据")
            except SerialException as exc:
                self.communication_error.emit(str(exc))
                return

    def stop(self) -> None:
        self._running = False
        self.wait(1000)


class SerialManager(QObject):
    received = Signal(str)
    sent = Signal(str)
    connected = Signal(str)
    disconnected = Signal()
    communication_error = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._serial_port: Serial | None = None
        self._reader: SerialReader | None = None

    @staticmethod
    def available_ports() -> list[tuple[str, str]]:
        return [(port.device, port.description or "未知设备") for port in list_ports.comports()]

    @property
    def is_connected(self) -> bool:
        return self._serial_port is not None and self._serial_port.is_open

    def connect(self, port: str, baudrate: int) -> None:
        self.disconnect()
        self._serial_port = Serial(port=port, baudrate=baudrate, timeout=0.2, write_timeout=1)
        self._serial_port.reset_input_buffer()
        self._reader = SerialReader(self._serial_port)
        self._reader.received.connect(self.received)
        self._reader.communication_error.connect(self.communication_error)
        self._reader.start()
        self.connected.emit(port)

    def send(self, text: str) -> None:
        if not self.is_connected or self._serial_port is None:
            raise RuntimeError("单片机串口未连接")
        try:
            # 所有命令以一个完整 ASCII 行发送，确保最后仅有一个 LF。
            command = text.rstrip("\r\n")
            self._serial_port.write((command + "\n").encode("utf-8"))
            self._serial_port.flush()
            self.sent.emit(command)
        except SerialException as exc:
            self.communication_error.emit(str(exc))
            raise RuntimeError(f"串口发送失败：{exc}") from exc

    def disconnect(self) -> None:
        if self._reader is not None:
            self._reader.stop()
            self._reader = None
        if self._serial_port is not None:
            if self._serial_port.is_open:
                self._serial_port.close()
            self._serial_port = None
        self.disconnected.emit()
