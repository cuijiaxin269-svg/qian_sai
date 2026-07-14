import streamlit as st
import serial
import time
import os
import threading
import pandas as pd
import numpy as np

DATA_SAVE_DIR = r"D:\ji_chuang\dai_ma\data_save"
MCU_POWER_CHANNEL = 2
MCU_POWER_VOLTAGE = 5.0
MCU_POWER_OCP = 0.2
MEAS_STABLE_REL_TOL = 0.01
MEAS_STABLE_ABS_TOL = 1e-15
MEAS_STABLE_MAX_READS = 60


def _safe_float(raw_str, default=0.0):
    """Parse instrument replies such as '1.23E-12,0' safely."""
    if raw_str is None:
        return default
    text = str(raw_str).strip()
    if not text or text.upper() == "INVALID":
        return default
    try:
        return float(text.split(',')[0])
    except (ValueError, IndexError):
        return default


def _timestamp_name(prefix, suffix="csv"):
    return f"{prefix}_{time.strftime('%Y%m%d_%H%M%S')}.{suffix}"


def save_measurement_csv(df, prefix):
    os.makedirs(DATA_SAVE_DIR, exist_ok=True)
    path = os.path.join(DATA_SAVE_DIR, _timestamp_name(prefix))
    df.to_csv(path, index=False, encoding="utf-8-sig", float_format="%.18f")
    return path


def capacitance_display_columns(df, value_col="Cp_Measured"):
    out = df.copy()
    if value_col in out.columns:
        vals = pd.to_numeric(out[value_col], errors="coerce")
        out["Cp_pF"] = vals * 1e12
        out["Cp_nF"] = vals * 1e9
        out["Cp_Display"] = vals.apply(lambda v: format_value(v, "F"))
    return out


def final_display_columns(df):
    out = df.copy()
    if "Parameter" in out.columns and "Value" in out.columns:
        vals = pd.to_numeric(out["Value"], errors="coerce")
        out["Value_pF"] = np.where(out["Parameter"].isin(["Ciss", "Coss", "Crss"]), vals * 1e12, np.nan)
        out["Value_ohm"] = np.where(out["Parameter"].eq("Rg"), vals, np.nan)
        out["Readable_Value"] = out.apply(
            lambda r: format_value(r["Value"], "Ω" if r["Parameter"] == "Rg" else "F"),
            axis=1
        )
    return out


def relay_reply_ok(reply, expected):
    if reply is None:
        return False
    text = str(reply).strip()
    expected = str(expected)
    digits = ''.join(ch for ch in text if ch.isdigit())
    if not digits:
        return False
    return digits == expected or digits.startswith(expected)

# 回路颜色映射（全局共享）
CURVE_COLORS = {
    'Ciss': '#E74C3C', 'Coss': '#3498DB', 'Crss': '#2ECC71', 'Rg': '#9B59B6',
    'Ciss放电': '#999', 'Coss放电': '#999', 'Crss放电': '#999', '初始化': '#666'
}

# 回路名 → 继电器指令映射，用于扫压前重新确认继电器状态
CIRCUIT_NAME_TO_ID = {
    'Ciss': '1', 'Ciss放电': '2',
    'Coss': '3', 'Coss放电': '4',
    'Crss': '5', 'Crss放电': '6',
    'Rg': '7', '初始化': '8',
}

# ==========================================
# 模块一：仪器控制类封装 (Class Definitions)
# ==========================================

class TH1992_Controller:
    """TH1992 源表控制类 (已升级支持双通道)"""

    def __init__(self, port, baudrate=115200):
        self.port = port
        self.ser = serial.Serial(
            port=port, baudrate=baudrate, bytesize=8,
            parity='N', stopbits=1, timeout=2
        )
        self.ser.reset_input_buffer()

    def send_cmd(self, cmd):
        if self.ser and self.ser.is_open:
            self.ser.write((cmd + '\n').encode('ascii'))
            time.sleep(0.01)

    def query(self, cmd):
        self.ser.reset_input_buffer()
        self.send_cmd(cmd)
        return self.ser.readline().decode('ascii').strip()

    def init_instrument(self):
        """一键初始化基础设置 (同时初始化 CH1 和 CH2)"""
        for ch in [1, 2]:
            cmds = [
                f"OUTPut{ch}:STATe OFF",  # 初始化前先关断，避免上一次状态残留
                f"SENSe{ch}:REMote OFF",  # 二线设置
                f"OUTPut{ch}:LOW GROund",  # 低端子接地
                f"OUTPut{ch}:HCAPacitance:STATe OFF",  # 高电容关
                f"OUTPut{ch}:OFF:MODE NORMal",  # 常规输出关闭
                f"SOURce{ch}:FUNCtion:SHAPe DC",  # 输出波形直流
                f"SOURce{ch}:FUNCtion:MODE VOLTage",  # 电源方式电压
                f"SOURce{ch}:VOLTage:RANGe:AUTO ON",  # 电压量程自动
                f"SENSe{ch}:CURRent:RANGe:AUTO ON",  # 电流量程自动
                f"SENSe{ch}:CURRent:PROTection:LEVel {MCU_POWER_OCP if ch == MCU_POWER_CHANNEL else 0.1}",
                f"SENSe{ch}:VOLTage:APERture 0.02",  # 孔径时间20ms
                f"SENSe{ch}:CURRent:APERture 0.02"
            ]
            for c in cmds:
                self.send_cmd(c)
        self.power_mcu_channel()

    def power_mcu_channel(self, voltage=MCU_POWER_VOLTAGE, ocp=MCU_POWER_OCP):
        """给单片机供电通道上电，保证随后可以连接 RS232 继电器矩阵。"""
        ch = MCU_POWER_CHANNEL
        self.send_cmd(f"SOURce{ch}:VOLTage:LEVel {voltage}")
        self.send_cmd(f"SENSe{ch}:CURRent:PROTection:LEVel {ocp}")
        self.send_cmd(f"OUTPut{ch}:STATe ON")

    def close(self):
        if self.ser and self.ser.is_open:
            self.send_cmd("OUTPut1:STATe OFF")  # 关断CH1输出保护
            self.send_cmd("OUTPut2:STATe OFF")  # 关断CH2输出保护
            self.ser.close()


class TH2840_Controller:
    """TH2840 阻抗分析仪控制类"""

    def __init__(self, port, baudrate=115200):
        self.port = port
        self.ser = serial.Serial(
            port=port, baudrate=baudrate, bytesize=8,
            parity='N', stopbits=1, timeout=2
        )
        self.ser.reset_input_buffer()

    def send_cmd(self, cmd):
        if self.ser and self.ser.is_open:
            self.ser.write((cmd + '\n').encode('ascii'))
            time.sleep(0.02)

    def query(self, cmd):
        self.ser.reset_input_buffer()
        self.send_cmd(cmd)
        return self.ser.readline().decode('ascii').strip()

    def query_fast(self, cmd):
        """快速查询：跳过缓冲区清空与额外延时，适于连续扫描"""
        if self.ser and self.ser.is_open:
            self.ser.write((cmd + '\n').encode('ascii'))
            return self.ser.readline().decode('ascii').strip()
        return ''

    def init_instrument(self):
        """一键初始化基础设置"""
        cmds = [
            "APERture FAST",  # 速度快速
            "FUNCtion:IMPedance:RANGe:AUTO ON",  # AC量程自动
            "FUNCtion:DCR:RANGe:AUTO ON",  # DC量程自动
            "BIAS:STATe OFF",  # 关DC偏置
            "BIAS:VOLTage 0",  # DC偏置0V
            "OUTPut:IMPedance 100"  # 内阻100欧
        ]
        for c in cmds:
            self.send_cmd(c)

    def calibrate(self, cal_type="OPEN"):
        """校准耗时较长，需要延长超时时间"""
        old_timeout = self.ser.timeout
        self.ser.timeout = 60  # 设为60秒防止读取超时
        self.query(f"CORRection:{cal_type};*OPC?")
        self.ser.timeout = old_timeout

    def spot_freq(self, n, freq):
        """设定频率点 n 的频率 (Hz)"""
        self.send_cmd(f"CORR:SPOT{n}:FREQ {freq}")

    def spot_stat(self, n, state):
        """设定频率点 n 的开关状态 (1=ON, 0=OFF)"""
        self.send_cmd(f"CORR:SPOT{n}:STAT {state}")

    def spot_open(self, n, ack=True):
        """对频率点 n 执行开路校准，ack=True 时返回 1(成功)/0(失败)"""
        old_timeout = self.ser.timeout
        self.ser.timeout = 60
        cmd = f"CORR:SPOT{n}:OPEN"
        if ack:
            cmd += " ACK"
        result = self.query(cmd)
        self.ser.timeout = old_timeout
        return result

    def spot_short(self, n, ack=True):
        """对频率点 n 执行短路校准，ack=True 时返回 1(成功)/0(失败)"""
        old_timeout = self.ser.timeout
        self.ser.timeout = 60
        cmd = f"CORR:SPOT{n}:SHOR"
        if ack:
            cmd += " ACK"
        result = self.query(cmd)
        self.ser.timeout = old_timeout
        return result

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()


