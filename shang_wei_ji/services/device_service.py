"""控制类业务：所有 UI 页面经由本模块向单片机发送控制操作。"""

from communication import commands
from communication.serial_manager import SerialManager


class DeviceService:
    def __init__(self, serial_manager: SerialManager) -> None:
        self._serial = serial_manager
        self._control_ready = False
        self._current_route: str | None = None
        self._confirmed_bias_v: float | None = None
        self._dds_enabled = False

    @property
    def current_route(self) -> str | None:
        return self._current_route

    @property
    def confirmed_bias_v(self) -> float | None:
        return self._confirmed_bias_v

    @property
    def dds_enabled(self) -> bool:
        return self._dds_enabled

    def set_control_ready(self, ready: bool) -> None:
        self._control_ready = ready
        if not ready:
            self._current_route = None
            self._confirmed_bias_v = None
            self._dds_enabled = False

    def assert_ready(self) -> None:
        if not self._control_ready:
            raise RuntimeError("STM32 正在上电/复位安全自检，请等待 SAFETY_BOOT_DONE 后再操作")

    def confirm_route(self, route: str) -> None:
        self._current_route = route

    def confirm_bias(self, voltage_v: float) -> None:
        self._confirmed_bias_v = voltage_v

    def confirm_dds(self, enabled: bool) -> None:
        self._dds_enabled = enabled

    def require_dds(self) -> None:
        if not self._dds_enabled:
            raise RuntimeError("DDS 未确认开启，请先在 Tab1 点击“开始输出”并等待 DDS_ON 回包")

    def set_dds_output(self, enabled: bool) -> None:
        self.assert_ready()
        self._serial.send(commands.dds_output(enabled))

    def set_bias(self, voltage_v: float) -> None:
        self.assert_ready()
        if not 0 <= voltage_v <= 100:
            raise ValueError("偏压必须在 0~100 V 范围内")
        self._serial.send(commands.bias_set(voltage_v))

    def set_relay(self, route: str) -> None:
        self.assert_ready()
        self._serial.send(commands.relay_set(route))

    def ensure_measurement_route(self, route: str) -> bool:
        """回路已经由 STM32 确认时不重复切换；返回是否实际发送了切换命令。"""
        if route not in {"CISS_MEAS", "COSS_MEAS", "CRSS_MEAS"}:
            raise ValueError(f"不是测量回路：{route}")
        if self._current_route == route:
            return False
        self.set_relay(route)
        return True

    def reset_mcu(self) -> None:
        self._serial.send(commands.mcu_reset())
        # 复位命令发出后立即锁定，直到收到新的 SAFETY_BOOT_DONE。
        self.set_control_ready(False)

    def safe_stop(self) -> None:
        """安全停止仅关闭 DDS 并将偏压设置为 0 V。"""
        self.set_dds_output(False)
        self.set_bias(0.0)
