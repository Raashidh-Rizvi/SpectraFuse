"""Fit the Punjab study's monthly FRP model to Sri Lankan FIRMS data."""

import csv
import math
from collections import defaultdict
from pathlib import Path
from statistics import correlation, mean


START_MONTH = "2018-05"
END_MONTH = "2025-12"
VALIDATION_START_MONTH = "2025-01"
DATA = Path(__file__).resolve().parents[1] / "data" / "sri-lanka-2000-2025"
OUTPUT = DATA.parent / "frp-plots" / "monthly-frp-harmonization.csv"


def monthly_totals(folder, satellite=None):
    totals = defaultdict(float)
    for path in sorted(folder.rglob("*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                if satellite and row["satellite"] != satellite:
                    continue
                month = row["acq_date"][:7]
                if START_MONTH <= month <= END_MONTH:
                    value = float(row["frp"] or "nan")
                    if math.isfinite(value) and value >= 0:
                        totals[month] += value
    return totals


def fit_gaussian(rows):
    """Fit amplitude analytically for each candidate peak and width."""
    scale = max(x for x, _ in rows)
    if scale <= 0 or len({x for x, _ in rows}) < 3:
        raise ValueError("The training set needs at least three distinct MODIS totals.")
    normalized = [(x / scale, y) for x, y in rows]

    def evaluate(center, log_width):
        width = math.exp(log_width)
        basis = [math.exp(-0.5 * ((x - center) / width) ** 2) for x, _ in normalized]
        norm = sum(g * g for g in basis)
        if norm < 1e-24:
            return math.inf, center, log_width, 0.0
        amplitude = sum(g * y for g, (_, y) in zip(basis, normalized)) / norm
        error = sum((amplitude * g - y) ** 2 for g, (_, y) in zip(basis, normalized))
        return error, center, log_width, amplitude

    # Search a broad range, then refine around the best candidate.
    best = min(evaluate(i / 10, j / 4) for i in range(51) for j in range(-20, 13))
    for step in (0.05, 0.01, 0.002, 0.0004):
        _, center, log_width, _ = best
        best = min(
            evaluate(center + i * step, log_width + j * step)
            for i in range(-5, 6) for j in range(-5, 6)
        )
    _, center, log_width, amplitude = best
    return amplitude, center * scale, math.exp(log_width) * scale


def main():
    aqua = monthly_totals(DATA / "modis", "Aqua")
    viirs = monthly_totals(DATA / "viirs-jpss1")
    months = sorted(aqua.keys() & viirs.keys())
    training = [(aqua[m], viirs[m]) for m in months if m < VALIDATION_START_MONTH]
    validation = [(aqua[m], viirs[m]) for m in months if m >= VALIDATION_START_MONTH]
    if len(training) < 3 or not validation:
        raise SystemExit("Choose dates that give at least three training months and one validation month.")
    a, b, c = fit_gaussian(training)

    def predict(x):
        return a * math.exp(-0.5 * ((x - b) / c) ** 2)

    OUTPUT.parent.mkdir(exist_ok=True)
    low, high = min(x for x, _ in training), max(x for x, _ in training)
    with OUTPUT.open("w", encoding="utf-8", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(["month", "aqua_modis_frp_sum_mw", "noaa20_viirs_frp_sum_mw",
                         "estimated_noaa20_frp_sum_mw", "split", "outside_training_range"])
        for month in months:
            x = aqua[month]
            split = "training" if month < VALIDATION_START_MONTH else "validation"
            writer.writerow([month, round(x, 3), round(viirs[month], 3),
                             round(predict(x), 3), split, not low <= x <= high])

    observed = [y for _, y in validation]
    errors = [predict(x) - y for x, y in validation]
    total_variance = sum((y - mean(observed)) ** 2 for y in observed)
    print(f"{months[0]} to {months[-1]}: {len(training)} training and {len(validation)} validation months")
    x, y = zip(*training)
    print(f"Training Pearson r: {correlation(x, y):.3f}")
    print(f"Gaussian a={a:.3f}, b={b:.3f}, c={c:.3f}; MODIS training range {low:.3f} to {high:.3f}")
    print(f"Validation MAE: {mean(map(abs, errors)):,.1f} MW")
    print(f"Validation mean-only baseline MAE: {mean(abs(mean(y) - v) for v in observed):,.1f} MW")
    if total_variance:
        print(f"Validation R-squared: {1 - sum(e * e for e in errors) / total_variance:.3f}")
    print(OUTPUT)


if __name__ == "__main__":
    main()
