# AD9833：STM32 SPI 控制与系统控制逻辑

> 整理说明：本文档整合当前系统对 DDS、ADC、DAC、串口和上位机的控制需求，以及 STM32 通过 SPI 控制 AD9833 的接线、寄存器、频率/相位计算、代码示例和调试方法。

## 本文档包含

1. 控制逻辑
2. STM32 通过 SPI 控制 AD9833 学习笔记

---

## 第 1 部分：控制逻辑

使用芯片
STM32H7R7L8H6H


加一个串口，还有那个上位机部分


dds9833（代码完成了）
输出1M的sin波


ADC 9238 （pssi和dma）
两路采集，采样频率10M，一个电流信号，一个电压信号（电势差）
读数据，20M频率，交错读数


（算法）
电桥算法，计算出阻抗


DAC 1220，
控制信号0到10直流电

---

## 第 2 部分：STM32 通过 SPI 控制 AD9833 学习笔记

> 文件名按当前文件夹已有名称保留为 `SPI-ad8933.md`，内容实际整理的是 AD9833。



![[ad9833.pdf]]
### 1. AD9833 是什么


AD9833 是 Analog Devices 的一款低功耗可编程波形发生器，本质上是一个 DDS 芯片。

DDS 全称是 Direct Digital Synthesis，直接数字频率合成。它可以通过数字寄存器控制输出频率、相位和波形。

AD9833 可以输出：

- 正弦波
- 三角波
- 方波，来自 DAC 数据 MSB 或 MSB/2

典型用途：

- 简易信号发生器
- 频率激励源
- 传感器测试信号
- 扫频信号
- 本振信号
- FSK、PSK 等简单调制

数据手册中的重要特性：

- 供电范围：`2.3V ~ 5.5V`
- 功耗较低，3V 时约 `12.65mW`
- 输出频率范围：`0MHz ~ 12.5MHz`
- 频率寄存器：`28 bit`
- 相位寄存器：`12 bit`
- DAC 分辨率：`10 bit`
- 通过 3 线 SPI 写入控制数据
- 串行时钟 SCLK 最高可到 `40MHz`
- 支持掉电/睡眠控制

### 2. AD9833 的核心工作逻辑

AD9833 内部大致由这些部分组成：

- 28 位相位累加器
- FREQ0、FREQ1 两个频率寄存器
- PHASE0、PHASE1 两个相位寄存器
- 正弦查找表 SIN ROM
- 10 位 DAC
- 控制寄存器
- SPI 串行接口

可以把它理解成：

1. STM32 通过 SPI 把频率控制字写入 AD9833
2. AD9833 根据 MCLK 和频率控制字产生数字相位
3. 数字相位经过相位寄存器偏移
4. 如果输出正弦波，就经过 SIN ROM 转成幅度数据
5. 幅度数据送入 DAC
6. VOUT 引脚输出模拟波形

如果选择方波输出，AD9833 不一定走 DAC 正弦路径，而是把 DAC 数据的 MSB 或 MSB/2 输出到 VOUT。

### 3. AD9833 重要引脚理解

常见模块上会引出这些信号：

| 引脚        | 作用                          |
| --------- | --------------------------- |
| VCC / VDD | 芯片供电，常见模块可接 3.3V 或 5V，具体看模块 |
| GND       | 地                           |
| FSYNC     | SPI 片选/帧同步，低电平有效            |
| SCLK      | SPI 时钟                      |
| SDATA     | SPI 数据输入，对应 STM32 MOSI      |
| MCLK      | AD9833 主时钟输入，常见模块为 25MHz 晶振 |
| VOUT      | 波形输出                        |

注意：AD9833 只有写入控制，没有常规 MISO 回读线，所以 STM32 一般只需要 MOSI、SCK、CS 三根 SPI 控制线。

### 4. STM32 和 AD9833 的接线

典型硬件 SPI 接线：

| STM32      | AD9833    |
| ---------- | --------- |
| SPI_SCK    | SCLK      |
| SPI_MOSI   | SDATA     |
| 普通 GPIO 输出 | FSYNC     |
| GND        | GND       |
| 3.3V 或 5V  | VCC / VDD |

如果用 STM32 软件 SPI，也可以任意选择 3 个 GPIO：

| STM32 GPIO | AD9833 |
|---|---|
| GPIO 输出 | SCLK |
| GPIO 输出 | SDATA |
| GPIO 输出 | FSYNC |

建议：