class RelayMatrix:
    """继电器开关矩阵控制类 (通过单片机 COM14 切换测量回路)"""

    # 回路映射
    CIRCUITS = {
        '1': 'Ciss 测量回路',
        '2': 'Ciss 放电回路',
        '3': 'Coss 测量回路',
        '4': 'Coss 放电回路',
        '5': 'Crss 测量回路',
        '6': 'Crss 放电回路',
        '7': 'Rg 测量回路',
        '8': '初始化 (全断开)',
    }

    def __init__(self, port, baudrate=115200):
        self.port = port
        self.ser = serial.Serial(
            port=port, baudrate=baudrate, bytesize=8,
            parity='N', stopbits=1, timeout=2
        )
        self.ser.reset_input_buffer()

    def switch_to(self, circuit_id):
        """发送 ASCII 数字切换回路，返回单片机回复（应相同）"""
        if not self.ser or not self.ser.is_open:
            return None
        self.ser.reset_input_buffer()
        self.ser.write((str(circuit_id) + '\n').encode('ascii'))
        time.sleep(0.08)
        replies = []
        while True:
            reply = self.ser.readline().decode('ascii', errors='ignore').strip()
            if reply:
                replies.append(reply)
                if relay_reply_ok(reply, circuit_id):
                    break
            if not reply or self.ser.in_waiting <= 0:
                break
        reply = replies[-1] if replies else ""
        if self.ser.in_waiting:
            self.ser.reset_input_buffer()
        return reply

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()


# ==========================================
# 模块二：Streamlit 页面与全局状态初始化
# ==========================================
st.set_page_config(page_title="双仪器综合控制台", layout="wide")

# 初始化 session_state，持久化保存类实例和数据
if 'th1992' not in st.session_state: st.session_state.th1992 = None
if 'th2840' not in st.session_state: st.session_state.th2840 = None
if 'relay' not in st.session_state: st.session_state.relay = None
if 'cv_active_circuit' not in st.session_state: st.session_state.cv_active_circuit = None
if 'cv_curves' not in st.session_state: st.session_state.cv_curves = {}  # {回路名: DataFrame}
if 'cv_scan_state' not in st.session_state: st.session_state.cv_scan_state = None
if 'final_results' not in st.session_state: st.session_state.final_results = pd.DataFrame()
if 'final_flow' not in st.session_state: st.session_state.final_flow = None
if 'data_cache' not in st.session_state:
    # 更新了 DataFrame 列名，支持双通道记录
    st.session_state.data_cache = pd.DataFrame(columns=["Time", "Cp", "Rs", "V1", "I1", "V2", "I2"])

# ==========================================
# 模块三：侧边栏 - 串口连接管理
# ==========================================
with st.sidebar:
    st.title("🔌 仪器连接区")

    st.subheader("TH1992 源表配置")
    port_1992 = st.text_input("1992 串口号", value="COM13")
    baud_1992 = st.selectbox("1992 波特率", [9600, 115200], index=1, key="b1")

    if st.session_state.th1992 is None:
        if st.button("🟢 连接 TH1992"):
            try:
                st.session_state.th1992 = TH1992_Controller(port_1992, baud_1992)
                st.success("TH1992 连接成功！")
                st.rerun()
            except Exception as e:
                st.error(f"连接失败: {e}")
    else:
        st.success("🟢 TH1992 已连接")
        if st.button("🔴 断开 TH1992"):
            st.session_state.th1992.close()
            st.session_state.th1992 = None
            st.rerun()

    st.divider()

    st.subheader("TH2840 阻抗仪配置")
    port_2840 = st.text_input("2840 串口号", value="COM12")
    baud_2840 = st.selectbox("2840 波特率", [9600, 115200], index=1, key="b2")

    if st.session_state.th2840 is None:
        if st.button("🟢 连接 TH2840"):
            try:
                st.session_state.th2840 = TH2840_Controller(port_2840, baud_2840)
                st.success("TH2840 连接成功！")
                st.rerun()
            except Exception as e:
                st.error(f"连接失败: {e}")
    else:
        st.success("🟢 TH2840 已连接")
        if st.button("🔴 断开 TH2840"):
            st.session_state.th2840.close()
            st.session_state.th2840 = None
            st.rerun()

    st.divider()

    st.subheader("🔀 继电器矩阵配置")
    port_relay = st.text_input("矩阵串口号", value="COM14")
    baud_relay = st.selectbox("矩阵波特率", [9600, 115200], index=1, key="b3")

    if st.session_state.relay is None:
        if st.button("🟢 连接继电器矩阵"):
            try:
                relay = RelayMatrix(port_relay, baud_relay)
                # 用指令8（初始化）验证通信
                reply = relay.switch_to('8')
                if relay_reply_ok(reply, '8'):
                    st.session_state.relay = relay
                    st.success("继电器矩阵连接成功！（指令8握手通过）")
                    st.rerun()
                else:
                    relay.close()
                    st.error(f"连接验证失败：发送'8'，收到'{reply}'（期望'8'）")
            except Exception as e:
                st.error(f"连接失败: {e}")
    else:
        st.success("🟢 继电器矩阵已连接")
        if st.button("🔴 断开继电器矩阵"):
            st.session_state.relay.close()
            st.session_state.relay = None
            st.rerun()

    # 当前回路状态指示
    if st.session_state.relay is not None and st.session_state.cv_active_circuit is not None:
        st.divider()
        st.markdown("### 📍 当前回路")
        c = CURVE_COLORS.get(st.session_state.cv_active_circuit, '#FFF')
        st.markdown(
            f"<div style='padding:8px 12px;border-radius:6px;"
            f"background:{c}20;border-left:4px solid {c};font-weight:bold'>"
            f"{st.session_state.cv_active_circuit}</div>",
            unsafe_allow_html=True
        )




# ==========================================
# 模块四：主工作区 - 四大功能 Tabs
# ==========================================
st.title("🎛️ 集创赛 - 多仪器协同上位机")
st.subheader("测量之前务必把页面一和二实现一下")
st.subheader("如遇特殊情况直接取消连接")


tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "⚡ 仪器一键初始化", "🎛️ 动态参数设置", "📊 数据采集与处理",
    "📈 C-V 自动扫描测试", "🏁 决赛一键测量", "🔀 继电器矩阵控制"
])








