#!/usr/bin/env python3
"""Receive AD9238 CSV frames from STM32 USART and plot channel A/B."""

from __future__ import annotations

import argparse
import csv
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import serial
from serial.tools import list_ports


FRAME_BEGIN = "AD9238_FRAME_BEGIN"
FRAME_END = "AD9238_FRAME_END"
DATA_HEADER = "format,index,ch_a,ch_b"
ADC_BITS = 12
ADC_MAX_CODE = (1 << ADC_BITS) - 1
ADC_MID_CODE = 2048
ADC_FULL_SCALE_VPP = 10.0


@dataclass
class Ad9238Frame:
    raw_samples: int | None
    channel_samples: int | None
    index: list[int]
    ch_a: list[int]
    ch_b: list[int]


def code_to_voltage(code: int) -> float:
    return ((code & ADC_MAX_CODE) - ADC_MID_CODE) * ADC_FULL_SCALE_VPP / 4096.0


def list_serial_ports() -> None:
    ports = list(list_ports.comports())
    if not ports:
        print("没有发现串口。请检查 USB 转串口是否插好。")
        return

    print("可用串口：")
    for port in ports:
        desc = port.description or ""
        hwid = port.hwid or ""
        print(f"  {port.device:8s}  {desc}  {hwid}")


def read_line_text(ser: serial.Serial) -> str:
    raw = ser.readline()
    if not raw:
        return ""
    return raw.decode("utf-8", errors="replace").strip()


def read_frame(ser: serial.Serial) -> Ad9238Frame | None:
    raw_samples: int | None = None
    channel_samples: int | None = None
    indexes: list[int] = []
    ch_a: list[int] = []
    ch_b: list[int] = []
    in_frame = False
    in_data = False

    while True:
        line = read_line_text(ser)
        if not line:
            return None

        if line == FRAME_BEGIN:
            in_frame = True
            in_data = False
            raw_samples = None
            channel_samples = None
            indexes.clear()
            ch_a.clear()
            ch_b.clear()
            continue

        if line == "AD9238_UART_READY" or line.startswith("AD9238_STATUS,"):
            print(f"[STM32] {line}")
            continue

        if not in_frame:
            continue

        if line == FRAME_END:
            if indexes:
                return Ad9238Frame(raw_samples, channel_samples, indexes, ch_a, ch_b)
            return None

        if line.startswith("raw_samples,"):
            raw_samples = int(line.split(",", 1)[1])
            continue

        if line.startswith("channel_samples,"):
            channel_samples = int(line.split(",", 1)[1])
            continue

        if line == DATA_HEADER:
            in_data = True
            continue

        if in_data:
            parts = line.split(",")
            if len(parts) != 3:
                continue
            try:
                idx = int(parts[0])
                a = int(parts[1]) & ADC_MAX_CODE
                b = int(parts[2]) & ADC_MAX_CODE
            except ValueError:
                continue
            indexes.append(idx)
            ch_a.append(a)
            ch_b.append(b)


def save_frame_csv(frame: Ad9238Frame, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = time.strftime("ad9238_%Y%m%d_%H%M%S.csv")
    path = output_dir / filename

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["index", "ch_a_code", "ch_b_code", "ch_a_v", "ch_b_v"])
        for idx, a, b in zip(frame.index, frame.ch_a, frame.ch_b):
            writer.writerow([idx, a, b, f"{code_to_voltage(a):.6f}", f"{code_to_voltage(b):.6f}"])

    return path


def make_time_axis(frame: Ad9238Frame, sample_rate: float) -> list[float]:
    if sample_rate <= 0:
        return [float(i) for i in frame.index]
    return [i / sample_rate for i in frame.index]


def make_demo_frame(sample_count: int = 2048) -> Ad9238Frame:
    indexes = list(range(sample_count))
    ch_a: list[int] = []
    ch_b: list[int] = []

    for i in indexes:
        phase = 2.0 * math.pi * 12.0 * i / sample_count
        a = int(ADC_MID_CODE + 1200.0 * math.sin(phase))
        b = int(ADC_MID_CODE + 700.0 * math.sin(phase - math.radians(35.0)))
        ch_a.append(max(0, min(ADC_MAX_CODE, a)))
        ch_b.append(max(0, min(ADC_MAX_CODE, b)))

    return Ad9238Frame(sample_count * 2, sample_count, indexes, ch_a, ch_b)


