import numpy as np
import pandas as pd

from backend.fire import SOURCES, workspace


def daily_grid(area, start, end):
    """Match detections by UTC day and shared approximately 5 km geographic cell."""
    root = workspace(area) / "processed"
    days = [{part.stem: part for part in (root / source).glob("*.parquet")
             if start <= part.stem <= end} for source in SOURCES]
    records = []
    for day in sorted(days[0].keys() & days[1].keys()):
        counts = []
        for source, partitions in zip(SOURCES, days):
            points = pd.read_parquet(partitions[day], columns=["latitude", "longitude"])
            points["y"] = np.floor((points.latitude + 90) * 22.2).astype(int)
            points["x"] = np.floor((points.longitude + 180) * 22.2).astype(int)
            counts.append(points.groupby(["y", "x"]).size().rename(source))
        paired = pd.concat(counts, axis=1).fillna(0).astype(int).reset_index()
        paired.insert(0, "day", day)
        records.append(paired)
    columns = ["day", "y", "x", *SOURCES]
    return pd.concat(records, ignore_index=True) if records else pd.DataFrame(columns=columns)


def spatial_validation(cells, holdout, factor):
    """Compare counts on the same occupied grid-days in the temporal holdout."""
    selected = cells[cells.day.str[:7].isin(holdout.index)]
    modis, viirs = SOURCES
    rows = []
    for method, scale in [("Raw grid-day MODIS", 1), ("Calibrated grid-day MODIS", factor)]:
        error = selected[modis] * scale - selected[viirs]
        rows.append({"Method": method, "Occupied grid-days": len(selected),
                     "MAE": error.abs().mean(), "Bias": error.mean()})
    return pd.DataFrame(rows).set_index("Method")