# -------- Tab 1: 初始化 --------
with tab1:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("TH1992 初始化")
        if st.button("🚀 执行 TH1992 双通道一键配置"):
            if st.session_state.th1992:
                st.session_state.th1992.init_instrument()
                st.success(f"TH1992 已初始化，CH{MCU_POWER_CHANNEL} 已输出 {MCU_POWER_VOLTAGE:g}V 给单片机供电。")
            else:
                st.warning("请先在左侧连接 TH1992")

    with col2:
        st.subheader("TH2840 初始化与校准")
        if st.button("🚀 执行 TH2840 一键配置"):
            if st.session_state.th2840:
                st.session_state.th2840.init_instrument()
                st.success("TH2840 基础设置已下发！")
            else:
                st.warning("请先在左侧连接 TH2840")

        st.write("### 🎯 单频点校准 (SPOT1~10)")

        spot_n = st.selectbox("频率点编号", list(range(1, 11)), index=0, key="spot_n")
        spot_freq = st.number_input(
            "频率点频率 (Hz)", min_value=20, max_value=1000000,
            value=1000000, step=1000, key="spot_freq"
        )
        spot_enable = st.toggle("启用该频率点", value=True, key="spot_enable")

        # 先应用频率和开关状态
        col_apply, _, _ = st.columns([1, 2, 2])
        with col_apply:
            if st.button("📝 应用频率点设置", use_container_width=True):
                if st.session_state.th2840:
                    st.session_state.th2840.spot_freq(spot_n, spot_freq)
                    st.session_state.th2840.spot_stat(spot_n, 1 if spot_enable else 0)
                    st.success(f"SPOT{spot_n}: {spot_freq}Hz, {'ON' if spot_enable else 'OFF'}")
                else:
                    st.warning("请先连接 TH2840")

        st.write("**执行单点校准**（每次约数秒）")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🔓 执行单点开路校准", use_container_width=True):
                if st.session_state.th2840:
                    with st.spinner(f"正在对 SPOT{spot_n} 执行开路校准，请稍候..."):
                        result = st.session_state.th2840.spot_open(spot_n, ack=True)
                    if result == '1':
                        st.success(f"SPOT{spot_n} ({spot_freq}Hz) 开路校准成功！")
                    else:
                        st.error(f"SPOT{spot_n} 开路校准失败（返回: {result}）")
                else:
                    st.warning("请先连接 TH2840")
        with c2:
            if st.button("🔒 执行单点短路校准", use_container_width=True):
                if st.session_state.th2840:
                    with st.spinner(f"正在对 SPOT{spot_n} 执行短路校准，请稍候..."):
                        result = st.session_state.th2840.spot_short(spot_n, ack=True)
                    if result == '1':
                        st.success(f"SPOT{spot_n} ({spot_freq}Hz) 短路校准成功！")
                    else:
                        st.error(f"SPOT{spot_n} 短路校准失败（返回: {result}）")
                else:
                    st.warning("请先连接 TH2840")







# -------- Tab 2: 参数设置 --------
with tab2:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("TH1992 输出参数 (双通道)")

        # 在列内再分子列，优雅处理双通道 UI
        ch1_col, ch2_col = st.columns(2)
        with ch1_col:
            st.markdown("**通道 1 (CH1)**")
            v1 = st.number_input("设定电压 CH1 (V)", min_value=0.0, max_value=100.0, value=0.0, key="v1")
            ocp1 = st.number_input("限流 CH1 (A)", min_value=0.001, max_value=1.0, value=0.1, key="ocp1")
        with ch2_col:
            st.markdown("**通道 2 (CH2)**")
            v2 = st.number_input("设定电压 CH2 (V)", min_value=0.0, max_value=100.0, value=5.0, key="v2")
            ocp2 = st.number_input("限流 CH2 (A)", min_value=0.001, max_value=1.0, value=0.2, key="ocp2")

        if st.button("应用 TH1992 参数并开启输出"):
            if st.session_state.th1992:
                # 配置并开启 CH1
                st.session_state.th1992.send_cmd(f"SOURce1:VOLTage:LEVel {v1}")
                st.session_state.th1992.send_cmd(f"SENSe1:CURRent:PROTection:LEVel {ocp1}")
                st.session_state.th1992.send_cmd("OUTPut1:STATe ON")

                # 配置并开启 CH2
                st.session_state.th1992.send_cmd(f"SOURce2:VOLTage:LEVel {v2}")
                st.session_state.th1992.send_cmd(f"SENSe2:CURRent:PROTection:LEVel {ocp2}")
                st.session_state.th1992.send_cmd("OUTPut2:STATe ON")

                st.success("双通道参数下发成功，已开启输出！")
    with col2:
        st.subheader("TH2840 测试条件")
        test_freq = st.number_input("测试频率 (Hz)", min_value=20, max_value=1000000, value=1000000)
        ac_volt = st.slider("AC 测试电平 (V)", min_value=0.01, max_value=0.50, value=0.10, step=0.01)
        if st.button("应用 TH2840 参数"):
            if st.session_state.th2840:
                st.session_state.th2840.send_cmd(f"FREQuency {test_freq}")
                st.session_state.th2840.send_cmd(f"VOLTage {ac_volt}")
                st.success(f"已设定频率: {test_freq}Hz, AC电平: {ac_volt}V")






# --- 请将这个单位转换函数放在代码最上方 (import 语句下方) ---
def format_value(value, unit_type):
    """自动将科学计数法格式化为带前缀的人类易读单位"""
    try:
        val = float(value)
    except:
        return "0.00"

    abs_val = abs(val)
    if abs_val == 0:
        return f"0.00 {unit_type}"

    # 电容单位换算 (F)
    if unit_type == "F":
        if abs_val < 1e-9:
            return f"{val * 1e12:.5f} pF"
        elif abs_val < 1e-6:
            return f"{val * 1e9:.5f} nF"
        elif abs_val < 1e-3:
            return f"{val * 1e6:.5f} µF"
        else:
            return f"{val * 1e3:.5f} mF"

    # 电流单位换算 (A)
    elif unit_type == "A":
        if abs_val < 1e-6:
            return f"{val * 1e9:.2f} nA"
        elif abs_val < 1e-3:
            return f"{val * 1e6:.2f} µA"
        elif abs_val < 1:
            return f"{val * 1e3:.2f} mA"
        else:
            return f"{val:.3f} A"

    # 电阻单位换算 (Ω)
    elif unit_type == "Ω":
        if abs_val > 1e6:
            return f"{val / 1e6:.5f} MΩ"
        elif abs_val > 1e3:
            return f"{val / 1e3:.5f} kΩ"
        else:
            return f"{val:.5f} Ω"

    # 其他常规显示 (电压等)
    else:
        return f"{val:.2f} {unit_type}"