- STM32 和 AD9833 必须共地
- STM32 是 3.3V IO 时，AD9833 供电用 3.3V 最省心
- 如果 AD9833 模块接 5V，要确认模块输入是否兼容 3.3V 逻辑
- VOUT 是模拟输出，后级最好根据需求加滤波、缓冲或放大

### 5. SPI 协议基础

SPI 全称是 Serial Peripheral Interface，串行外设接口。

SPI 常见 4 根线：

- SCK：时钟，由主机产生
- MOSI：主机输出，从机输入
- MISO：主机输入，从机输出
- CS/NSS：片选，选择具体从机

AD9833 只需要写入数据，不需要回读，所以实际只用：

- SCLK
- SDATA
- FSYNC

也就是 3 线 SPI。

### 6. SPI 的几个关键概念

#### 主机和从机

STM32 控制 AD9833 时：

- STM32 是主机
- AD9833 是从机
- STM32 提供 SCLK
- STM32 通过 MOSI/SDATA 发送数据
- STM32 控制 FSYNC 低电平选中 AD9833

#### 片选 FSYNC

AD9833 的 FSYNC 是帧同步信号，也可以当作片选。

写入一个 16 位字的基本过程：

1. SCLK 空闲保持高电平
2. FSYNC 拉低
3. STM32 发送 16 位数据，MSB 先发
4. AD9833 在 SCLK 下降沿移入数据
5. 16 位发送完成后 FSYNC 拉高

FSYNC 也可以一直保持低电平，连续发送多个 16 位字；等最后一个 16 位字发完后再拉高。

#### SPI 模式

数据手册给出的微控制器接口建议：

- SCK 空闲为高电平：`CPOL = 1`
- 数据在 SCK 下降沿有效：`CPHA = 0`
- 数据 MSB first

这通常对应 SPI Mode 2：

```text
CPOL = 1
CPHA = 0
```

STM32 配置硬件 SPI 时建议：

- Master 主机模式
- 只发送即可，可用 Transmit Only 或 2 Lines 但不接 MISO
- Data Size：8 bit 或 16 bit 都可以
- First Bit：MSB First
- Clock Polarity：High
- Clock Phase：1 Edge
- NSS：软件管理，用普通 GPIO 控制 FSYNC
- Baud Rate：低速先调通，再逐步提高

如果使用 8 位 SPI 发送一个 16 位字，要保持 FSYNC 为低，然后连续发送高字节和低字节，最后再拉高 FSYNC。

### 7. AD9833 串行写入格式

AD9833 每次接收一个 16 位字。

```text
D15 D14 D13 ... D0
```

不同的 `D15:D14` 表示写入目标不同：

| D15:D14 | 含义 |
|---|---|
| `00` | 写控制寄存器 |
| `01` | 写 FREQ0 频率寄存器的 14 位数据 |
| `10` | 写 FREQ1 频率寄存器的 14 位数据 |
| `11` | 写 PHASE0 或 PHASE1 相位寄存器 |

AD9833 的频率寄存器是 28 位，但一次 SPI 只能写 16 位，其中只有 14 位是频率数据，所以完整写一个频率需要连续写两次：

1. 写低 14 位
2. 写高 14 位

### 8. 频率计算公式

AD9833 的输出频率由 MCLK 和频率寄存器决定：

```text
fOUT = FREQREG * fMCLK / 2^28
```

反过来，如果想输出某个频率：

```text
FREQREG = fOUT * 2^28 / fMCLK
```

其中：

- `fOUT`：想要输出的频率
- `fMCLK`：AD9833 的主时钟频率
- `FREQREG`：要写入的 28 位频率控制字

常见 AD9833 模块的 MCLK 是 `25MHz`。

例如想输出 `1kHz`，MCLK 为 `25MHz`：

```text
FREQREG = 1000 * 2^28 / 25000000
        ≈ 10737
        ≈ 0x000029F1
```

然后拆成两个 14 位：

```text
低 14 位 = FREQREG & 0x3FFF
高 14 位 = (FREQREG >> 14) & 0x3FFF
```

写 FREQ0 时，每个 14 位数据前面加地址位 `01`：

```c
freq_lsb_word = 0x4000 | (freq_word & 0x3FFF);
freq_msb_word = 0x4000 | ((freq_word >> 14) & 0x3FFF);
```

写 FREQ1 时，每个 14 位数据前面加地址位 `10`：

```c
freq_lsb_word = 0x8000 | (freq_word & 0x3FFF);
freq_msb_word = 0x8000 | ((freq_word >> 14) & 0x3FFF);
```

