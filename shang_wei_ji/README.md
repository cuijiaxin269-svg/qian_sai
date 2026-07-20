# 嵌入式测试系统上位机（初版）

这是单片机唯一串口控制的上位机初始版本。

已完成：串口自动识别、连接、DDS 固定 1 MHz 输出控制、UART4 直接数值偏压控制、UART4 继电器矩阵控制和安全停止。

已预留：单点采集、C-V 扫描、Ciss/Coss/Crss 一键测量。待单片机测量代码和实际回传格式确定后，在 `communication/commands.py` 与对应 `services/` 中接入。

## 安装与运行

```powershell
python -m pip install -r requirements.txt
python main.py
```

## 当前默认控制文本

所有控制命令均以换行结尾，且集中定义在 `communication/commands.py`：

| 功能 | 默认发送文本 |
|---|---|
| DDS 输出控制 | 暂用 `DDS,1000000,<开关>`；等待 DDS 实际指令 |
| 偏压设置 | 直接发送 `0.00`~`100.00` 数值，例如 `12.50` |
| Ciss / Coss / Crss 测量回路 | `ciss` / `coss` / `crss` |
| Ciss / Coss / Crss 放电回路 | `cissset` / `cossset` / `crssset` |
| 继电器安全复位 | `reset` |
| 安全停止 | 依次发送 DDS 关闭和偏压 `0 V` |

单片机代码完成后，只需修改 `communication/commands.py` 中的组包函数，不需要在界面代码中查找或修改发送内容。

## 打包 EXE

```powershell
python -m pip install pyinstaller
pyinstaller --noconsole --onedir --name 嵌入式测试上位机 main.py
```
