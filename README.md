# 嵌入式测量与信号采集工程

本仓库汇集基于 STM32 的高速数据采集、DDS 信号发生、DAC 输出、继电器矩阵控制，以及配套上位机控制程序。仓库只保存可编辑的源码、工程配置和必要说明；大体积资料、工具链安装包、视频、编译产物与本地日志均由 `.gitignore` 排除。

## 目录说明

| 目录 | 内容 |
| --- | --- |
| `all_code/AD9238_data_read` | AD9238 双通道采集基础工程，包含 PSSI + DMA 采集、J-Link 脚本和数据分析工具。 |
| `all_code/AD9238_DDS_data_read` | 在 AD9238 采集基础上增加 DDS 三线 GPIO 控制的工程。 |
| `all_code/DA_out` | STM32H7R7L8 控制 DAC1220 的三线 GPIO 输出工程。 |
| `all_code/ad9938dds` | 基于 STM32H743 的 AD9938/DDS 工程，包含 Keil 与 IAR 工程文件。 |
| `all_code/JiDianQiJuZhen` | 继电器矩阵控制工程。 |
| `shang_wei_ji/pp` | Python/Streamlit 上位机程序及启动、打包脚本。 |
| `information` | 经过整理的技术笔记、接口与测量流程说明。厂家原始资料位于本地，但不纳入 Git。 |
| `outputs/ad9238_ioc_export` | 从 CubeMX 配置导出的 AD9238 引脚配置表。 |

## 固件工程使用方法

1. 根据目标工程进入对应目录，例如 `all_code/AD9238_DDS_data_read`。
2. 使用 STM32CubeMX 打开 `.ioc` 文件检查芯片、时钟和外设配置。
3. 使用 VS Code/CMake 或 Keil/IAR 打开相应工程文件进行编译。
4. 连接 ST-LINK 或 J-Link，确认目标板供电和 SWD 接线后烧录。

各工程内的 `README`、`工程说明`、`.vscode/tasks.json` 和 `tools/` 目录提供与该工程对应的编译、烧录或采集辅助信息。

### AD9238 + DDS 工程

`all_code/AD9238_DDS_data_read` 使用 AD9238 的 PSSI + DMA 双通道采集，并通过 GPIO 软件时序控制 DDS。默认 DDS 引脚为：

| 信号 | STM32 引脚 |
| --- | --- |
| SYNC / FSYNC | PD5 |
| CLK / SCLK | PE2 |
| DATA / SDATA | PE14 |

### DAC1220 工程

`all_code/DA_out` 通过 GPIO 软件时序驱动 DAC1220：

| 信号 | STM32 引脚 |
| --- | --- |
| CS | PF1 |
| SDIO | PB5 |
| SCLK | PC10 |

上电默认输出约为 2.5 V（以 `VREF = 2.5 V`、16 位 Straight Binary 配置为前提）。

## 上位机程序

进入 `shang_wei_ji/pp` 后，可使用 Windows 命令行启动：

```bat
start_control_app.cmd
```

程序依赖 Python、Streamlit、pyserial、pandas 和 numpy。运行前请按实际设备修改串口、仪器连接和数据保存路径；当前程序中的部分本地路径来自开发机，迁移到新电脑时需要重新配置。

## 版本管理约定

- 提交：源码、头文件、链接脚本、`.ioc`、工程文件、构建配置、必要的说明文档和辅助脚本。
- 不提交：`build` 输出、`.o/.axf/.hex` 等目标文件、日志、IDE 个人配置、压缩备份、工具链安装包、视频与厂家原始资料。
- 若确实需要共享大文件，请使用 Git LFS 或发行版附件，不要直接加入普通 Git 提交。

## 说明

硬件接线、供电电压和烧录操作具有风险。首次运行或修改引脚配置前，请先核对原理图、芯片手册和板卡实际连接。
