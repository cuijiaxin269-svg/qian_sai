import serial
import time


class TH2840Controller:
    def __init__(self, port, baudrate=115200, timeout=2):
        """
        初始化串口连接
        :param port: 串口号 (如 'COM3')
        :param baudrate: 波特率 (需要与仪器面板 SYSTEM 里的设置保持一致)
        :param timeout: 超时时间(秒)
        """
        self.port = port
        try:
            self.ser = serial.Serial(
                port=port,
                baudrate=baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=timeout
            )
            print(f"成功连接到串口: {self.port}")
            # 连接后先清空一下缓冲区，防止读到之前的脏数据
            self.ser.reset_input_buffer()
        except Exception as e:
            print(f"串口打开失败，请检查端口号或占用情况！错误信息: {e}")
            self.ser = None

    def send_query(self, command):
        """发送查询指令并读取返回结果"""
        if not self.ser or not self.ser.is_open:
            return "串口未打开"

        try:
            # 清空接收区旧数据
            self.ser.reset_input_buffer()

            # 发送指令，注意必须带上换行符 \n
            self.ser.write((command + '\n').encode('ascii'))

            # 稍作延时给仪器处理时间（简单的查询0.1秒足够）
            time.sleep(0.1)

            # 读取一行返回值并解码，去除首尾空白字符
            response = self.ser.readline().decode('ascii').strip()
            return response
        except Exception as e:
            return f"通信错误: {e}"

    def get_idn(self):
        """功能1：返回仪器类型 (Identity)"""
        print("正在查询仪器类型...")
        response = self.send_query("*IDN?")
        return response

    def get_measurement(self):
        """功能2：获取当前测量值 (Fetch)"""
        print("正在获取测量数据...")
        response = self.send_query("FETCh?")
        return response

    def close(self):
        """关闭串口"""
        if self.ser and self.ser.is_open:
            self.ser.close()
            print(f"串口 {self.port} 已关闭。")


# ==========================================
# 测试代码 (主程序)
# ==========================================
if __name__ == '__main__':
    # ⚠️ 请将这里的 'COM3' 改为你电脑设备管理器中实际的串口号
    # ⚠️ 波特率通常是 115200 或 9600，请查看仪器 [SYSTEM] 菜单里的 [BUS] 设置
    COM_PORT = 'COM12'
    BAUD_RATE = 115200

    # 1. 实例化控制类
    th2840 = TH2840Controller(port=COM_PORT, baudrate=BAUD_RATE)

    if th2840.ser and th2840.ser.is_open:
        # 2. 测试功能1：获取仪器信息
        idn_info = th2840.get_idn()
        print(f"👉 仪器信息: {idn_info}")
        print("-" * 40)

        # 3. 测试功能2：获取测量数据
        # 建议连续读几次看看效果
        for i in range(3):
            meas_data = th2840.get_measurement()
            print(f"👉 第 {i + 1} 次测量值: {meas_data}")
            time.sleep(0.5)  # 每次读取间隔0.5秒

        print("-" * 40)

        # 4. 退出前关闭串口
        th2840.close()