### 9. 相位计算公式

AD9833 的相位寄存器是 12 位。

相位偏移公式：

```text
PhaseRegister = phase * 4096 / 2π
```

如果用角度表示：

```text
PhaseRegister = phase_degree * 4096 / 360
```

例如：

| 相位 | 寄存器值 |
|---|---|
| 0° | 0 |
| 90° | 1024 |
| 180° | 2048 |
| 270° | 3072 |

写 PHASE0：

```c
phase_word = 0xC000 | (phase_reg & 0x0FFF);
```

写 PHASE1：

```c
phase_word = 0xE000 | (phase_reg & 0x0FFF);
```

因为：

- PHASE 写入时 `D15:D14 = 11`
- `D13 = 0` 选择 PHASE0
- `D13 = 1` 选择 PHASE1

### 10. 控制寄存器

控制寄存器是 AD9833 使用中最重要的寄存器。

控制寄存器 16 位格式：

```text
D15 D14 D13 D12 D11 D10 D9 D8 D7 D6 D5 D4 D3 D2 D1 D0
 0   0  B28 HLB FSEL PSEL 0 RST SLP1 SLP12 OPBITEN 0 DIV2 0 MODE 0
```

常用位说明：

| 位 | 名称 | 作用 |
|---|---|---|
| D13 | B28 | 1 表示连续两次 16 位写入完整 28 位频率字 |
| D12 | HLB | B28=0 时选择写高 14 位还是低 14 位 |
| D11 | FSELECT | 0 选择 FREQ0，1 选择 FREQ1 |
| D10 | PSELECT | 0 选择 PHASE0，1 选择 PHASE1 |
| D8 | RESET | 1 复位内部寄存器，0 开始输出 |
| D7 | SLEEP1 | 1 关闭内部 MCLK |
| D6 | SLEEP12 | 1 关闭 DAC |
| D5 | OPBITEN | 1 输出数字方波，0 输出 DAC 波形 |
| D3 | DIV2 | 配合 OPBITEN，选择 MSB 或 MSB/2 |
| D1 | MODE | 0 正弦波，1 三角波 |

保留位要写 0。

### 11. 常用控制字

下面这些控制字适合入门直接使用。

#### 复位并准备写 28 位频率

```c
0x2100
```

含义：

- B28 = 1
- RESET = 1
- 方便连续写入完整 28 位频率字
- 输出暂时保持复位状态

#### 输出正弦波

```c
0x2000
```

含义：

- B28 = 1
- RESET = 0
- OPBITEN = 0
- MODE = 0
- 输出正弦波

#### 输出三角波

```c
0x2002
```

含义：

- B28 = 1
- RESET = 0
- MODE = 1
- OPBITEN = 0
- 输出三角波

#### 输出方波

常见写法：

```c
0x2028
```

含义：

- B28 = 1
- OPBITEN = 1
- DIV2 = 1
- MODE = 0
- VOUT 输出 DAC 数据 MSB 对应的方波

如果希望关闭 DAC 省电，可以配合 SLEEP12：

```c
0x2068
```

这里 SLEEP12 = 1，DAC 关闭，只输出数字方波路径。

### 12. AD9833 初始化推荐流程

数据手册建议上电后先复位 AD9833。

推荐流程：

1. 初始化 STM32 的 SPI 和 FSYNC GPIO
2. FSYNC 默认拉高
3. 写控制字 `0x2100`，让 AD9833 进入 RESET，并设置 B28
4. 计算目标频率对应的 28 位频率字
5. 写 FREQ0 低 14 位
6. 写 FREQ0 高 14 位
7. 写 PHASE0，通常先写 0
8. 写控制字选择波形并清除 RESET
9. VOUT 开始输出波形

例如输出 1kHz 正弦波：

```text
写 0x2100
计算 1kHz 的 FREQREG
写 0x4000 | 低14位
写 0x4000 | 高14位
写 0xC000 | 0x000
写 0x2000
```

AD9833 在清除 RESET 后，大约经过 7 或 8 个 MCLK 周期，模拟输出才会变化。

### 13. STM32 HAL 硬件 SPI 示例

下面是通用写法，假设：

- 使用 `hspi1`
- FSYNC 接在 `AD9833_FSYNC_GPIO_Port`
- FSYNC 引脚是 `AD9833_FSYNC_Pin`
- AD9833 MCLK 是 25MHz

