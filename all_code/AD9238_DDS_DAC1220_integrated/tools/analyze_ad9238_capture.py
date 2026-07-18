#!/usr/bin/env python3
"""Analyze one J-Link-saved AD9238 interleaved capture and plot both channels."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import minimize_scalar


ADC_FULL_SCALE_VPP = 10.0


def wrap_deg(value: float) -> float:
    return (value + 180.0) % 360.0 - 180.0


def fit_sine(values: np.ndarray, sample_rate: float, expected_hz: float) -> dict[str, float]:
    t = np.arange(values.size, dtype=np.float64) / sample_rate
    search_half_width = max(sample_rate / values.size * 3.0, expected_hz * 0.03)

    def solve(freq: float) -> tuple[float, np.ndarray]:
        angle = 2.0 * np.pi * freq * t
        design = np.column_stack((np.sin(angle), np.cos(angle), np.ones(values.size)))
        coeff, *_ = np.linalg.lstsq(design, values, rcond=None)
        residual = values - design @ coeff
        return float(residual @ residual), coeff

    optimum = minimize_scalar(
        lambda freq: solve(freq)[0],
        bounds=(expected_hz - search_half_width, expected_hz + search_half_width),
        method="bounded",
        options={"xatol": 0.01},
    )
    frequency = float(optimum.x)
    residual_ss, coeff = solve(frequency)
    sin_coeff, cos_coeff, dc = (float(x) for x in coeff)
    amplitude_peak = math.hypot(sin_coeff, cos_coeff)
    phase_deg = math.degrees(math.atan2(cos_coeff, sin_coeff))
    rms_error = math.sqrt(residual_ss / values.size)
    return {
        "frequency_hz": frequency,
        "dc_v": dc,
        "amplitude_peak_v": amplitude_peak,
        "vpp_v": 2.0 * amplitude_peak,
        "phase_deg_at_t0": phase_deg,
        "fit_rms_error_v": rms_error,
        "min_v": float(values.min()),
        "max_v": float(values.max()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", type=Path)
    parser.add_argument("--sample-rate", type=float, default=10_000_000.0)
    parser.add_argument("--a-frequency", type=float, default=1_000_000.0)
    parser.add_argument("--b-frequency", type=float, default=500_000.0)
    parser.add_argument("--planar", action="store_true", help="input stores all A samples then all B samples")
    parser.add_argument("--output", type=Path, default=Path("build/vscode-debug/ad9238_result.png"))
    args = parser.parse_args()

    raw = np.fromfile(args.capture, dtype="<u2")
    if raw.size < 4 or raw.size % 2:
        raise SystemExit(f"invalid interleaved capture length: {raw.size}")
    raw &= 0x0FFF
    if args.planar:
        midpoint = raw.size // 2
        ch_a_code = raw[:midpoint]
        ch_b_code = raw[midpoint:]
    else:
        ch_a_code = raw[0::2]
        ch_b_code = raw[1::2]
    ch_a_signed = ch_a_code.astype(np.int32)
    ch_b_signed = ch_b_code.astype(np.int32)
    ch_a_signed[ch_a_signed >= 0x800] -= 0x1000
    ch_b_signed[ch_b_signed >= 0x800] -= 0x1000
    ch_a = ch_a_signed.astype(np.float64) * ADC_FULL_SCALE_VPP / 4096.0
    ch_b = ch_b_signed.astype(np.float64) * ADC_FULL_SCALE_VPP / 4096.0

    direct_a = fit_sine(ch_a, args.sample_rate, args.a_frequency)
    direct_b = fit_sine(ch_b, args.sample_rate, args.b_frequency)
    swapped_a = fit_sine(ch_a, args.sample_rate, args.b_frequency)
    swapped_b = fit_sine(ch_b, args.sample_rate, args.a_frequency)
    direct_error = direct_a["fit_rms_error_v"] + direct_b["fit_rms_error_v"]
    swapped_error = swapped_a["fit_rms_error_v"] + swapped_b["fit_rms_error_v"]
    if swapped_error < direct_error:
        ch_a, ch_b = ch_b, ch_a
        ch_a_code, ch_b_code = ch_b_code, ch_a_code
        result_a, result_b = swapped_b, swapped_a
    else:
        result_a, result_b = direct_a, direct_b
    result = {
        "sample_rate_hz": args.sample_rate,
        "samples_per_channel": int(ch_a.size),
        "channel_a": result_a,
        "channel_b": result_b,
        "phase_a_minus_b_deg_at_t0": wrap_deg(
            result_a["phase_deg_at_t0"] - result_b["phase_deg_at_t0"]
        ),
        "harmonic_phase_a_minus_2b_deg": wrap_deg(
            result_a["phase_deg_at_t0"] - 2.0 * result_b["phase_deg_at_t0"]
        ),
        "clipped_low_a": int(np.count_nonzero(ch_a_code == 0x800)),
        "clipped_high_a": int(np.count_nonzero(ch_a_code == 0x7FF)),
        "clipped_low_b": int(np.count_nonzero(ch_b_code == 0x800)),
        "clipped_high_b": int(np.count_nonzero(ch_b_code == 0x7FF)),
    }

    show_count = min(ch_a.size, int(round(args.sample_rate * 10e-6)))
    t_us = np.arange(show_count) / args.sample_rate * 1e6
    fig, ax = plt.subplots(figsize=(11, 5.8))
    ax.plot(t_us, ch_a[:show_count], "o-", ms=3, lw=1.2, label="CH A measured")
    ax.plot(t_us, ch_b[:show_count], "o-", ms=3, lw=1.2, label="CH B measured")
    ax.axhline(0.0, color="black", lw=0.7, alpha=0.5)
    ax.set_xlabel("Time (us)")
    ax.set_ylabel("Voltage (V, configured 10 Vpp full scale)")
    ax.set_title(
        "AD9238 capture | "
        f"A {result_a['frequency_hz']/1e6:.4f} MHz, {result_a['vpp_v']:.3f} Vpp | "
        f"B {result_b['frequency_hz']/1e3:.2f} kHz, {result_b['vpp_v']:.3f} Vpp"
    )
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")
    fig.tight_layout()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=180)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"plot={args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
