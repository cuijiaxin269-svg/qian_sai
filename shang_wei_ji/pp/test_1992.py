# import serial
# import time
#
#
# def test_th1992_communication(com_port, baud_rate):
#     print(f"[{com_port}] 正在尝试打开串口 (波特率: {baud_rate})...")
#
#     try:
#         # 1. 初始化并打开串口
#         ser = serial.Serial(
#             port=com_port,
#             baudrate=baud_rate,
#             bytesize=8,
#             parity='N',
#             stopbits=1,
#             timeout=2  # 设置2秒超时，如果2秒内没收到消息就不等了，防止程序卡死
#         )
#         print("✅ 串口打开成功！")
#
#         # 2. 准备测试指令
#         # *IDN? 意思是 Identification Query（查询设备身份）
#         # 注意：发送给仪器的指令末尾必须加上换行符 '\n'，否则仪器会一直等你的下一句话
#         cmd = "*IDN?\n"
#         print(f"➡️ 向仪器发送指令: {cmd.strip()}")
#
#         # 将字符串编码为 ASCII 字节流并发送
#         ser.write(cmd.encode('ascii'))
#
#         # 稍微等个 0.1 秒，给仪器一点点处理和把数据放到发送区的时间
#         time.sleep(0.1)
#
#         # 3. 读取仪器的回应
#         # readline() 会一直读取，直到遇到换行符或者超时
#         response = ser.readline().decode('ascii').strip()
#
#         # 4. 判断结果
#         if response:
#             print(f"🎉 成功收到仪器回应: 【 {response} 】")
#             print("✅ 通信测试完美通过！您的电脑可以成功控制 TH1992 了！")
#         else:
#             print("❌ 发送了指令，但仪器没有回话（一片空白）。")
#
#
#
#         ser.timeout = 6
#
#         cmd_0 = ":DISPlay:VIEW?\n"
#         print(f"➡️ 向仪器发送指令: {cmd_0.strip()}")
#
#         # 将字符串编码为 ASCII 字节流并发送
#         ser.write(cmd_0.encode('ascii'))
#
#         # 4. 读取返回值。
#         # 此时 Python 会在这里“卡住”挂起，死死盯着串口。
#         # 只要仪器没算完，Python 就不往下走；只要仪器一算完吐出 '1'，Python 瞬间捕获！
#         print("⏳ 仪器正在咔咔计算中，请不要乱动，耐心等待...")
#         reply = ser.readline().decode('ascii').strip()
#
#         print("reply:", reply)
#         # 5. 收到回复，判断结果
#         # if reply == '1':
#         #     print("✅ 收到仪器信号：校准彻底完成！")
#         #
#         # else:
#         #     print("❌ 校准超时或发生未知错误！")
#
#
#
#
#
#         # 5. 用完记得关门
#         ser.close()
#         print("串口已安全关闭。")
#
#     except serial.SerialException as e:
#         print(f"❌ 串口连接致命错误: {e}")
#         print("👉 排查建议：串口号填错了？或者该串口正被其他软件（如串口调试助手）占用着？")
#     except Exception as e:
#         print(f"❌ 发生未知错误: {e}")
#
#
# if __name__ == '__main__':
#     # ==========================================
#     # ⚠️ 运行前，请务必修改以下两个参数！
#     # ==========================================
#
#     # 1. 你的串口号（去电脑的“设备管理器”里看，比如 'COM3', 'COM9'）
#     MY_COM_PORT = 'COM13'
#
#     # 2. 你的波特率（去 TH1992 的 System/Bus 菜单里看，通常是 9600 或 115200）
#     MY_BAUD_RATE = 115200
#
#     # 开始测试！
#     test_th1992_communication(MY_COM_PORT, MY_BAUD_RATE)


import serial
import time


