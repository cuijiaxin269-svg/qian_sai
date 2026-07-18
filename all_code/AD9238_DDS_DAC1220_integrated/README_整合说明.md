# AD9238 + AD9833 + DAC1220 整合工程

本目录是独立整合工程，底座来自 `AD9238_DDS_data_read`，并合入 `DA1220_out` 的 DAC1220 GPIO 软件 SPI 驱动。两个源工程保持不变。

## DAC1220 引脚

| 信号 | STM32H7R7 引脚 |
| --- | --- |
| SCLK | PF1 |
| SDIO | PB5 |
| CS | PC10 |

PF1、PB5、PC10 只供 DAC1220 软件 SPI 使用。AD9238 的 PSSI_D10 固定使用 PD6；本整合工程不保留 PB5 的 PSSI 诊断复用模式。

## 启动行为

1. 初始化 GPIO、PSSI、DMA 和时钟。
2. 初始化并自校准 DAC1220。
3. DAC1220 持续输出 4 V，直到 MCU 复位或重新烧录。
4. 初始化 AD9238 与 AD9833，并启动一次采集。

## 编译和烧录

用 VS Code 打开本目录，运行 `STM32: Build` 编译，运行 `J-Link: Build and Flash` 烧录。

CubeMX 配置文件为 `AD9238_DDS_DAC1220_integrated.ioc`。
