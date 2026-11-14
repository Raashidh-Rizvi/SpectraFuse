"""Train a linear model to predict VIIRS FRP (MW) from three match features."""
import csv
import json
import math
from statistics import mean

from match_frp_archives import OUTPUT

FEATURES = ("modis_frp", "distance_km", "time_difference_minutes")
TARGET = "viirs_frp"
MODEL = OUTPUT.with_name("viirs-frp-model.json")


def fit(rows):
    # Coordinate descent solves ordinary least squares using centered features.
    columns = list(zip(*rows))
    centers = [mean(column) for column in columns]
    features = [[value - center for value in column]
                for column, center in zip(columns[:-1], centers[:-1])]
    residuals = [value - centers[-1] for value in columns[-1]]
    coefficients = [0.0] * len(features)
    for _ in range(1000):
        largest_change = 0.0
        for i, feature in enumerate(features):
            norm = sum(value * value for value in feature)
            if not norm:
                continue
            change = sum(value * error for value, error in zip(feature, residuals)) / norm
            coefficients[i] += change
            residuals = [error - change * value for error, value in zip(residuals, feature)]
            largest_change = max(largest_change, abs(change))
        if largest_change < 1e-9:
            break
    intercept = centers[-1] - sum(c * x for c, x in zip(coefficients, centers))
    return intercept, coefficients


def main():
    records = []
    with OUTPUT.open(newline="", encoding="utf-8-sig") as source:
        for row in csv.DictReader(source):
            values = tuple(float(row[key] or "nan") for key in (*FEATURES, TARGET))
            if all(math.isfinite(value) for value in values):
                records.append((row["modis_acq_date"], row["viirs_acq_date"], values))

    dates = sorted({day for modis, viirs, _ in records for day in (modis, viirs)})
    if len(dates) < 5:
        raise SystemExit("At least five distinct acquisition dates are needed.")
    cutoff = dates[int(len(dates) * 0.8)]
    train = [values for m, v, values in records if max(m, v) < cutoff]
    test = [values for m, v, values in records if min(m, v) >= cutoff]
    if not train or not test:
        raise SystemExit("The date split needs both training and test pairs.")
    intercept, coefficients = fit(train)
    actual = [row[-1] for row in test]
    errors = [max(0, intercept + sum(c * x for c, x in zip(coefficients, row))) - row[-1]
              for row in test]
    baseline = mean(row[-1] for row in train)
    variance = sum((y - mean(actual)) ** 2 for y in actual)
    model = {"intercept": intercept, "coefficients": dict(zip(FEATURES, coefficients)),
             "minimum_prediction_mw": 0, "test_start_date": cutoff}
    MODEL.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8")
    print(f"Training pairs: {len(train):,} | Test pairs: {len(test):,} | Test starts: {cutoff}")
    print(f"Test MAE: {mean(map(abs, errors)):.2f} MW")
    print(f"Training-mean baseline MAE: {mean(abs(y - baseline) for y in actual):.2f} MW")
    if variance:
        print(f"Test R-squared: {1 - sum(e * e for e in errors) / variance:.3f}")
    print(MODEL)


if __name__ == "__main__":
    main()