# -------- 这是 Tab 3 代码 --------
with tab3:
    st.subheader("先得到Cs，后得到Rs。有点延迟")
    st.subheader("数据面板")

    if st.button("📥 执行单次测量"):
        if st.session_state.th1992 and st.session_state.th2840:
            # 1. 动态分时拿 TH2840 的数据 (先取 Cp，延迟后再取 Rs)
            cp_val, rs_val = 0.0, 0.0
            try:
                # 第一步：强制仪器切换到 Cp-D 模式，测并联电容
                st.session_state.th2840.send_cmd("FUNCtion:IMPedance CPD")
                time.sleep(0.15)  # 给仪器内部继电器切换留出时间
                res_cp = st.session_state.th2840.query("FETCh?")
                cp_val = float(res_cp.split(',')[0])  # 提取主参数 Cp

                # ==============================
                # 这里就是你想要的中间延迟 (比如 0.5 秒，可自行修改)
                time.sleep(0.5)
                # ==============================

                # 第二步：强制仪器切换到 Cs-Rs 模式，测串联电阻
                st.session_state.th2840.send_cmd("FUNCtion:IMPedance CSRS")
                time.sleep(0.15)  # 同样等待模式切换稳定
                res_rs = st.session_state.th2840.query("FETCh?")
                rs_val = float(res_rs.split(',')[1])  # 提取副参数 Rs

            except Exception as e:
                st.error(f"TH2840 分时读取与解析失败: {e}")

            # 2. 拿 TH1992 的数据
            def _safe_float_local(raw_str):
                """安全转浮点：处理 'Invalid'、空串、逗号分隔等异常"""
                if not raw_str or raw_str.upper() == 'INVALID':
                    return 0.0
                try:
                    return float(raw_str.split(',')[0])
                except (ValueError, IndexError):
                    return 0.0

            try:
                i1_raw = st.session_state.th1992.query("MEASure:CURRent? (@1)")
                v1_raw = st.session_state.th1992.query("MEASure:VOLTage? (@1)")
                i2_raw = st.session_state.th1992.query("MEASure:CURRent? (@2)")
                v2_raw = st.session_state.th1992.query("MEASure:VOLTage? (@2)")

                i1_read = _safe_float_local(i1_raw)
                v1_read = _safe_float_local(v1_raw)
                i2_read = _safe_float_local(i2_raw)
                v2_read = _safe_float_local(v2_raw)
            except Exception as e:
                v1_read, i1_read, v2_read, i2_read = 0.0, 0.0, 0.0, 0.0
                st.error(f"TH1992 解析失败: {e}")

            # 3. 页面顶端大屏显示 (修改了这里，调用了换算函数)
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Cp (并联电容)", format_value(cp_val, "F"))
            m2.metric("Rs (串联电阻)", format_value(rs_val, "Ω"))
            m3.metric("CH1 (电压 / 电流)", f"{v1_read:.2f} V / {format_value(i1_read, 'A')}")
            m4.metric("CH2 (电压 / 电流)", f"{v2_read:.2f} V / {format_value(i2_read, 'A')}")

            # 4. 存入 DataFrame (底层依然存原始浮点数，单位：法拉、欧姆、伏特、安培)
            new_row = pd.DataFrame([{
                "Time": time.strftime("%H:%M:%S"),
                "Cp": cp_val,
                "Rs": rs_val,
                "V1": v1_read,
                "I1": i1_read,
                "V2": v2_read,
                "I2": i2_read
            }])
            st.session_state.data_cache = pd.concat([st.session_state.data_cache, new_row], ignore_index=True)

        else:
            st.error("请先连接全部两台仪器！")

            # ==========================================
            # 历史数据表格与绘图展示 (前端视觉优化版)
            # ==========================================
        if not st.session_state.data_cache.empty:
            # 1. 拷贝一份数据专门用来“展示”（保护底层真实数据不被破坏）
            display_df = st.session_state.data_cache.copy()

            # 2. 将电容从 法拉(F) 换算为 皮法(pF)，扩大 10的12次方倍
            display_df["Cp (pF)"] = display_df["Cp"] * 1e12

            # 3. 为了让表格更好看，顺手把其他列也改个带单位的名字
            display_df.rename(columns={
                "Rs": "Rs (Ω)",
                "V1": "V1 (V)",
                "I1": "I1 (A)",
                "V2": "V2 (V)",
                "I2": "I2 (A)"
            }, inplace=True)

            # 4. 显示优化后的表格 (排除掉原来那个极其微小的 Cp 原数据列)
            st.write("### 📜 历史测量数据")
            columns_to_show = ["Time", "Cp (pF)", "Rs (Ω)", "V1 (V)", "I1 (A)", "V2 (V)", "I2 (A)"]

            # 使用 st.dataframe 的格式化功能，让数值显示更整齐 (保留两位小数)
            st.dataframe(
                display_df[columns_to_show].style.format({
                    "Cp (pF)": "{:.2f}",
                    "Rs (Ω)": "{:.2f}",
                    "V1 (V)": "{:.2f}",
                    "I1 (A)": "{:.4f}",
                    "V2 (V)": "{:.2f}",
                    "I2 (A)": "{:.4f}"
                }),
                use_container_width=True
            )



















# -------- C-V 曲线绘制辅助函数 --------
def _cv_valid_xy(df):
    """返回按 x 排序的有效电压/电容点 (V, F)。重复 x 取 y 均值。"""
    if df is None or df.empty or "Cp_Measured" not in df.columns:
        return np.array([]), np.array([])
    x_col = "Actual_Voltage" if "Actual_Voltage" in df.columns else "Set_Voltage"
    if x_col not in df.columns:
        return np.array([]), np.array([])
    x = pd.to_numeric(df[x_col], errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(df["Cp_Measured"], errors="coerce").to_numpy(dtype=float)  # 已是 F
    mask = np.isfinite(x) & np.isfinite(y) & (x > 0) & (y > 0)
    x, y = x[mask], y[mask]
    if len(x) <= 1:
        return x, y
    order = np.argsort(x)
    x, y = x[order], y[order]
    # 重复 x 取均值，不丢数据
    uniq_x, uniq_inv = np.unique(x, return_inverse=True)
    uniq_y = np.array([y[uniq_inv == i].mean() for i in range(len(uniq_x))])
    return uniq_x, uniq_y


def _cv_log_limits(values, current=None, pad=1.45, floor=1e-12):
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr) & (arr > 0)]
    if arr.size == 0:
        return current
    data_min = max(float(arr.min()) / pad, floor)
    data_max = float(arr.max()) * pad
    if data_min >= data_max:
        data_min = max(float(arr.min()) / 3.0, floor)
        data_max = float(arr.max()) * 3.0
    if current and current[0] > 0 and current[1] > current[0]:
        if data_min >= current[0] and data_max <= current[1]:
            return current
        data_min = min(data_min, current[0])
        data_max = max(data_max, current[1])
    return (data_min, data_max)


