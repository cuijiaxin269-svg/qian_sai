# AD9238_DDS_data_read 工程说明

本工程基于已调通的 `AD9238_data_read` 重新建立，保留 AD9238 的 PSSI + DMA 双通道采集功能，并新增 DDS 三线 GPIO 控制。

## 工程路径

```text
D:\qian_sai\all_code\AD9238_DDS_data_read
```

## 主要功能

1. AD9238 双通道采集。
2. MCU 内部计算两路信号频率、幅值、相位和相位差。
3. DDS 软件三线控制，默认初始化输出 1 MHz 正弦。

## DDS 引脚

| DDS 功能 | STM32 引脚 | GPIO 标签 | 默认状态 |
|---|---|---|---|
| SYNC / FSYNC | PD5 | DDS_SYNC | 高电平 |
| CLK / SCLK | PE2 | DDS_CLK | 低电平 |
| DATA / SDATA | PE14 | DDS_DATA | 低电平 |

## DDS 代码位置

| 文件 | 说明 |
|---|---|
| `Appli/Core/Inc/dds_ad9833.h` | DDS 驱动接口 |
| `Appli/Core/Src/dds_ad9833.c` | GPIO bit-bang 写 16 位、设置频率、设置波形 |
| `Appli/Core/Src/main.c` | 调用 `DDS_AD9833_Init()` 初始化 DDS |

当前 DDS 驱动按 AD9833 兼容寄存器格式实现：

- MCLK 默认：25 MHz
- 默认频率：1 MHz
- 默认波形：正弦波
- 串行时序：SYNC 空闲高，CLK 空闲低，DATA MSB first

如果实际 DDS 芯片不是 AD9833，只需要替换 `dds_ad9833.c` 里的寄存器写入格式，PD5/PE2/PE14 引脚不需要改。

## AD9238 关键配置

AD9238 采集沿用 `AD9238_data_read` 中已验证的配置：

- PSSI 16-bit 外部时钟采集
- GPDMA1 Channel15
- AD9238 输出按 two's-complement 解析
- PD6 配置为 PSSI_D10 的 AF9，修复 D10 读取问题

## 编译与烧录

用 VS Code 打开：

```text
D:\qian_sai\all_code\AD9238_DDS_data_read
```

然后执行任务：

```text
J-Link: Build and Flash
```

生成并烧录的文件是：

```text
D:\qian_sai\all_code\AD9238_DDS_data_read\build\vscode-debug\AD9238_DDS_data_read_Appli.bin
```

## 当前已验证

- Appli 编译通过。
- Boot 编译通过。
- J-Link 脚本路径已改到新工程。
- AD9238 结果读取脚本地址已按新工程符号表更新。
