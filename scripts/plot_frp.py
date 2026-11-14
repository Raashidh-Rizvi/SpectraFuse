"""Compare FRP for nearby MODIS and VIIRS JPSS-1 detections."""

import csv
import math
import tempfile
import webbrowser
from bisect import bisect_left, bisect_right
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import StatisticsError, correlation


START_DATE = "2018-01-01"
END_DATE = "2025-12-30"
MAX_DISTANCE_KM = 0.8
MAX_TIME_MINUTES = 20


def read_detections(folder, start, end):
    detections = []
    for path in sorted(folder.rglob("*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                if not start <= row["acq_date"] <= end:
                    continue
                day = date.fromisoformat(row["acq_date"])
                time = row["acq_time"].strip().zfill(4)
                hour, minute = int(time[:2]), int(time[2:])
                if not 0 <= hour < 24 or not 0 <= minute < 60:
                    raise ValueError(f"Invalid acquisition time in {path}: {time}")
                timestamp = day.toordinal() * 1440 + hour * 60 + minute
                lat, lon, frp = (float(row[key] or "nan") for key in ("latitude", "longitude", "frp"))
                if all(math.isfinite(value) for value in (lat, lon, frp)):
                    detections.append((timestamp, math.radians(lat), math.radians(lon), frp))
    return sorted(detections)


def distance_km(a, b):
    _, lat_a, lon_a, _ = a
    _, lat_b, lon_b, _ = b
    haversine = (
        math.sin((lat_b - lat_a) / 2) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin((lon_b - lon_a) / 2) ** 2
    )
    return 12742 * math.asin(math.sqrt(min(1, haversine)))


def match_detections(modis, viirs):
    viirs_times = [row[0] for row in viirs]
    candidates = []
    for i, detection in enumerate(modis):
        timestamp = detection[0]
        first = bisect_left(viirs_times, timestamp - MAX_TIME_MINUTES)
        last = bisect_right(viirs_times, timestamp + MAX_TIME_MINUTES)
        for j in range(first, last):
            distance = distance_km(detection, viirs[j])
            if distance <= MAX_DISTANCE_KM:
                candidates.append((abs(timestamp - viirs_times[j]), distance, i, j))

    # Prefer the smallest time gap, then the smallest distance. Use each row once.
    used_modis, used_viirs = set(), set()
    pairs = []
    for minutes, km, i, j in sorted(candidates):
        if i not in used_modis and j not in used_viirs:
            used_modis.add(i)
            used_viirs.add(j)
            pairs.append((modis[i], viirs[j], minutes, km))
    return pairs


def save_plot(pairs, start, end, output, *, viirs_label="JPSS-1", match_label=None):
    if match_label is None:
        match_label = f"Within {MAX_DISTANCE_KM:g} km and {MAX_TIME_MINUTES:g} min"
    modis_values = [modis[3] for modis, _, _, _ in pairs]
    viirs_values = [viirs[3] for _, viirs, _, _ in pairs]
    try:
        summary = f"Pearson r = {correlation(modis_values, viirs_values):.3f}"
    except StatisticsError:
        summary = "Pearson r undefined"

    low = min([0, *modis_values, *viirs_values])
    high = max([1, *modis_values, *viirs_values])
    left, top, size = 90, 105, 420
    bottom = top + size
    svg = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 600" '
        'width="600" height="600" font-family="sans-serif" font-size="13">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<text x="300" y="30" text-anchor="middle" font-size="22">Matched MODIS and VIIRS FRP</text>',
        f'<text x="300" y="55" text-anchor="middle">{start} to {end} · {len(pairs):,} pairs · {summary}</text>',
        f'<text x="300" y="77" text-anchor="middle">{match_label}</text>',
        '<text x="300" y="575" text-anchor="middle">MODIS FRP (MW)</text>',
        f'<text transform="translate(24 315) rotate(-90)" text-anchor="middle">VIIRS {viirs_label} FRP (MW)</text>',
    ]
    for index in range(6):
        fraction = index / 5
        x, y = left + fraction * size, bottom - fraction * size
        value = low + fraction * (high - low)
        svg.extend([
            f'<path d="M{left} {y}h{size} M{x} {top}v{size}" stroke="#dbe3ea"/>',
            f'<text x="{left - 8}" y="{y + 4}" text-anchor="end">{value:.3g}</text>',
            f'<text x="{x}" y="{bottom + 22}" text-anchor="middle">{value:.3g}</text>',
        ])
    svg.append(f'<path d="M{left} {bottom}l{size} {-size}" stroke="#64748b" stroke-dasharray="5 4"/>')

    for modis, viirs, minutes, km in pairs:
        x = left + (modis[3] - low) / (high - low) * size
        y = bottom - (viirs[3] - low) / (high - low) * size
        modis_time = datetime.fromordinal(modis[0] // 1440) + timedelta(minutes=modis[0] % 1440)
        viirs_time = datetime.fromordinal(viirs[0] // 1440) + timedelta(minutes=viirs[0] % 1440)
        svg.append(
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="#155e9d" fill-opacity="0.75">'
            f'<title>MODIS {modis[3]:g} MW at {modis_time:%Y-%m-%d %H:%M} UTC | '
            f'VIIRS {viirs[3]:g} MW at {viirs_time:%Y-%m-%d %H:%M} UTC | '
            f'{minutes} min apart | {km:.2f} km apart</title></circle>'
        )
    if not pairs:
        svg.append('<text x="300" y="315" text-anchor="middle">No pairs within the selected tolerances</text>')
    svg.append("</svg>")
    output.write_text("\n".join(svg), encoding="utf-8")


def main():
    start = date.fromisoformat(START_DATE)
    end = date.fromisoformat(END_DATE)
    if start > end:
        raise SystemExit("END_DATE must be on or after START_DATE")
    if any(not math.isfinite(limit) or limit < 0 for limit in (MAX_DISTANCE_KM, MAX_TIME_MINUTES)):
        raise SystemExit("Matching tolerances must be finite and nonnegative")

    data = Path(__file__).resolve().parents[1] / "data" / "sri-lanka-2000-2025"
    modis = read_detections(data / "modis", start.isoformat(), end.isoformat())
    viirs = read_detections(data / "viirs-jpss1", start.isoformat(), end.isoformat())
    pairs = match_detections(modis, viirs)
    print(f"MODIS: {len(modis):,} | VIIRS JPSS-1: {len(viirs):,} | Matched: {len(pairs):,}")

    with tempfile.NamedTemporaryFile(prefix="frp-matches-", suffix=".svg", delete=False) as temporary:
        output = Path(temporary.name)
    save_plot(pairs, start, end, output)
    if not webbrowser.open(output.as_uri()):
        print(f"Open this file in your browser: {output}")


if __name__ == "__main__":
    main()