def _render_cv_chart(saved_curves, live_circuit, live_df):
    """Plotly C-V 曲线：悬停坐标、参考线、直连原始数据、双对数轴。"""
    import plotly.graph_objects as go

    fig = go.Figure()
    has_data = False
    all_x, all_y = [], []

    def _fmt_cap(value_f):
        if value_f >= 1e-9:
            return f"{value_f * 1e9:.2f} nF"
        elif value_f >= 1e-12:
            return f"{value_f * 1e12:.2f} pF"
        else:
            return f"{value_f:.2e} F"

    # ── 已保存曲线 ──
    for cname, df in saved_curves.items():
        x, y = _cv_valid_xy(df)
        if len(x) >= 2:
            color = CURVE_COLORS.get(cname, "#64748B")
            fig.add_trace(go.Scatter(
                x=x, y=y, mode="lines", name=cname,
                line=dict(color=color, width=1.6),
                hovertemplate=(
                    f"<b>{cname}</b><br>"
                    "Vds = %{x:.3f} V<br>"
                    "Cp  = %{customdata}<extra></extra>"
                ),
                customdata=[_fmt_cap(v) for v in y],
            ))
            all_x.extend(x.tolist())
            all_y.extend(y.tolist())
            has_data = True

    # ── 实时扫描曲线 ──
    if live_circuit and live_df is not None and not live_df.empty:
        x, y = _cv_valid_xy(live_df)
        if len(x) >= 2:
            color = CURVE_COLORS.get(live_circuit, "#64748B")
            fig.add_trace(go.Scatter(
                x=x, y=y, mode="lines", name=f"{live_circuit} 扫描中",
                line=dict(color=color, width=2.0, dash="dash"),
                hovertemplate=(
                    f"<b>{live_circuit} 扫描中</b><br>"
                    "Vds = %{x:.3f} V<br>"
                    "Cp  = %{customdata}<extra></extra>"
                ),
                customdata=[_fmt_cap(v) for v in y],
            ))
            all_x.extend(x.tolist())
            all_y.extend(y.tolist())
            has_data = True

    if not has_data:
        fig.add_annotation(
            text="暂无 C-V 数据<br>请在继电器矩阵页切换回路后开始扫描",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="#94A3B8"),
        )

    # ── 坐标轴范围 ──
    scan_state = st.session_state.get("cv_scan_state")
    is_running = bool(scan_state and scan_state.get("running"))

    if is_running and scan_state.get("chart_xlim"):
        xlim = scan_state["chart_xlim"]
    else:
        xlim = _cv_log_limits(all_x, pad=1.16, floor=1e-6) or (0.8, 40.0)

    if is_running:
        ylim = _cv_log_limits(all_y, scan_state.get("chart_ylim"), pad=1.7, floor=1e-14)
        if ylim:
            scan_state["chart_ylim"] = ylim
        else:
            ylim = scan_state.get("chart_ylim") or (1e-13, 1e-8)
    else:
        ylim = _cv_log_limits(all_y, pad=1.7, floor=1e-14) or (1e-13, 1e-8)

    # ── Y 轴各 decade 水平辅助线，同时收集主刻度值 ──
    y_ticks = []
    y_start = 10 ** np.floor(np.log10(ylim[0]))
    y_end   = 10 ** np.ceil(np.log10(ylim[1]))
    v = y_start
    while v <= y_end * 1.0001:
        if v >= ylim[0] * 0.999:
            y_ticks.append(v)
            fig.add_hline(
                y=v, line_dash="dot", line_color="#CBD5E1", line_width=0.5,
                annotation_text=f"  {v:.0e} F", annotation_position="top right",
                annotation_font_size=8, annotation_font_color="#94A3B8",
            )
        v *= 10

    # ── X 轴：只留 10 的幂次主刻度标签 ──
    x_start = 10 ** np.floor(np.log10(xlim[0]))
    x_ticks = []
    t = x_start
    while t <= xlim[1] * 1.0001:
        if t >= xlim[0] * 0.999:
            x_ticks.append(t)
        t *= 10

    fig.update_xaxes(
        type="log", range=[np.log10(xlim[0]), np.log10(xlim[1])],
        title="漏源电压 Vds / V",
        gridcolor="#E5E7EB",
        minor=dict(gridcolor="#F3F4F6", griddash="dot"),
        tickmode="array",
        tickvals=x_ticks,
        ticktext=[f"{int(tv)}" if tv >= 1 else f"{tv:g}" for tv in x_ticks],
    )
    fig.update_yaxes(
        type="log", range=[np.log10(ylim[0]), np.log10(ylim[1])],
        title="电容 Cp / F",
        gridcolor="#E5E7EB",
        minor=dict(gridcolor="#F3F4F6", griddash="dot"),
        tickmode="array",
        tickvals=y_ticks,
        ticktext=[f"{tv:.0e}" for tv in y_ticks],
    )

    fig.update_layout(
        template="plotly_white",
        title=dict(text="C-V 特性曲线", font=dict(size=16, color="#0F172A")),
        hovermode="x unified",
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="left", x=0, font=dict(size=10),
        ),
        margin=dict(l=70, r=40, t=55, b=65),
        width=1100,
        height=900,
    )

    st.plotly_chart(fig, use_container_width=True)


def _cv_scan_worker(scan_state, th1992, th2840, active_circuit, volt_points, delay_t, freq_hz, ac_volt):
    rows = []
    scan_state.update({
        "running": True,
        "done": False,
        "cancelled": False,
        "error": None,
        "progress": 0.0,
        "rows": rows,
        "message": "正在准备扫描..."
    })
    try:
        # 继电器稳定延迟（_start_cv_scan 已重新确认，此处再等 0.2s 消除瞬态）
        time.sleep(0.2)

        if th2840:
            th2840.send_cmd("FUNCtion:IMPedance CPD")
            if freq_hz is not None:
                th2840.send_cmd(f"FREQuency {freq_hz}")
            if ac_volt is not None:
                th2840.send_cmd(f"VOLTage {ac_volt}")
            time.sleep(0.2)

        if th1992:
            th1992.send_cmd("OUTPut1:STATe ON")
            time.sleep(0.3)

        total_points = len(volt_points)
        for i, target_v in enumerate(volt_points):
            if scan_state["stop_event"].is_set():
                scan_state["cancelled"] = True
                scan_state["message"] = "扫描已取消，正在安全归零..."
                break

            if th1992:
                th1992.send_cmd(f"SOURce1:VOLTage:LEVel {target_v}")

            scan_state["message"] = f"[{active_circuit or '未知回路'}] {target_v:.2f} V ({i + 1}/{total_points})"
            end_time = time.time() + delay_t
            while time.time() < end_time:
                if scan_state["stop_event"].is_set():
                    scan_state["cancelled"] = True
                    break
                time.sleep(0.05)
            if scan_state["cancelled"]:
                scan_state["message"] = "扫描已取消，正在安全归零..."
                break

            actual_v = float(target_v)
            if th1992:
                actual_v = _safe_float(th1992.query("MEASure:VOLTage? (@1)"), default=float(target_v))

            if th2840:
                th2840.send_cmd("FUNCtion:IMPedance CPD")
                time.sleep(0.15)
            raw = th2840.query("FETCh?") if th2840 else ""
            actual_cp = _safe_float(raw)
            rows.append({
                "Time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "Circuit": active_circuit or "",
                "Set_Voltage": float(target_v),
                "Actual_Voltage": actual_v,
                "Cp_Measured": actual_cp,
                "Cp_pF": actual_cp * 1e12,
                "Cp_nF": actual_cp * 1e9,
                "Cp_Display": format_value(actual_cp, "F"),
                "Raw": raw
            })
            scan_state["progress"] = (i + 1) / total_points

        scan_df = pd.DataFrame(rows)
        if not scan_df.empty:
            scan_df = capacitance_display_columns(scan_df)
            prefix = f"cv_scan_{active_circuit or 'unknown'}"
            scan_state["csv_path"] = save_measurement_csv(scan_df, prefix)
        scan_state["df"] = scan_df
    except Exception as e:
        scan_state["error"] = str(e)
    finally:
        if th1992:
            try:
                th1992.send_cmd("SOURce1:VOLTage:LEVel 0")
                time.sleep(0.2)
                th1992.send_cmd("OUTPut1:STATe OFF")
            except Exception as e:
                scan_state["error"] = f"{scan_state.get('error') or ''} 安全归零异常: {e}".strip()
        scan_state["running"] = False
        scan_state["done"] = True


def _start_cv_scan(active_circuit, volt_points, delay_t, freq_hz, ac_volt):
    # ── 重新确认继电器状态，防止 Tab 6 切换后继电器未稳定 ──
    relay = st.session_state.relay
    if relay and active_circuit:
        circuit_id = CIRCUIT_NAME_TO_ID.get(active_circuit)
        if circuit_id:
            reply = relay.switch_to(circuit_id)
            if relay_reply_ok(reply, circuit_id):
                time.sleep(0.35)  # 等待继电器物理触点稳定
            else:
                # 重试一次
                time.sleep(0.2)
                reply = relay.switch_to(circuit_id)
                if not relay_reply_ok(reply, circuit_id):
                    # 继续执行，但记录警告
                    pass

    stop_event = threading.Event()
    scan_state = {
        "stop_event": stop_event,
        "running": True,
        "done": False,
        "cancelled": False,
        "progress": 0.0,
        "rows": [],
        "df": pd.DataFrame(),
        "csv_path": None,
        "message": "正在启动扫描...",
        "error": None,
        "circuit": active_circuit,
        "chart_xlim": _cv_log_limits(volt_points, pad=1.18, floor=1e-6) or (0.8, 40.0),
        "chart_ylim": None,
    }
    worker = threading.Thread(
        target=_cv_scan_worker,
        args=(scan_state, st.session_state.th1992, st.session_state.th2840,
              active_circuit, volt_points, delay_t, freq_hz, ac_volt),
        daemon=True
    )
    scan_state["thread"] = worker
    st.session_state.cv_scan_state = scan_state
    worker.start()


