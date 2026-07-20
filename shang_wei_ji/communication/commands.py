"""单片机控制命令集中定义处。

当前是上位机初版的临时文本命令。单片机固件完成后，只修改本文件
中的函数即可替换为真实协议，不要把命令字符串写进 UI 页面。
"""


def dds_output(enabled: bool) -> str:
    """DDS 固定 1 MHz：使用 STM32 最新 UART4 真实指令。"""
    return "dds_on" if enabled else "dds_off"


def mcu_reset() -> str:
    return "mcu_reset"


def bias_set(voltage_v: float) -> str:
    """UART4 实际偏压设置：直接发送 0.00~100.00 数值。"""
    return f"bias={voltage_v:.2f}"


RELAY_COMMANDS = {
    "CISS_MEAS": "ciss",
    "COSS_MEAS": "coss",
    "CRSS_MEAS": "crss",
    "CISS_DISCHARGE": "cissset",
    "COSS_DISCHARGE": "cossset",
    "CRSS_DISCHARGE": "crssset",
    "SAFE_OPEN": "reset",
}


def relay_set(route: str) -> str:
    """将上位机回路名称转换为 STM32 UART4 已实现的小写指令。"""
    try:
        return RELAY_COMMANDS[route]
    except KeyError as exc:
        raise ValueError(f"未知继电器回路：{route}") from exc


def route_from_reply(command: str) -> str | None:
    """把 STM32 的 OK,ciss 等确认回包转换为界面使用的回路名称。"""
    reverse = {value: key for key, value in RELAY_COMMANDS.items()}
    return reverse.get(command.strip().lower())


def cv_scan_start(cap_type: str, stop_v: float) -> str:
    """启动单回路 C-V 扫压：sweep_ciss/coss/crss=终止偏压。"""
    command_names = {
        "Ciss": "sweep_ciss",
        "Coss": "sweep_coss",
        "Crss": "sweep_crss",
    }
    try:
        return f"{command_names[cap_type]}={stop_v:.2f}"
    except KeyError as exc:
        raise ValueError(f"未知扫描曲线：{cap_type}") from exc


def cv_scan_all(stop_v: float) -> str:
    """启动 Ciss→Coss→Crss 三回路连续扫压。"""
    return f"sweep_all={stop_v:.2f}"


def cv_scan_current(stop_v: float) -> str:
    return f"sweep={stop_v:.2f}"


def cv_scan_current_start(stop_v: float) -> str:
    return f"sweep,start={stop_v:.2f}"


def cv_scan_stop() -> str:
    return "sweep_stop"


def sweep_status() -> str:
    return "sweep_status"


def nack(sequence: int) -> str:
    return f"nack={int(sequence)}"


def ack(sequence: int) -> str:
    return f"ack={int(sequence)}"


def gear_set(gear: str) -> str:
    if gear not in {"A", "B", "C", "D"}:
        raise ValueError("挡位必须是 A、B、C 或 D")
    return gear


def gear_auto() -> str:
    return "auto"


def point_measure(cap_type: str, voltage_v: float) -> str:
    names = {"Ciss": "point_ciss", "Coss": "point_coss", "Crss": "point_crss"}
    try:
        return f"{names[cap_type]}={voltage_v:.2f}"
    except KeyError as exc:
        raise ValueError(f"未知单点测量类型：{cap_type}") from exc


def point_all(voltage_v: float) -> str:
    return f"point_all={voltage_v:.2f}"