```c
#include "main.h"
#include <stdint.h>

#define AD9833_MCLK 25000000UL

extern SPI_HandleTypeDef hspi1;

static void AD9833_Write16(uint16_t data)
{
    uint8_t tx[2];

    tx[0] = (uint8_t)(data >> 8);
    tx[1] = (uint8_t)(data & 0xFF);

    HAL_GPIO_WritePin(AD9833_FSYNC_GPIO_Port, AD9833_FSYNC_Pin, GPIO_PIN_RESET);
    HAL_SPI_Transmit(&hspi1, tx, 2, HAL_MAX_DELAY);
    HAL_GPIO_WritePin(AD9833_FSYNC_GPIO_Port, AD9833_FSYNC_Pin, GPIO_PIN_SET);
}
```

注意：

- AD9833 要求 MSB first，所以先发高字节
- FSYNC 必须在 16 位发送期间保持低电平
- 如果用 8 位 SPI，发送两个字节时 FSYNC 不要中途拉高

### 14. 设置频率函数

```c
static void AD9833_SetFrequency(uint8_t freq_reg, uint32_t freq_hz)
{
    uint32_t freq_word;
    uint16_t lsb;
    uint16_t msb;
    uint16_t addr;

    freq_word = (uint32_t)((uint64_t)freq_hz * 268435456ULL / AD9833_MCLK);

    if (freq_reg == 0)
    {
        addr = 0x4000;   // FREQ0
    }
    else
    {
        addr = 0x8000;   // FREQ1
    }

    lsb = addr | (uint16_t)(freq_word & 0x3FFF);
    msb = addr | (uint16_t)((freq_word >> 14) & 0x3FFF);

    AD9833_Write16(lsb);
    AD9833_Write16(msb);
}
```

这里使用 `uint64_t` 是为了避免乘法溢出。

### 15. 设置相位函数

```c
static void AD9833_SetPhase(uint8_t phase_reg, uint16_t phase_value)
{
    phase_value &= 0x0FFF;

    if (phase_reg == 0)
    {
        AD9833_Write16(0xC000 | phase_value);  // PHASE0
    }
    else
    {
        AD9833_Write16(0xE000 | phase_value);  // PHASE1
    }
}
```

如果用角度设置相位：

```c
static uint16_t AD9833_DegreeToPhase(float degree)
{
    return (uint16_t)(degree * 4096.0f / 360.0f) & 0x0FFF;
}
```

### 16. 输出波形函数

```c
typedef enum
{
    AD9833_WAVE_SINE,
    AD9833_WAVE_TRIANGLE,
    AD9833_WAVE_SQUARE
} AD9833_WaveType;

static void AD9833_SetWave(AD9833_WaveType wave)
{
    switch (wave)
    {
        case AD9833_WAVE_SINE:
            AD9833_Write16(0x2000);
            break;

        case AD9833_WAVE_TRIANGLE:
            AD9833_Write16(0x2002);
            break;

        case AD9833_WAVE_SQUARE:
            AD9833_Write16(0x2028);
            break;
    }
}
```

### 17. 完整初始化示例

```c
void AD9833_Init(uint32_t freq_hz, AD9833_WaveType wave)
{
    HAL_GPIO_WritePin(AD9833_FSYNC_GPIO_Port, AD9833_FSYNC_Pin, GPIO_PIN_SET);

    AD9833_Write16(0x2100);       // RESET=1, B28=1
    AD9833_SetFrequency(0, freq_hz);
    AD9833_SetPhase(0, 0);
    AD9833_SetWave(wave);         // RESET=0, 开始输出
}
```

使用：

```c
AD9833_Init(1000, AD9833_WAVE_SINE);
```

表示输出 1kHz 正弦波。

### 18. 如何切换频率

AD9833 有两个频率寄存器：

- FREQ0
- FREQ1

可以提前把两个频率写进去，然后通过 FSELECT 快速切换。

例如：

```c
AD9833_Write16(0x2100);
AD9833_SetFrequency(0, 1000);   // FREQ0 = 1kHz
AD9833_SetFrequency(1, 2000);   // FREQ1 = 2kHz
AD9833_SetPhase(0, 0);
AD9833_Write16(0x2000);         // 选择 FREQ0 输出正弦
```

选择 FREQ1：

```c
AD9833_Write16(0x2800);         // B28=1, FSELECT=1, 正弦输出
```

切回 FREQ0：

```c
AD9833_Write16(0x2000);         // B28=1, FSELECT=0, 正弦输出
```

这可以用于 FSK 调制：

