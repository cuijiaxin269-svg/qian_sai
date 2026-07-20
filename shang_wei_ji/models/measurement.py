from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class MeasurementRecord:
    task_id: str
    cap_type: str
    capacitance_f: float
    bias_actual_v: float | None = None
    quality: float | None = None
    valid: bool = True
    bias_set_v: float | None = None
    scan_sequence: int | None = None
    point_index: int | None = None
    point_total: int | None = None
    gear: int | None = None
    range_status: str | None = None
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            object.__setattr__(self, "timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    @property
    def capacitance_pf(self) -> float:
        return self.capacitance_f * 1e12


def format_capacitance(value_f: float) -> str:
    absolute = abs(value_f)
    if absolute >= 1e-6:
        return f"{value_f * 1e6:.3f} µF"
    if absolute >= 1e-9:
        return f"{value_f * 1e9:.3f} nF"
    return f"{value_f * 1e12:.3f} pF"
