"""Plot FRP and report Pearson correlation for all matched archive pairs."""

import csv
import math
import tempfile
import webbrowser
from pathlib import Path
from statistics import StatisticsError, correlation

from match_frp_archives import OUTPUT
from plot_frp import save_plot
from datetime import date, datetime


def main():
    pairs = []
    dates = []
    with OUTPUT.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            readings = []
            for sensor in ("modis", "viirs"):
                acquired = datetime.strptime(
                    f"{row[f'{sensor}_acq_date']} {row[f'{sensor}_acq_time'].zfill(4)}",
                    "%Y-%m-%d %H%M",
                )
                minute = acquired.toordinal() * 1440 + acquired.hour * 60 + acquired.minute
                readings.append((minute, 0, 0, float(row[f"{sensor}_frp"] or "nan")))
            if all(math.isfinite(reading[3]) for reading in readings):
                modis, viirs = readings
                pairs.append((modis, viirs, int(row["time_difference_minutes"]), float(row["distance_km"])))
                dates.extend(date.fromordinal(reading[0] // 1440) for reading in readings)

    try:
        r = correlation([modis[3] for modis, _, _, _ in pairs],
                        [viirs[3] for _, viirs, _, _ in pairs])
        print(f"{len(pairs):,} pairs | Pearson r = {r:.4f}")
    except StatisticsError:
        print(f"{len(pairs):,} pairs | Pearson r undefined")
    if not pairs:
        return

    with tempfile.NamedTemporaryFile(suffix=".svg", prefix="frp-correlation-", delete=False) as target:
        plot = Path(target.name)
    save_plot(pairs, min(dates), max(dates), plot, viirs_label="NOAA-21",
              match_label="All pairs from the matched archives")
    if not webbrowser.open(plot.as_uri()):
        print(plot)


if __name__ == "__main__":
    main()
