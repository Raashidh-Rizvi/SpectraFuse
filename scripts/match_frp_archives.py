"""Export every MODIS and NOAA-20 pair within the configured limits."""

import argparse
import csv
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "sri-lanka-2000-2025"
MODIS_CSV = DATA / "MODIS_SP.csv"
VIIRS_CSV = DATA / "VIIRS_NOAA20_SP.csv"
OUTPUT = ROOT / "data" / "frp-plots" / "modis-noaa20-matches.csv"
PROCESSED = ROOT / "data" / "processed data"
MAX_KM = 0.5
MAX_MINUTES = 10


def detections(path):
    with path.open(encoding="utf-8-sig", newline="") as source:
        for index, row in enumerate(csv.DictReader(source), start=1):
            acquired = datetime.strptime(
                f"{row['acq_date']} {row['acq_time'].strip().zfill(4)}", "%Y-%m-%d %H%M"
            )
            minute = acquired.toordinal() * 1440 + acquired.hour * 60 + acquired.minute
            lat, lon = map(float, (row["latitude"], row["longitude"]))
            yield index, minute, lat, lon, row


def distance_km(lat_a, lon_a, lat_b, lon_b):
    a, b = math.radians(lat_a), math.radians(lat_b)
    h = math.sin((b - a) / 2) ** 2 + (
        math.cos(a) * math.cos(b) * math.sin(math.radians(lon_b - lon_a) / 2) ** 2
    )
    return 12742 * math.asin(math.sqrt(min(1, h)))


def export_matched_records(source, output, matched_records):
    with source.open(encoding="utf-8-sig", newline="") as input_file, output.open(
        "w", encoding="utf-8", newline=""
    ) as output_file:
        reader = csv.DictReader(input_file)
        writer = csv.DictWriter(output_file, fieldnames=["source_record", *reader.fieldnames])
        writer.writeheader()
        for index, row in enumerate(reader, start=1):
            if index in matched_records:
                writer.writerow({"source_record": index, **row})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--merged-only", action="store_true",
                        help="Write only the merged CSV.")
    args = parser.parse_args()
    # Latitude bins are wider than 1 km. Search adjacent bins and verify distance.
    bin_degrees = MAX_KM / 100
    viirs_by_bin = defaultdict(list)
    satellites = set()
    for detection in detections(VIIRS_CSV):
        _, minute, lat, _, row = detection
        satellites.add(row["satellite"])
        viirs_by_bin[minute // MAX_MINUTES, math.floor(lat / bin_degrees)].append(detection)

    fields = ("satellite", "acq_date", "acq_time", "latitude", "longitude", "frp", "confidence", "type")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    counts = defaultdict(int)
    matched_modis, matched_viirs = set(), set()
    with OUTPUT.open("w", encoding="utf-8", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(["modis_record", "viirs_record", "time_difference_minutes", "distance_km"]
                        + [f"{sensor}_{field}" for sensor in ("modis", "viirs") for field in fields])
        for index, minute, lat, lon, modis in detections(MODIS_CSV):
            if modis["satellite"] != "Aqua":
                continue
            lat_bin = math.floor(lat / bin_degrees)
            for time_bin in range((minute - MAX_MINUTES) // MAX_MINUTES,
                                  (minute + MAX_MINUTES) // MAX_MINUTES + 1):
                for nearby_bin in range(lat_bin - 1, lat_bin + 2):
                    for other, other_minute, other_lat, other_lon, viirs in viirs_by_bin.get(
                        (time_bin, nearby_bin), ()
                    ):
                        gap = abs(minute - other_minute)
                        if gap > MAX_MINUTES:
                            continue
                        distance = distance_km(lat, lon, other_lat, other_lon)
                        if distance <= MAX_KM:
                            writer.writerow([index, other, gap, f"{distance:.9f}"]
                                            + [row[field] for row in (modis, viirs) for field in fields])
                            counts[modis["satellite"]] += 1
                            matched_modis.add(index)
                            matched_viirs.add(other)

    if not args.merged_only:
        PROCESSED.mkdir(parents=True, exist_ok=True)
        export_matched_records(MODIS_CSV, PROCESSED / "modis_matched.csv", matched_modis)
        export_matched_records(VIIRS_CSV, PROCESSED / "viirs_noaa20_matched.csv", matched_viirs)
    print(f"Filtered records: {len(matched_modis):,} MODIS, {len(matched_viirs):,} VIIRS")

    print(f"VIIRS platform codes: {', '.join(sorted(satellites))}")
    print(f"{sum(counts.values()):,} pairs: {dict(sorted(counts.items()))}")
    print(OUTPUT)


if __name__ == "__main__":
    main()