def _generate_volt_points(start_v, stop_v):
    """自适应采样电压点: 0–20V 区域密集 100 点, 20–100V 区域稀疏 100 点.
    实际扫描范围决定从两个池中各取多少点. 至少保证 3 个点."""
    if start_v >= stop_v:
        return np.array([start_v, stop_v])
    DENSE_MAX = 20.0   # 密集区上限
    SPARSE_MAX = 100.0  # 稀疏区上限
    DENSE_N = 100
    SPARSE_N = 100

    pts = []
    # 密集区: start_v → min(stop_v, 20)
    dense_end = min(stop_v, DENSE_MAX)
    if start_v < dense_end:
        frac = (dense_end - start_v) / DENSE_MAX
        n = max(3, int(np.round(frac * DENSE_N)))
        pts.append(np.linspace(start_v, dense_end, n, dtype=float))

    # 稀疏区: max(start_v, 20) → stop_v
    sparse_start = max(start_v, DENSE_MAX)
    if stop_v > sparse_start:
        frac = (stop_v - sparse_start) / (SPARSE_MAX - DENSE_MAX)
        n = max(2, int(np.round(frac * SPARSE_N)))
        new_pts = np.linspace(sparse_start, stop_v, n, dtype=float)
        # 去重
        if len(pts) and abs(new_pts[0] - pts[-1][-1]) < 1e-9:
            new_pts = new_pts[1:]
        pts.append(new_pts)

    result = np.concatenate(pts) if pts else np.array([start_v, stop_v])
    return np.unique(result)  # 确保单调严格递增


# -------- Tab 4: C-V 自动扫描测试 --------
with tab4:
    st.subheader("C-V 特性曲线自动扫描")
    st.subheader("使用之前先使用页面二给TH1992下发一下参数")
    st.markdown("控制 **TH1992 CH1** 提供步进直流偏压，并使用 **TH2840** 同步测量电容 (Cp)。")

    # ==== 参数输入区 ====
    if 'cv_start_v' not in st.session_state:
        st.session_state.cv_start_v = 0.0
        st.session_state.cv_stop_v = 30.0
        st.session_state.cv_delay_t = 1.0

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.session_state.cv_start_v = st.number_input(
            "起始电压 (V)", min_value=0.0, max_value=100.0,
            value=st.session_state.cv_start_v, step=1.0, key="cv_start_v_key"
        )
    with col2:
        st.session_state.cv_stop_v = st.number_input(
            "终止电压 (V)", min_value=0.0, max_value=100.0,
            value=st.session_state.cv_stop_v, step=1.0, key="cv_stop_v_key"
        )
    with col3:
        st.session_state.cv_delay_t = st.number_input(
            "稳定延时 (秒)", min_value=0.1, max_value=30.0,
            value=st.session_state.cv_delay_t, step=0.1, key="cv_delay_t_key"
        )
    with col4:
        # 预览当前参数将产生的采样点数
        preview_pts = _generate_volt_points(
            st.session_state.cv_start_v, st.session_state.cv_stop_v
        )
        st.metric("预计采样点数", len(preview_pts))

    st.caption("采样策略：0–20 V 密集 (100 点)，20–100 V 稀疏 (100 点)，按实际扫描范围比例分配。")

    st.divider()

    # 读取当前扫描状态
    scan_state = st.session_state.get("cv_scan_state")

    # ── 第一步：若扫描刚完成，立即结算并触发干净重绘 ──
    if scan_state and scan_state.get("done") and not scan_state.get("_handled"):
        scan_df = scan_state.get("df", pd.DataFrame())
        active_circuit = scan_state.get("circuit")
        if not scan_df.empty and active_circuit:
            st.session_state.cv_curves[active_circuit] = scan_df
        scan_state["_handled"] = True
        st.session_state.cv_scan_state = None
        st.rerun(scope="app")

    # ── 第二步：扫描运行中 → fragment 实时更新曲线，其余直接渲染 ──
    if scan_state and scan_state.get("running"):
        stop_ev = scan_state.get("stop_event")
        if stop_ev and stop_ev.is_set():
            st.warning("⏳ 正在取消扫描，等待安全归零...")
        else:
            if st.button("⏹️ 立即取消扫描", type="primary",
                         key="cv_cancel_btn", use_container_width=True):
                scan_state["stop_event"].set()
                st.rerun()

        @st.fragment(run_every=1.5)
        def _cv_scan_live_view():
            cs = st.session_state.get("cv_scan_state")
            if cs and cs.get("running"):
                st.progress(cs.get("progress", 0.0))
                st.info(f"⏳ {cs.get('message', '正在扫描...')}")
                live_df = pd.DataFrame(cs.get("rows", []))
                _render_cv_chart(st.session_state.cv_curves, cs.get("circuit"), live_df)
            elif cs and cs.get("done"):
                st.rerun(scope="app")

        _cv_scan_live_view()
    else:
        # ── 空闲 / 完成：直接同步渲染，0 延迟，不依赖 fragment 定时器 ──
        _render_cv_chart(st.session_state.cv_curves, None, None)

    # ═══════════════════════════════════════════════════
    #  图表下方控件 (不受 fragment 刷新影响)
    # ═══════════════════════════════════════════════════
    col_status, col_clear = st.columns([3, 1])
    with col_status:
        if st.session_state.cv_active_circuit:
            st.info(f"📍 当前测量回路: **{st.session_state.cv_active_circuit}**")
        else:
            st.info("📍 当前测量回路: **未选择**（请先在继电器矩阵页切换回路）")
    with col_clear:
        if st.button("🗑️ 清空图表", use_container_width=True):
            st.session_state.cv_curves = {}
            st.rerun()

    if st.button("🚀 开始 C-V 扫描测试", use_container_width=True):
        start_v = st.session_state.cv_start_v
        stop_v = st.session_state.cv_stop_v
        delay_t = st.session_state.cv_delay_t
        active_circuit = st.session_state.cv_active_circuit

        if not (st.session_state.th1992 and st.session_state.th2840):
            st.error("请先连接 TH1992 和 TH2840。")
            st.stop()
        if start_v >= stop_v:
            st.error("参数设置有误：终止电压需大于起始电压！")
            st.stop()

        volt_points = _generate_volt_points(start_v, stop_v)

        _start_cv_scan(
            active_circuit, volt_points, delay_t,
            None, None
        )
        st.rerun()

    if st.session_state.cv_curves:
        st.write("### 扫描数据")
        display_tables = []
        for circuit_name, curve_df in st.session_state.cv_curves.items():
            if curve_df is not None and not curve_df.empty:
                display_df = capacitance_display_columns(curve_df)
                display_df["Circuit"] = circuit_name
                display_tables.append(display_df)
        if display_tables:
            merged_display = pd.concat(display_tables, ignore_index=True)
            cols = ["Circuit", "Time", "Set_Voltage", "Actual_Voltage", "Cp_Display", "Cp_pF", "Raw"]
            cols = [c for c in cols if c in merged_display.columns]
            st.dataframe(
                merged_display[cols].style.format({
                    "Set_Voltage": "{:.2f}",
                    "Actual_Voltage": "{:.3f}",
                    "Cp_pF": "{:.4f}",
                }),
                use_container_width=True
            )


