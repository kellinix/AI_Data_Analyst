"""Generate small, non-personal cross-industry files for local report review."""

from __future__ import annotations

import argparse
import csv
from datetime import date, timedelta
from pathlib import Path


def write_csv(path: Path, headers: list[str], rows: list[list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def generate(folder: Path) -> None:
    start = date(2025, 1, 1)
    write_csv(folder / "clinic_appointments.csv",
              ["appointment_date", "clinic", "appointment_status", "wait_minutes", "fee_amount"],
              [[start + timedelta(days=i), ["North", "South", "West"][i % 3],
                "Attended" if i % 7 else "Cancelled", 15 + i % 26 if i % 7 else "",
                60 if i % 7 else 0] for i in range(180)])
    write_csv(folder / "factory_batches.csv",
              ["batch_date", "product_line", "shift", "units_produced", "defect_count", "downtime_minutes"],
              [[start + timedelta(days=i), ["Parts A", "Parts B"][i % 2],
                ["Day", "Night"][i % 2], 80 + i % 41,
                i % 4, 5 + i % 13] for i in range(180)])
    write_csv(folder / "energy_usage.csv",
              ["reading_date", "site", "kwh_consumed", "energy_cost", "peak_demand_kw"],
              [[start + timedelta(days=i), ["Depot", "Office", "Warehouse"][i % 3],
                300 + i % 100, 90 + i % 30, 40 + i % 18] for i in range(180)])
    write_csv(folder / "hiring_pipeline.csv",
              ["application_date", "department", "hiring_stage", "hired", "days_to_decision"],
              [[start + timedelta(days=i), ["Support", "Engineering", "Sales"][i % 3],
                "Hired" if i % 5 == 0 else "Not hired", 1 if i % 5 == 0 else 0,
                10 + i % 22] for i in range(180)])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    generate(parser.parse_args().output)
