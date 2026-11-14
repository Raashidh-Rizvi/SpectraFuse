"""Build the reproducible Sri Lanka pilot report after both downloads complete."""
import argparse
import sys
from pathlib import Path

import plotly.express as px

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.analytics import evaluate_overlap, historical_anomalies
from backend.fire import SOURCES, atomic, monthly, workspace
from backend.grid import daily_grid, spatial_validation

AREA = "79.5,5.8,82,10"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--partial", action="store_true")
    args = parser.parse_args()
    table, metrics = monthly(AREA)
    pilot = table.loc["2018-01":"2023-12"]
    paired = len(pilot.dropna(subset=list(SOURCES)))
    if paired != 72 and not args.partial:
        raise SystemExit("The pilot requires 72 complete months for both products.")
    holdout, validation = evaluate_overlap(pilot)
    if holdout.empty:
        raise SystemExit("Insufficient paired months for holdout validation.")
    cells = daily_grid(AREA, "2018-01-01", "2023-12-31")
    output = workspace(AREA) / "harmonized" / ("pilot" if paired == 72 else "pilot-partial")
    for name, frame in {
        "monthly-activity": pilot.join(historical_anomalies(pilot.harmonized)),
        "holdout-comparison": holdout,
        "holdout-metrics": validation,
        "daily-grid": cells,
        "spatial-validation": spatial_validation(cells, holdout, metrics["factor"]),
    }.items():
        atomic(output / f"{name}.csv", lambda path: frame.to_csv(path, index=name != "daily-grid"))

    series = pilot[[*SOURCES, "harmonized"]].rename(columns={
        SOURCES[0]: "MODIS raw", SOURCES[1]: "VIIRS S-NPP raw", "harmonized": "Harmonized"})
    figure = px.line(series, title=f"Sri Lanka pilot · {paired}/72 paired months",
                     labels={"month": "UTC month", "value": "Detection count or VIIRS-scale activity", "variable": "Product"})
    figure.update_traces(line_dash="dash", selector={"name": "Harmonized"})
    atomic(output / "monthly-comparison.html", lambda path: figure.write_html(path))
    print(f"Detected MODIS: {int(pilot[SOURCES[0]].sum()):,}; VIIRS: {int(pilot[SOURCES[1]].sum()):,}")
    print(f"Grid-days occupied by both products: {(cells[list(SOURCES)] > 0).all(axis=1).sum():,} / {len(cells):,}")
    print(metrics)
    print(validation.to_string())
    print(output)


if __name__ == "__main__":
    main()
