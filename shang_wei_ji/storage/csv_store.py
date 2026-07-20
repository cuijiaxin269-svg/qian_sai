import csv
from pathlib import Path
from typing import Iterable

from models.measurement import MeasurementRecord


def save_records(records: Iterable[MeasurementRecord], directory: str, prefix: str) -> Path:
    folder = Path(directory).expanduser().resolve()
    folder.mkdir(parents=True, exist_ok=True)
    rows = list(records)
    timestamp = rows[0].timestamp.replace(":", "-").replace(" ", "_") if rows else "empty"
    path = folder / f"{prefix}_{timestamp}.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=[
            "timestamp", "task_id", "cap_type", "capacitance_f", "capacitance_pf",
            "bias_set_v", "bias_actual_v", "quality", "valid", "scan_sequence",
            "point_index", "point_total", "gear", "range_status",
        ])
        writer.writeheader()
        for record in rows:
            writer.writerow({
                "timestamp": record.timestamp,
                "task_id": record.task_id,
                "cap_type": record.cap_type,
                "capacitance_f": record.capacitance_f,
                "capacitance_pf": record.capacitance_pf,
                "bias_set_v": "" if record.bias_set_v is None else record.bias_set_v,
                "bias_actual_v": "" if record.bias_actual_v is None else record.bias_actual_v,
                "quality": "" if record.quality is None else record.quality,
                "valid": int(record.valid),
                "scan_sequence": "" if record.scan_sequence is None else record.scan_sequence,
                "point_index": "" if record.point_index is None else record.point_index,
                "point_total": "" if record.point_total is None else record.point_total,
                "gear": "" if record.gear is None else record.gear,
                "range_status": "" if record.range_status is None else record.range_status,
            })
    return path