class TH1992_Controller:
    def __init__(self, port='COM13', baudrate=115200):
        """
        初始化串口并建立与 TH1992 的连接
        注意：请确保波特率与仪器系统设置页面 (SYSTEM -> BUS -> RS232) 中的 BAUD 保持一致。
        """
        # baudrate = baud_rate,
        #             bytesize=8,
        #             parity='N',
        #             stopbits=1,
        #             timeout=2
        try:
            self.ser = serial.Serial(
                port=port,
                baudrate=baudrate,
                bytesize=8,
                parity='N',
                stopbits=1,
                timeout=2
            )
            print(f"✅ 成功连接到 TH1992 (端口: {port})")

            # 连接成功后，自动执行基础设置
            self.initialize_instrument()

        except serial.SerialException as e:
            print(f"❌ 串口连接失败，请检查端口号或仪器是否被占用。错误信息: {e}")
            self.ser = None

    def send_cmd(self, cmd, delay=0.05):
        """发送 SCPI 指令的基础函数"""
        if self.ser and self.ser.is_open:
            # 仪器通常以 \n 作为指令结束符
            full_cmd = cmd + '\n'
            self.ser.write(full_cmd.encode('ascii'))
            time.sleep(delay)  # 给予仪器处理指令的缓冲时间
        else:
            print("⚠️ 串口未打开，无法发送指令！")

    def initialize_instrument(self):
        """执行文档中的基础设置，并区分 CH1 和 CH2 的电压状态"""
        print("⏳ 正在下发基础设置...")

        # 全局设置：显示位数自动 (6.5位)
        self.send_cmd("DISPlay:DIGits 7")

        # 对 通道1 (CH1) 和 通道2 (CH2) 循环下发相同的基础设置
        for ch in [1, 2]:
            cmds = [
                f"OUTPut{ch}:STATe OFF",  # 安全起见：先关闭输出
                f"OUTPut{ch}:LOW GROund",  # 低端子：接地
                f"SENSe{ch}:REMote OFF",  # 二线设置 (关闭远端感应)
                f"OUTPut{ch}:HCAPacitance:STATe OFF",  # 高电容模式：关
                f"OUTPut{ch}:OFF:MODE NORMal",  # 输出关闭状态：常规
                f"SOURce{ch}:FUNCtion:SHAPe DC",  # 输出波形：直流
                f"SOURce{ch}:FUNCtion:MODE VOLTage",  # 基本功能/电源方式：电压源
                f"SOURce{ch}:VOLTage:RANGe:AUTO ON",  # 电压量程：自动
                f"SENSe{ch}:CURRent:RANGe:AUTO ON",  # 电流量程：自动
                f"SENSe{ch}:CURRent:PROTection:LEVel 0.1",  # 过载保护(OCP)：设置为 0.1A (100mA)，可按需修改
            ]
            for cmd in cmds:
                self.send_cmd(cmd, delay=0.02)

        print("✅ 基础公共设置下发完成！")

        # --- 通道差异化设置 ---

        # 1. 通道 2 设置为恒定 5V
        self.send_cmd("SOURce2:VOLTage:LEVel 5")
        print("✅ 通道 2 已设定为恒定电压: 5V")

        # 2. 通道 1 默认初始化为 0V (等待后续动态调节)
        self.send_cmd("SOURce1:VOLTage:LEVel 0")
        print("✅ 通道 1 已初始化为待命状态: 0V")

    def set_ch1_voltage(self, voltage):
        """
        动态调节通道 1 的电压 (0 ~ 100V)
        """
        if 0 <= voltage <= 100:
            self.send_cmd(f"SOURce1:VOLTage:LEVel {voltage}")
            print(f"⚡ 通道 1 电压已调节为: {voltage}V")
        else:
            print(f"⚠️ 安全拦截：设定的电压 {voltage}V 超出了 0-100V 的安全限制！")

    def turn_on_outputs(self, ch1=True, ch2=True):
        """开启通道输出"""
        if ch1: self.send_cmd("OUTPut1:STATe ON")
        if ch2: self.send_cmd("OUTPut2:STATe ON")
        print("🟢 已开启输出")

    def turn_off_outputs(self):
        """关闭所有通道输出"""
        self.send_cmd("OUTPut1:STATe OFF")
        self.send_cmd("OUTPut2:STATe OFF")
        print("🔴 已关闭输出")

    def close(self):
        """关闭串口"""
        if self.ser and self.ser.is_open:
            self.turn_off_outputs()  # 关闭前安全断电
            self.ser.close()
            print("🔌 串口已关闭")


# ==========================================
# 使用示例 (测试代码)
# ==========================================
if __name__ == '__main__':
    # 1. 实例化控制器 (请将 COM口 修改为您电脑上的实际端口号)
    # 波特率通常是 9600 或 115200，请查看 TH1992 屏幕的 SYSTEM 配置
    smu = TH1992_Controller(port='COM13', baudrate=115200)

    # 2. 开启输出 (此时 CH2 输出 5V，CH1 输出 0V)
    smu.turn_on_outputs()

    # 3. 动态调节 CH1 的电压 (例如：扫压测试、阶梯测试)
    try:
        # 测试：将 CH1 电压升到 12V
        time.sleep(20)
        smu.set_ch1_voltage(12.5)

        # 测试：将 CH1 电压升到 24V
        time.sleep(20)
        smu.set_ch1_voltage(24.0)

        # 测试：将 CH1 电压升到 100V
        time.sleep(20)
        smu.set_ch1_voltage(100.0)

        # 测试软件拦截：尝试输入 150V (会被代码拦截，保护仪器和被测件)
        time.sleep(20)
        smu.set_ch1_voltage(150.0)


        time.sleep(2)

    finally:
        # 4. 无论发生什么错误，结束时安全关闭输出并断开串口+-
        smu.close()