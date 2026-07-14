# DA_out DAC1220 工程说明

本工程用于 STM32H7R7L8 通过三线 GPIO 软件时序控制 TI DAC1220。

## 工程路径

```text
D:\qian_sai\all_code\DA_out
```

## DAC1220 引脚

| DAC1220 信号 | STM32 引脚 | GPIO 标签 | 默认状态 |
|---|---|---|---|
| CS | PF1 | DAC_CS | 高电平 |
| SDIO | PB5 | DAC_SDIO | 低电平 |
| SCLK | PC10 | DAC_SCLK | 低电平 |

## 默认输出

当前程序上电后输出约 `2.5V`。

前提条件：

- DAC1220 使用 `VREF = 2.5V`
- DAC1220 配置为 `Straight Binary`
- DAC1220 配置为 `16-bit` 模式

代码里对应的是：

```c
DAC1220_WriteCommandRegister(0x2020);
DAC_Output_SetCode16(0x8000);
```

其中 `0x2020` 表示：

```text
Normal mode
16-bit resolution
Straight binary
MSB first
Reserved bit13 = 1
```

`0x8000` 是 16 位中间码。DAC1220 在 Straight Binary 模式下：

```text
VOUT = 2 * VREF * code / 65536
```

所以当 `VREF = 2.5V` 时：

```text
code = 0x8000 -> VOUT ≈ 2.5V
```

## 代码位置

| 文件 | 说明 |
|---|---|
| `Appli/Core/Inc/dac_output.h` | DAC1220 驱动接口 |
| `Appli/Core/Src/dac_output.c` | DAC1220 三线 bit-bang 写寄存器和设置输出码值 |
| `Appli/Core/Src/main.c` | 初始化 GPIO 后调用 `DAC_Output_Init()` |

## 常用函数

```c
DAC1220_WriteRegister(uint8_t start_address, const uint8_t *data, uint8_t byte_count);
DAC1220_WriteCommandRegister(uint16_t command);
DAC1220_WriteDataInputRegister16(uint16_t code);
DAC_Output_SetCode16(uint16_t code);
DAC_Output_SetRatio(float ratio);
```

## 编译与烧录

用 VS Code 打开：

```text
D:\qian_sai\all_code\DA_out
```

然后运行：

```text
J-Link: Build and Flash
```

烧录文件：

```text
D:\qian_sai\all_code\DA_out\build\vscode-debug\DA_out_Appli.bin
```