def update_plot(ax_code, ax_volt, frame: Ad9238Frame, sample_rate: float) -> None:
    t = make_time_axis(frame, sample_rate)
    ch_a_v = [code_to_voltage(x) for x in frame.ch_a]
    ch_b_v = [code_to_voltage(x) for x in frame.ch_b]

    ax_code.clear()
    ax_code.plot(t, frame.ch_a, label="CH_A code", linewidth=1.0)
    ax_code.plot(t, frame.ch_b, label="CH_B code", linewidth=1.0)
    ax_code.set_ylabel("ADC code")
    ax_code.set_ylim(-64, 4160)
    ax_code.grid(True, alpha=0.3)
    ax_code.legend(loc="upper right")

    ax_volt.clear()
    ax_volt.plot(t, ch_a_v, label="CH_A voltage", linewidth=1.0)
    ax_volt.plot(t, ch_b_v, label="CH_B voltage", linewidth=1.0)
    ax_volt.set_xlabel("Time (s)" if sample_rate > 0 else "Sample index")
    ax_volt.set_ylabel("Voltage (V)")
    ax_volt.grid(True, alpha=0.3)
    ax_volt.legend(loc="upper right")

    ax_code.set_title(
        f"AD9238 frame: {len(frame.index)} samples/channel, "
        f"raw={frame.raw_samples}, channel={frame.channel_samples}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AD9238 STM32 serial waveform viewer")
    parser.add_argument("-p", "--port", help="串口号，例如 COM5")
    parser.add_argument("-b", "--baud", type=int, default=115200, help="波特率，默认 115200")
    parser.add_argument(
        "-r",
        "--sample-rate",
        type=float,
        default=10_000_000.0,
        help="每路采样率 Hz，默认 1600000",
    )
    parser.add_argument("--list-ports", action="store_true", help="列出可用串口后退出")
    parser.add_argument("--demo", action="store_true", help="使用模拟双通道数据预览界面")
    parser.add_argument("--save-csv", action="store_true", help="保存收到的每一帧 CSV")
    parser.add_argument("--save-plot", type=Path, help="把当前波形保存为 PNG")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("captures"),
        help="CSV 保存目录，默认 captures",
    )
    parser.add_argument("--once", action="store_true", help="只接收并显示一帧")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.list_ports:
        list_serial_ports()
        return 0

    if args.demo:
        frame = make_demo_frame()
        fig, (ax_code, ax_volt) = plt.subplots(2, 1, sharex=True, figsize=(11, 7))
        update_plot(ax_code, ax_volt, frame, args.sample_rate)
        fig.tight_layout()
        if args.save_plot:
            args.save_plot.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(args.save_plot, dpi=150)
            print(f"演示图已保存：{args.save_plot}")
        else:
            plt.show()
        return 0

    if not args.port:
        print("请指定串口，例如：")
        print("  python tools/ad9238_serial_viewer.py --list-ports")
        print("  python tools/ad9238_serial_viewer.py -p COM5")
        return 2

    plt.ion()
    fig, (ax_code, ax_volt) = plt.subplots(2, 1, sharex=True, figsize=(11, 7))

    print(f"打开串口 {args.port}, baud={args.baud}")
    with serial.Serial(args.port, args.baud, timeout=3) as ser:
        ser.reset_input_buffer()
        print("等待 STM32 数据帧...")

        while True:
            frame = read_frame(ser)
            if frame is None:
                print("等待帧超时或收到空数据，继续等待...")
                continue

            print(
                f"收到一帧：{len(frame.index)} 点/通道, "
                f"CH_A[0]={frame.ch_a[0]}, CH_B[0]={frame.ch_b[0]}"
            )

            if args.save_csv:
                saved = save_frame_csv(frame, args.output_dir)
                print(f"已保存：{saved}")

            update_plot(ax_code, ax_volt, frame, args.sample_rate)
            fig.tight_layout()
            if args.save_plot:
                args.save_plot.parent.mkdir(parents=True, exist_ok=True)
                fig.savefig(args.save_plot, dpi=150)
            fig.canvas.draw()
            fig.canvas.flush_events()
            plt.pause(0.01)

            if args.once:
                print("已完成单帧接收。关闭图窗后程序退出。")
                plt.ioff()
                plt.show()
                break

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n已停止。")
        raise SystemExit(0)
    except serial.SerialException as exc:
        print(f"串口错误：{exc}", file=sys.stderr)
        raise SystemExit(1)