# -------- Tab 5: 决赛一键测量 --------
with tab5:
    st.subheader("🏁 分赛区决赛一键测量")
    st.markdown("一键切换 Ciss、Coss、Crss、Rg 回路，并读取四个参量。")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        final_freq = st.number_input("测量频率 (Hz)", min_value=10000, max_value=1000000,
                                     value=1000000, step=1000, key="final_freq")
    with c2:
        final_ac = st.number_input("AC 电平 (V)", min_value=0.01, max_value=0.5,
                                   value=0.10, step=0.01, key="final_ac")
    with c3:
        final_vds = st.number_input("漏源偏置 Vds (V)", min_value=0.0, max_value=100.0,
                                    value=10.0, step=0.5, key="final_vds")
    with c4:
        auto_discharge = st.toggle("完成后回初始化", value=True, key="final_discharge")

    def _relay_switch_for_measure(circuit_id, label):
        reply = st.session_state.relay.switch_to(circuit_id)
        if not relay_reply_ok(reply, circuit_id):
            raise RuntimeError(f"{label} 回路切换失败，收到 {reply}，期望 {circuit_id}")
        st.session_state.cv_active_circuit = label

    def _read_stable_fetch(value_index=0):
        last_value = None
        last_raw = ""
        stable_count = 0
        for read_count in range(1, MEAS_STABLE_MAX_READS + 1):
            raw = st.session_state.th2840.query("FETCh?")
            parts = raw.split(',')
            value = _safe_float(parts[value_index] if len(parts) > value_index else raw)
            if last_value is not None:
                threshold = max(MEAS_STABLE_ABS_TOL, abs(last_value) * MEAS_STABLE_REL_TOL)
                if abs(value - last_value) <= threshold:
                    stable_count += 1
                else:
                    stable_count = 0
                if stable_count >= 1:
                    return raw, value, read_count
            last_value = value
            last_raw = raw
            time.sleep(0.2)
        return last_raw, last_value if last_value is not None else 0.0, MEAS_STABLE_MAX_READS

    def _read_capacitance_param(name, circuit_id, discharge_id=None, status_ph=None, flow=None):
        # 继电器已在 _prepare_final_param 中切换到测量回路，不再重复切换
        if status_ph:
            status_ph.info(f"正在测量 {name}...")
        st.session_state.th2840.send_cmd("FUNCtion:IMPedance CPD")
        raw, value, read_count = _read_stable_fetch(value_index=0)
        return raw, value, read_count

    def _read_rg_param(status_ph=None):
        # 继电器已在 _prepare_final_param 中切换到测量回路
        if status_ph:
            status_ph.info("正在测量 Rg...")
        st.session_state.th2840.send_cmd("FUNCtion:IMPedance CSRS")
        return _read_stable_fetch(value_index=1)

    FINAL_SEQUENCE = [
        {"name": "Ciss", "circuit_id": "1", "discharge_id": "2", "unit": "F", "kind": "cap"},
        {"name": "Coss", "circuit_id": "3", "discharge_id": "4", "unit": "F", "kind": "cap"},
        {"name": "Crss", "circuit_id": "5", "discharge_id": "6", "unit": "F", "kind": "cap"},
        {"name": "Rg", "circuit_id": "7", "discharge_id": "8", "unit": "Ω", "kind": "rg"},
    ]

    def _prepare_final_param(flow, status_ph=None):
        item = FINAL_SEQUENCE[flow["index"]]
        if status_ph:
            status_ph.info(f"正在切换到 {item['name']} 测量回路...")
        # 关断 TH1992 确保切换回路 / 校准 / 插拔 MOSFET 时安全
        try:
            st.session_state.th1992.send_cmd("SOURce1:VOLTage:LEVel 0")
            st.session_state.th1992.send_cmd("OUTPut1:STATe OFF")
        except Exception:
            pass
        time.sleep(0.15)
        _relay_switch_for_measure(item["circuit_id"], item["name"])
        flow["phase"] = "open"

    def _discharge_after_final_param(item, status_ph=None):
        discharge_id = item.get("discharge_id")
        if not discharge_id:
            return
        if status_ph:
            status_ph.info(f"{item['name']} 测量完成，正在切换到放电/安全回路 {discharge_id}...")
        reply = st.session_state.relay.switch_to(discharge_id)
        if not relay_reply_ok(reply, discharge_id):
            raise RuntimeError(f"{item['name']} 放电回路切换失败，收到 {reply}，期望 {discharge_id}")
        time.sleep(0.8)

    def _single_spot_calibration(flow, cal_kind):
        spot_no = flow.get("spot_no", 1)
        st.session_state.th2840.spot_freq(spot_no, flow["freq"])
        st.session_state.th2840.spot_stat(spot_no, 1)
        if cal_kind == "open":
            result = st.session_state.th2840.spot_open(spot_no, ack=True)
        else:
            result = st.session_state.th2840.spot_short(spot_no, ack=True)
        return str(result).strip()

    def _measure_final_current_param(flow, status_ph=None):
        item = FINAL_SEQUENCE[flow["index"]]

        # ① 确保继电器在测量回路（_prepare_final_param 已做过，此处再确认，电源关闭状态安全）
        _relay_switch_for_measure(item["circuit_id"], item["name"])
        time.sleep(0.3)

        # ② 配置 TH2840 频率/电平
        st.session_state.th2840.send_cmd(f"FREQuency {flow['freq']}")
        st.session_state.th2840.send_cmd(f"VOLTage {flow['ac']}")

        # ③ 接通 TH1992 CH1 漏源偏压（继电器已稳定在测量回路，不会带电切换）
        st.session_state.th1992.send_cmd(f"SOURce1:VOLTage:LEVel {flow['vds']}")
        st.session_state.th1992.send_cmd("OUTPut1:STATe ON")
        time.sleep(0.4)  # 确保电压稳定

        # ④ 读数
        if item["kind"] == "rg":
            raw, value, read_count = _read_rg_param(status_ph)
        else:
            raw, value, read_count = _read_capacitance_param(
                item["name"], item["circuit_id"], item["discharge_id"], status_ph, flow
            )

        flow["rows"].append({
            "Time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "Parameter": item["name"],
            "Value": value,
            "Display": format_value(value, item["unit"]),
            "Reads_To_Stable": read_count,
            "Unit": item["unit"],
            "Frequency_Hz": flow["freq"],
            "AC_V": flow["ac"],
            "Vds_V": flow["vds"],
            "Raw": raw,
        })

        # ⑤ 先关断 TH1992，再切放电回路 —— 防止带电切换继电器！
        try:
            st.session_state.th1992.send_cmd("SOURce1:VOLTage:LEVel 0")
            st.session_state.th1992.send_cmd("OUTPut1:STATe OFF")
        except Exception:
            pass
        time.sleep(0.15)

        _discharge_after_final_param(item, status_ph)

        flow["index"] += 1
        flow["phase"] = "prepare"
        if flow["index"] >= len(FINAL_SEQUENCE):
            result_df = final_display_columns(pd.DataFrame(flow["rows"]))
            st.session_state.final_results = result_df
            st.session_state.final_csv_path = save_measurement_csv(result_df, "final_four_params")
            st.session_state.final_flow = None
            if flow.get("auto_discharge"):
                st.session_state.relay.switch_to('8')

    @st.dialog("校准确认", dismissible=False)
    def _final_calibration_dialog():
        flow = st.session_state.final_flow
        if not flow:
            return
        item = FINAL_SEQUENCE[flow["index"]]
        status_ph = st.empty()
        st.write(f"当前准备测量：**{item['name']}**")

        if flow["phase"] == "prepare":
            st.info(
                f"下一步将切换到 {item['name']} 测量回路，"
                "然后进行开路校准、短路校准和测量；测量完成后再切换到放电回路。"
            )
            if st.button("切换到测量回路", type="primary", use_container_width=True):
                try:
                    with st.spinner("正在切换到测量回路..."):
                        _prepare_final_param(flow, status_ph)
                    st.success("回路准备完成。")
                    st.rerun()
                except Exception as e:
                    st.error(f"回路准备失败: {e}")
        elif flow["phase"] == "open":
            st.warning(f"请将 {item['name']} 测量回路保持开路，确认接线无误后再继续。\n\n⚠️ TH1992 输出已关断，可安全操作。")
            if st.button("已开路，执行开路校准", type="primary", use_container_width=True):
                # 再次确认 TH1992 输出已关断
                try:
                    st.session_state.th1992.send_cmd("OUTPut1:STATe OFF")
                except Exception:
                    pass
                with st.spinner("正在执行 SPOT1 开路校准，等待仪器返回完成信号..."):
                    result = _single_spot_calibration(flow, "open")
                if result == "1":
                    flow["phase"] = "short"
                    st.success("开路校准完成。")
                    st.rerun()
                else:
                    st.error(f"开路校准失败或未完成，仪器返回: {result}")
        elif flow["phase"] == "short":
            st.warning(f"请将 {item['name']} 测量回路短路，确认接线无误后再继续。\n\n⚠️ TH1992 输出已关断，可安全操作。")
            if st.button("已短路，执行短路校准", type="primary", use_container_width=True):
                # 再次确认 TH1992 输出已关断
                try:
                    st.session_state.th1992.send_cmd("OUTPut1:STATe OFF")
                except Exception:
                    pass
                with st.spinner("正在执行 SPOT1 短路校准，等待仪器返回完成信号..."):
                    result = _single_spot_calibration(flow, "short")
                if result == "1":
                    flow["phase"] = "dut"
                    st.success("短路校准完成。")
                    st.rerun()
                else:
                    st.error(f"短路校准失败或未完成，仪器返回: {result}")
        elif flow["phase"] == "dut":
            st.warning(
                f"{item['name']} 的开路/短路校准已完成。请将 MOSFET 插入底座并确认已经接入当前测量回路，"
                "确认后才会开始读取数据。\n\n⚠️ TH1992 输出已关断，插入 MOSFET 前确保电源已关闭。"
            )
            if st.button("MOSFET 已插入底座，开始测量", type="primary", use_container_width=True):
                with st.spinner(f"正在测量 {item['name']}..."):
                    _measure_final_current_param(flow, status_ph)
                st.rerun()

    if st.button("🚀 一键测量四个参量", type="primary", use_container_width=True):
        if not (st.session_state.th1992 and st.session_state.th2840 and st.session_state.relay):
            st.error("请先连接 TH1992、TH2840 和继电器矩阵。")
        else:
            # 立即关断 TH1992 CH1，确保后续校准/插拔 MOSFET 安全
            try:
                st.session_state.th1992.send_cmd("SOURce1:VOLTage:LEVel 0")
                st.session_state.th1992.send_cmd("OUTPut1:STATe OFF")
            except Exception:
                pass
            st.session_state.final_results = pd.DataFrame()
            st.session_state.final_csv_path = None
            st.session_state.final_flow = {
                "index": 0,
                "phase": "prepare",
                "rows": [],
                "freq": final_freq,
                "ac": final_ac,
                "vds": final_vds,
                "auto_discharge": auto_discharge,
                "spot_no": 1,
            }
            st.rerun()

    if st.session_state.final_flow:
        flow = st.session_state.final_flow
        current = FINAL_SEQUENCE[flow["index"]]
        st.info(f"正在进行一键测量流程：{current['name']} / {flow['phase']}")
        if flow["rows"]:
            st.dataframe(final_display_columns(pd.DataFrame(flow["rows"])), use_container_width=True)
        if st.button("取消一键测量流程", use_container_width=True):
            st.session_state.final_flow = None
            try:
                st.session_state.th1992.send_cmd("SOURce1:VOLTage:LEVel 0")
            except Exception:
                pass
            st.rerun()
        _final_calibration_dialog()

    if 'final_csv_path' in st.session_state and st.session_state.final_csv_path:
        st.success(f"四个参量测量完成，CSV 已保存到: {st.session_state.final_csv_path}")

    if not st.session_state.final_results.empty:
        mcols = st.columns(4)
        for idx, row in st.session_state.final_results.iterrows():
            with mcols[idx % 4]:
                st.metric(row["Parameter"], row["Display"])
        st.dataframe(st.session_state.final_results, use_container_width=True)