- FREQ0：表示一个频率
- FREQ1：表示另一个频率
- 不断切换 FSELECT 就能在两个频率之间跳变

### 19. 如何切换相位

AD9833 有两个相位寄存器：

- PHASE0
- PHASE1

可以通过 PSELECT 选择。

例如：

```c
AD9833_SetPhase(0, 0);       // 0°
AD9833_SetPhase(1, 2048);    // 180°
```

选择 PHASE1：

```c
AD9833_Write16(0x2400);      // B28=1, PSELECT=1, FREQ0, 正弦
```

这可以用于 PSK 调制。

### 20. 软件 SPI 写 AD9833 的逻辑

如果不用硬件 SPI，可以用 GPIO 模拟。

AD9833 的关键是：

- SCLK 空闲高
- FSYNC 拉低开始
- MSB 先发
- 每一位在 SCLK 下降沿被 AD9833 采样
- 16 位发完后 FSYNC 拉高

伪代码：

```c
void AD9833_Write16_SoftSPI(uint16_t data)
{
    FSYNC_HIGH();
    SCLK_HIGH();

    FSYNC_LOW();

    for (int i = 15; i >= 0; i--)
    {
        if (data & (1 << i))
        {
            SDATA_HIGH();
        }
        else
        {
            SDATA_LOW();
        }

        SCLK_LOW();     // AD9833 在下降沿采样
        SPI_DELAY();
        SCLK_HIGH();
        SPI_DELAY();
    }

    FSYNC_HIGH();
}
```

软件 SPI 的优点是引脚灵活，缺点是速度慢、占用 CPU。

### 21. 调试步骤建议

第一次调试 AD9833，不要一上来就追求高频和复杂功能。

推荐步骤：

1. 确认模块供电和共地
2. 确认模块是否有 25MHz MCLK
3. STM32 SPI 先降速，例如几百 kHz 到 1MHz
4. 先输出 1kHz 正弦波
5. 用示波器看 VOUT
6. 再测试三角波
7. 再测试方波
8. 再测试动态改频率

如果没有示波器，至少可以用万用表交流档粗略观察，但无法可靠判断频率和波形质量。

### 22. 常见问题排查

#### 没有波形输出

检查：

- VCC 是否正确
- GND 是否共地
- MCLK 是否存在
- FSYNC 是否默认拉高
- SPI 是否真的发出了 SCLK
- SDATA 是否接到 MOSI
- 是否写了 RESET=0 的控制字
- 频率字是否计算正确
- VOUT 后级是否被短路或负载太重

#### 频率不对

常见原因：

- MCLK 不是代码里写的 25MHz
- 频率公式写错
- 没有用 64 位计算，导致乘法溢出
- 高 14 位和低 14 位顺序写反
- 写 FREQ0/FREQ1 地址位错误

#### 波形失真

常见原因：

- 输出频率太接近上限
- 没有低通滤波
- 负载过重
- 电源噪声大
- 地线和布局不好
- VOUT 直接接了不合适的负载

#### SPI 写入无效

检查：

- SPI 模式是否为 CPOL=1、CPHA=0
- 是否 MSB First
- FSYNC 是否在完整 16 位期间保持低
- 8 位发送时是否先发高字节
- SCLK 速度是否过高

### 23. AD9833 使用逻辑总结

最重要的使用逻辑可以压缩成 5 句话：

1. AD9833 通过 3 线 SPI 接收 16 位控制字。
2. 频率寄存器是 28 位，完整写入需要连续写低 14 位和高 14 位。
3. 输出频率由 `FREQREG * fMCLK / 2^28` 决定。
4. 控制寄存器决定复位、波形类型、频率寄存器选择、相位寄存器选择和睡眠状态。
5. 上电后先 RESET，写频率和相位，再清除 RESET 开始输出。

### 24. 推荐最小代码流程

```c
// 1. SPI 和 GPIO 初始化由 CubeMX 或手写完成

// 2. AD9833 复位，允许完整 28 位频率写入
AD9833_Write16(0x2100);

// 3. 写入 FREQ0 = 1000Hz
AD9833_SetFrequency(0, 1000);

// 4. PHASE0 = 0
AD9833_SetPhase(0, 0);

// 5. 输出正弦波
AD9833_Write16(0x2000);
```

如果这段能输出 1kHz 正弦波，说明：

- SPI 基本正常
- FSYNC 控制正常
- 频率计算正常
- AD9833 主时钟正常

后面再扩展三角波、方波、扫频、FSK、PSK 会更稳。

---

