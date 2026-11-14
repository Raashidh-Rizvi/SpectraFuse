"""Aggregate saved model predictions over matched Aqua and NOAA-20 detections."""

import csv
import json
import math
from collections import defaultdict

from match_frp_archives import OUTPUT as MATCHES
from train_viirs_frp import FEATURES, MODEL, TARGET


OUTPUT = MATCHES.with_name("monthly-frp-harmonization.csv")


def main():
    model = json.loads(MODEL.read_text(encoding="utf-8"))
    cutoff = model["test_start_date"]
    totals = defaultdict(lambda: [0, 0.0, 0.0, 0.0])
    with MATCHES.open(newline="", encoding="utf-8-sig") as source:
        for row in csv.DictReader(source):
            values = [float(row[key] or "nan") for key in (*FEATURES, TARGET)]
            if not all(math.isfinite(value) for value in values):
                continue
            modis_date, viirs_date = row["modis_acq_date"], row["viirs_acq_date"]
            if max(modis_date, viirs_date) < cutoff:
                split = "training"
            elif min(modis_date, viirs_date) >= cutoff:
                split = "test"
            else:
                split = "crosses_cutoff"
            prediction = max(
                model["minimum_prediction_mw"],
                model["intercept"] + sum(
                    model["coefficients"][key] * value
                    for key, value in zip(FEATURES, values)
                ),
            )
            total = totals[viirs_date[:7], split]
            total[0] += 1
            total[1] += values[0]
            total[2] += values[-1]
            total[3] += prediction

    if not totals:
        raise SystemExit("No finite matched detections to harmonize.")
    with OUTPUT.open("w", encoding="utf-8", newline="") as target:
        writer = csv.writer(target)
        writer.writerow([
            "month", "split", "matched_pairs", "paired_aqua_frp_sum_mw",
            "paired_observed_noaa20_frp_sum_mw", "paired_estimated_noaa20_frp_sum_mw",
        ])
        for (month, split), (count, *values) in sorted(totals.items()):
            writer.writerow([month, split, count, *(round(value, 3) for value in values)])
    print(f"{sum(row[0] for row in totals.values())} matched pairs across "
          f"{len({month for month, _ in totals})} months")
    print(OUTPUT)


if __name__ == "__main__":
    main()