# -------- Tab 6: 继电器矩阵控制 --------
with tab6:
    st.subheader("🔀 继电器矩阵回路切换")
    st.markdown("点击按钮切换回路，切换后去 **Tab 4** 执行 C-V 扫描即可记录该回路曲线。")

    # 回路定义: (指令, 显示名, session_state 存储名)
    CIRCUIT_DEFS = [
        ('1', 'Ciss', 'Ciss'),
        ('2', 'Ciss 放电', 'Ciss放电'),
        ('3', 'Coss', 'Coss'),
        ('4', 'Coss 放电', 'Coss放电'),
        ('5', 'Crss', 'Crss'),
        ('6', 'Crss 放电', 'Crss放电'),
        ('7', 'Rg', 'Rg'),
        ('8', '初始化', '初始化'),
    ]

    def switch_circuit(circuit_id, label, session_name):
        if not st.session_state.relay:
            st.warning("请先在左侧连接继电器矩阵")
            return
        reply = st.session_state.relay.switch_to(circuit_id)
        if relay_reply_ok(reply, circuit_id):
            st.session_state.cv_active_circuit = session_name
            st.success(f"✅ 已切换到 **{label}**（单片机回复: {reply}）")
            st.rerun()
        else:
            st.error(f"❌ 切换失败 — 回复: {reply}（期望: {circuit_id}）")

    st.divider()

    st.write("### ⚡ 测量回路")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if st.button("1️⃣ 测 Ciss", use_container_width=True):
            switch_circuit('1', 'Ciss', 'Ciss')
    with col2:
        if st.button("3️⃣ 测 Coss", use_container_width=True):
            switch_circuit('3', 'Coss', 'Coss')
    with col3:
        if st.button("5️⃣ 测 Crss", use_container_width=True):
            switch_circuit('5', 'Crss', 'Crss')
    with col4:
        if st.button("7️⃣ 测 Rg", use_container_width=True):
            switch_circuit('7', 'Rg', 'Rg')

    st.divider()

    st.write("### 🔌 放电回路 & 初始化")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if st.button("2️⃣ Ciss 放电", use_container_width=True):
            switch_circuit('2', 'Ciss 放电', 'Ciss放电')
    with col2:
        if st.button("4️⃣ Coss 放电", use_container_width=True):
            switch_circuit('4', 'Coss 放电', 'Coss放电')
    with col3:
        if st.button("6️⃣ Crss 放电", use_container_width=True):
            switch_circuit('6', 'Crss 放电', 'Crss放电')
    with col4:
        if st.button("8️⃣ 初始化", use_container_width=True):
            switch_circuit('8', '初始化', '初始化')

    st.divider()

    st.write("### 📋 回路说明")
    st.markdown("""
    | 指令 | 回路 | 用途 |
    |:---:|------|------|
    | 1 | **Ciss 测量回路** | 输入电容测量 |
    | 2 | Ciss 放电回路 | 测量后放电 |
    | 3 | **Coss 测量回路** | 输出电容测量 |
    | 4 | Coss 放电回路 | 测量后放电 |
    | 5 | **Crss 测量回路** | 反向传输电容测量 |
    | 6 | Crss 放电回路 | 测量后放电 |
    | 7 | **Rg 测量回路** | 栅极电阻测量 |
    | 8 | 初始化 (全断开) | 安全状态，所有继电器断开 |
    """)
