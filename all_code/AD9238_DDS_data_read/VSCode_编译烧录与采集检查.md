# AD9238：在 VS Code 中编译、烧录和检查采�?
## 一键烧�?
1. �?VS Code 打开 `D:\qian_sai\all_code\AD9238_DDS_data_read`，不要只打开上一级目录�?2. 给开发板�?AD9238 模块上电，连�?J-Link；当前任务绑定的 J-Link 序列号是 `30500384`�?3. �?`Ctrl+Shift+P`，输入并选择 `Tasks: Run Task`�?4. 选择 `J-Link: Build and Flash`�?5. 终端依次完成 CMake 配置、Arm GCC 编译、J-Link 下载和校验。看�?`Verify successful.` 即烧录成功�?
只编译可�?`Ctrl+Shift+B`。只核对 Flash 内容可运�?`J-Link: Verify Only`�?
## 一键采集并画图

1. 保持信号源、AD9238、STM32 �?J-Link 连接�?2. �?`Ctrl+Shift+P`，运�?`Tasks: Run Task`�?3. 选择 `AD9238: Capture and Plot`�?4. 任务�?STM32 RAM 保存已经拆分的双通道数据，并运行正弦拟合�?5. 结果图位�?`build\vscode-debug\ad9238_result.png`�?
只查看固件内部统计可运行 `J-Link: Read AD9238 Result`�?
## 当前测试参数

- 通道 A�? MHz
- 通道 B�?00 kHz
- 每通道采样率：10 MHz
- 固件会根据上述两个频率自动纠正每帧可能翻转的 A/B 奇偶顺序�?- 两路频率不同，因此�?0°相位差”只能表示同一参考时刻的起始相位差，不能在整个采样窗口内保持恒定�?
## 当前必须先修的硬件问�?
固件诊断结果为：

```text
data_bit_activity_mask   = 0x0BFF
data_bit_stuck_low_mask  = 0x0400
data_bit_stuck_high_mask = 0x0000
```

`0x0400` 对应数据�?D10。当前工程使用：

```text
AD9238 D10 -> STM32 PD6 / AF6 / PSSI_D10
```

PCB 已确认模�?D10 �?PD6 导通。下一步应检�?AD9238 工作�?D10 焊盘是否存在跳变，以�?PD6 焊球/焊盘�?MCU 内部输入是否正常。只�?`stuck_low_mask` 清零且波形不再出�?1024 码跳变，幅值、偏置和相位结果才可信�?