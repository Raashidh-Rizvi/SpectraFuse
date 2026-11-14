"""Backcast VIIRS-equivalent FRP from Sri Lankan MODIS detections."""

import csv
import json
import math

from match_frp_archives import MODIS_CSV
from train_viirs_frp import MODEL


OUTPUT = MODEL.with_name("sri-lanka-synthetic-noaa20-2000-2018.csv")


def main():
    model = json.loads(MODEL.read_text(encoding="utf-8"))
    fields = ("acq_date", "acq_time", "latitude", "longitude")
    count = terra_count = 0
    with MODIS_CSV.open(encoding="utf-8-sig", newline="") as source, OUTPUT.open(
        "w", encoding="utf-8", newline=""
    ) as target:
        writer = csv.writer(target)
        writer.writerow([
            *fields, "source_modis_satellite", "source_modis_frp_mw",
            "estimated_noaa20_frp_mw", "terra_model_transfer", "data_origin",
        ])
        for row in csv.DictReader(source):
            if not "2000-01-01" <= row["acq_date"] <= "2018-12-31":
                continue
            frp = float(row["frp"] or "nan")
            if not math.isfinite(frp) or frp < 0:
                continue
            # No historical VIIRS match is assumed. Evaluate at zero match offsets.
            prediction = max(
                model["minimum_prediction_mw"],
                model["intercept"] + model["coefficients"]["modis_frp"] * frp,
            )
            terra = row["satellite"] == "Terra"
            writer.writerow([
                *(row[field] for field in fields), row["satellite"], frp,
                round(prediction, 3), terra, "synthetic_modis_backcast",
            ])
            count += 1
            terra_count += terra
    print(f"{count:,} synthetic records, including {terra_count:,} Terra transfers")
    print(OUTPUT)


if __name__ == "__main__":
    main()
